# Multi-platform Dockerfile for nexcoder
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY packages/ ./packages/

# Two-pass installation to resolve monorepo internal dependencies cleanly
RUN for pkg in packages/*/; do pip install -e "$pkg" --no-deps; done
RUN for pkg in packages/*/; do pip install -e "$pkg"; done
RUN pip install "psycopg[binary]>=3.2" "psycopg2-binary>=2.9.9" "pymysql>=1.1.0"

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["nexcoder", "serve", "--transport", "sse", "--host", "0.0.0.0", "--port", "8000", "--api"]
