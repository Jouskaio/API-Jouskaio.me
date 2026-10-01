# syntax=docker/dockerfile:1

# WITH_OCR=true adds handwriting recognition (kraken + CPU-only torch, about +1.5 GB).
# The OCR variant is linux/amd64 only: kraken's coremltools dependency has no arm64 wheel.
ARG WITH_OCR=false

FROM python:3.12-slim AS builder
ARG WITH_OCR
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv
WORKDIR /app
# Dependencies first: this layer is cached until pyproject.toml / uv.lock change.
COPY pyproject.toml uv.lock ./
RUN if [ "$WITH_OCR" = "true" ]; then extra="--extra ocr"; else extra=""; fi \
    && uv sync --frozen --no-dev --no-install-project $extra
COPY src ./src
RUN if [ "$WITH_OCR" = "true" ]; then extra="--extra ocr"; else extra=""; fi \
    && uv sync --frozen --no-dev $extra

FROM python:3.12-slim
# pandoc converts RTF -> Markdown, poppler-utils extracts the text of PDF files.
RUN apt-get update \
    && apt-get install -y --no-install-recommends pandoc poppler-utils \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --no-create-home app \
    && mkdir /inbox /vault /data \
    && chown app /data
COPY --from=builder /app /app
# The root filesystem is read-only in compose: libraries that want a cache or a config
# directory (torch, matplotlib via lightning) get one on the /tmp tmpfs.
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    HOME=/tmp XDG_CACHE_HOME=/tmp/.cache MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"]
CMD ["uvicorn", "jouskaio_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
