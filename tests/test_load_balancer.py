from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from coffee_uploader.load_balancer import (
    BackendTarget,
    RoundRobinSelector,
    ServiceRegistry,
    _build_backends,
    _is_healthy,
    _parse_service_urls,
)


def test_parse_service_urls_from_inline_and_file(tmp_path: Path):
    instances_file = tmp_path / "instances.txt"
    instances_file.write_text(
        "# comment\nhttp://localhost:8081\nhttp://localhost:8082/\n",
        encoding="utf-8",
    )

    urls = _parse_service_urls(
        "http://localhost:8080/,http://localhost:8081",
        instances_file,
    )

    assert urls == [
        "http://localhost:8080",
        "http://localhost:8081",
        "http://localhost:8082",
    ]


def test_is_healthy_accepts_plain_2xx_and_status_up_json():
    plain = httpx.Response(204, text="")
    assert _is_healthy(plain)

    up = httpx.Response(200, json={"status": "UP"})
    assert _is_healthy(up)

    down = httpx.Response(200, json={"status": "DOWN"})
    assert not _is_healthy(down)

    bad = httpx.Response(503, json={"status": "UP"})
    assert not _is_healthy(bad)


def test_round_robin_selector_cycles_in_order():
    selector = RoundRobinSelector()
    healthy = [
        BackendTarget("http://a", "http://public-a"),
        BackendTarget("http://b", "http://public-b"),
        BackendTarget("http://c", "http://public-c"),
    ]

    picks = [selector.choose(healthy) for _ in range(5)]
    assert all(p is not None for p in picks)

    assert [p.internal_url for p in picks if p is not None] == [
        "http://a",
        "http://b",
        "http://c",
        "http://a",
        "http://b",
    ]


def test_build_backends_uses_public_urls_when_given():
    backends = _build_backends(
        ["http://harbour-1:8090", "http://harbour-2:8090"],
        ["http://localhost:8081", "http://localhost:8082"],
    )
    assert backends[0].internal_url == "http://harbour-1:8090"
    assert backends[0].public_url == "http://localhost:8081"
    assert backends[1].internal_url == "http://harbour-2:8090"
    assert backends[1].public_url == "http://localhost:8082"


def test_build_backends_rejects_mismatched_list_sizes():
    with pytest.raises(ValueError, match="size must match"):
        _build_backends(
            ["http://harbour-1:8090", "http://harbour-2:8090"],
            ["http://localhost:8081"],
        )


def test_service_registry_refresh_tracks_health(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return None

        def get(self, url: str) -> httpx.Response:
            if url == "http://s1/actuator/health":
                return httpx.Response(200, json={"status": "UP"})
            if url == "http://s2/actuator/health":
                return httpx.Response(200, json={"status": "DOWN"})
            raise httpx.ConnectError("refused")

    monkeypatch.setattr("coffee_uploader.load_balancer.httpx.Client", FakeClient)

    registry = ServiceRegistry(
        [
            BackendTarget("http://s1", "http://public-s1"),
            BackendTarget("http://s2", "http://public-s2"),
            BackendTarget("http://s3", "http://public-s3"),
        ],
        health_path="/actuator/health",
        timeout=1.0,
    )

    registry.refresh()

    assert [item.internal_url for item in registry.healthy_instances()] == ["http://s1"]
    snapshot = {item.backend.internal_url: item for item in registry.snapshot()}
    assert snapshot["http://s2"].healthy is False
    assert snapshot["http://s3"].healthy is False
    assert "ConnectError" in snapshot["http://s3"].detail
