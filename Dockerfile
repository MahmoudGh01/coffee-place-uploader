FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY coffee_uploader ./coffee_uploader

RUN pip install --no-cache-dir .

EXPOSE 8090

CMD ["coffee-redirect-lb", "--listen-host", "0.0.0.0", "--listen-port", "8090"]
