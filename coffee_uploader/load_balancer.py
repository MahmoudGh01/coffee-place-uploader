from __future__ import annotations

import argparse
import json
import logging
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urljoin

import httpx


log = logging.getLogger(__name__)


def _normalize_base_url(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError("instance URL cannot be empty")
    if not value.startswith(("http://", "https://")):
        raise ValueError(f"instance URL must include scheme: {value!r}")
    return value.rstrip("/")


def _is_healthy(response: httpx.Response) -> bool:
    if response.status_code < 200 or response.status_code >= 300:
        return False

    content_type = response.headers.get("Content-Type", "")
    if "application/json" not in content_type:
        return True

    try:
        payload = response.json()
    except ValueError:
        return True

    if isinstance(payload, dict) and "status" in payload:
        return str(payload["status"]).upper() == "UP"
    return True


def _parse_service_urls(instances: str | None, instances_file: Path | None) -> list[str]:
    values: list[str] = []

    if instances:
        for raw in instances.split(","):
            if raw.strip():
                values.append(raw.strip())

    if instances_file:
        for line in instances_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                values.append(line)

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        url = _normalize_base_url(raw)
        if url not in seen:
            normalized.append(url)
            seen.add(url)
    return normalized


def _build_backends(internal_urls: list[str], public_urls: list[str] | None) -> list[BackendTarget]:
    if not public_urls:
        return [BackendTarget(internal_url=url, public_url=url) for url in internal_urls]
    if len(public_urls) != len(internal_urls):
        raise ValueError(
            "public instance list size must match backend instance list size"
        )
    return [
        BackendTarget(internal_url=internal_urls[idx], public_url=public_urls[idx])
        for idx in range(len(internal_urls))
    ]


@dataclass(frozen=True)
class BackendTarget:
    internal_url: str
    public_url: str


@dataclass(frozen=True)
class InstanceStatus:
    backend: BackendTarget
    healthy: bool
    detail: str


class RoundRobinSelector:
    def __init__(self):
        self._index = 0
        self._lock = threading.Lock()

    def choose(self, healthy_instances: list[BackendTarget]) -> BackendTarget | None:
        if not healthy_instances:
            return None
        with self._lock:
            selected = healthy_instances[self._index % len(healthy_instances)]
            self._index += 1
            return selected


class ServiceRegistry:
    def __init__(
        self,
        backends: list[BackendTarget],
        *,
        health_path: str,
        timeout: float,
    ):
        if not backends:
            raise ValueError("at least one service URL is required")

        self._backends = list(backends)
        self._health_path = "/" + health_path.lstrip("/")
        self._timeout = timeout
        self._lock = threading.Lock()
        self._statuses: dict[str, InstanceStatus] = {
            backend.internal_url: InstanceStatus(
                backend=backend,
                healthy=False,
                detail="not checked yet",
            )
            for backend in self._backends
        }

    def refresh(self) -> None:
        updates: dict[str, InstanceStatus] = {}
        with httpx.Client(timeout=self._timeout) as client:
            for backend in self._backends:
                health_url = f"{backend.internal_url}{self._health_path}"
                try:
                    response = client.get(health_url)
                except httpx.HTTPError as exc:
                    updates[backend.internal_url] = InstanceStatus(
                        backend=backend,
                        healthy=False,
                        detail=f"{type(exc).__name__}: {exc}",
                    )
                    continue

                healthy = _is_healthy(response)
                detail = (
                    f"HTTP {response.status_code}"
                    if healthy
                    else f"HTTP {response.status_code}: unhealthy"
                )
                updates[backend.internal_url] = InstanceStatus(
                    backend=backend,
                    healthy=healthy,
                    detail=detail,
                )

        with self._lock:
            self._statuses = updates

    def healthy_instances(self) -> list[BackendTarget]:
        with self._lock:
            return [s.backend for s in self._statuses.values() if s.healthy]

    def snapshot(self) -> list[InstanceStatus]:
        with self._lock:
            return list(self._statuses.values())


def _make_handler(
    registry: ServiceRegistry,
    selector: RoundRobinSelector,
) -> type[BaseHTTPRequestHandler]:
    class RedirectHandler(BaseHTTPRequestHandler):
        def _send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_no_content(self, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def _service_snapshot_payload(self) -> dict:
            snapshot = registry.snapshot()
            return {
                "total": len(snapshot),
                "healthy": sum(1 for item in snapshot if item.healthy),
                "services": [
                    {
                        "internalUrl": item.backend.internal_url,
                        "publicUrl": item.backend.public_url,
                        "healthy": item.healthy,
                        "detail": item.detail,
                    }
                    for item in snapshot
                ],
            }

        def _handle_internal_routes(self) -> bool:
            path = self.path.split("?", 1)[0]
            if path == "/_lb/services":
                if self.command == "HEAD":
                    self._send_no_content(status=200)
                else:
                    self._send_json(self._service_snapshot_payload(), status=200)
                return True

            if path == "/_lb/health":
                has_healthy = bool(registry.healthy_instances())
                payload = {
                    "status": "UP" if has_healthy else "DOWN",
                    "healthyBackends": len(registry.healthy_instances()),
                }
                status = 200 if has_healthy else 503
                if self.command == "HEAD":
                    self._send_no_content(status=status)
                else:
                    self._send_json(payload, status=status)
                return True

            return False

        def _redirect(self) -> None:
            if self._handle_internal_routes():
                return

            target_backend = selector.choose(registry.healthy_instances())
            if not target_backend:
                details = "; ".join(
                    f"{item.backend.internal_url} ({item.detail})"
                    for item in registry.snapshot()
                )
                body = (
                    "No healthy backend services available. "
                    f"Last checks: {details}\n"
                )
                self.send_response(503)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))
                return

            location = urljoin(f"{target_backend.public_url}/", self.path.lstrip("/"))
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            log.info("%s %s -> %s", self.command, self.path, location)

        def do_GET(self) -> None:
            self._redirect()

        def do_POST(self) -> None:
            self._redirect()

        def do_PUT(self) -> None:
            self._redirect()

        def do_PATCH(self) -> None:
            self._redirect()

        def do_DELETE(self) -> None:
            self._redirect()

        def do_HEAD(self) -> None:
            self._redirect()

        def log_message(self, format: str, *args) -> None:
            log.info("server: " + format, *args)

    return RedirectHandler


def run_redirect_balancer(
    *,
    listen_host: str,
    listen_port: int,
    backends: list[BackendTarget],
    health_path: str,
    health_timeout: float,
    check_interval: float,
) -> None:
    registry = ServiceRegistry(
        backends,
        health_path=health_path,
        timeout=health_timeout,
    )
    selector = RoundRobinSelector()

    stop_event = threading.Event()

    def health_loop() -> None:
        while not stop_event.is_set():
            registry.refresh()
            stop_event.wait(check_interval)

    registry.refresh()
    checker = threading.Thread(target=health_loop, name="health-checker", daemon=True)
    checker.start()

    handler = _make_handler(registry, selector)
    server = ThreadingHTTPServer((listen_host, listen_port), handler)
    log.info("redirect load balancer started on %s:%d", listen_host, listen_port)
    log.info(
        "services: %s",
        ", ".join(f"{b.internal_url}->{b.public_url}" for b in backends),
    )
    log.info("health check: path=%s every=%ss", health_path, check_interval)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("shutting down redirect load balancer")
    finally:
        stop_event.set()
        server.shutdown()
        server.server_close()
        checker.join(timeout=1.0)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="coffee-redirect-lb",
        description=(
            "HTTP 302 redirect load balancer for multiple StarHarbour "
            "payment-service instances."
        ),
    )
    p.add_argument(
        "--instances",
        help="Comma-separated backend URLs, e.g. http://localhost:8080,http://localhost:8081",
    )
    p.add_argument(
        "--instances-file",
        type=Path,
        help="Path to file with one backend URL per line",
    )
    p.add_argument(
        "--public-instances",
        help=(
            "Comma-separated redirect URLs returned in Location headers, "
            "e.g. http://localhost:8081,http://localhost:8082"
        ),
    )
    p.add_argument(
        "--public-instances-file",
        type=Path,
        help="Path to file with one public redirect URL per line",
    )
    p.add_argument(
        "--listen-host",
        default="0.0.0.0",
        help="Host/IP to bind the load balancer (default: 0.0.0.0)",
    )
    p.add_argument(
        "--listen-port",
        type=int,
        default=8090,
        help="Port to bind the load balancer (default: 8090)",
    )
    p.add_argument(
        "--health-path",
        default="/actuator/health",
        help="Health endpoint path on each backend (default: /actuator/health)",
    )
    p.add_argument(
        "--health-timeout",
        type=float,
        default=2.0,
        help="Health-check request timeout in seconds (default: 2.0)",
    )
    p.add_argument(
        "--check-interval",
        type=float,
        default=5.0,
        help="Health-check interval in seconds (default: 5.0)",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG-level logs",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        service_urls = _parse_service_urls(args.instances, args.instances_file)
        public_urls = _parse_service_urls(
            args.public_instances,
            args.public_instances_file,
        )
        backends = _build_backends(service_urls, public_urls or None)
    except (OSError, ValueError) as exc:
        log.error("invalid instance configuration: %s", exc)
        return 2

    if not service_urls:
        log.error("provide at least one backend using --instances or --instances-file")
        return 2

    run_redirect_balancer(
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        backends=backends,
        health_path=args.health_path,
        health_timeout=max(0.1, args.health_timeout),
        check_interval=max(0.5, args.check_interval),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
