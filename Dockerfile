FROM python:3.12-slim

# ─────────────────────────────────────────────────────────────────────────────
# IntelligenceOS — Web Service Dockerfile
#
# Render deployment:
#   Service type   : Web Service
#   Dockerfile     : Dockerfile
#   Start command  : (empty — ENTRYPOINT + CMD below handle it)
#   Environment    : set all secrets via Render dashboard or .env import
#
# The entrypoint.sh script:
#   1. Runs `alembic upgrade head` if DATABASE_URL is set
#   2. Starts uvicorn bound to 0.0.0.0:$PORT (Render injects PORT at runtime)
#
# Do NOT bake secrets into this image. Supply all credentials at runtime via
# Render environment variables.
# ─────────────────────────────────────────────────────────────────────────────

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system utilities and Tesseract OCR engine (required for image ingestion)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    dos2unix \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reproducible package installations
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install Python dependencies from pyproject.toml
COPY pyproject.toml /app/
RUN uv pip install --system --no-cache ".[dev]"

# Copy project files — no .env file is copied; all secrets are injected at runtime
COPY alembic.ini /app/
COPY alembic /app/alembic
COPY app /app/app
COPY tests /app/tests
COPY entrypoint.sh /app/entrypoint.sh

# Ensure executable permissions and Unix line endings on entrypoint
RUN dos2unix /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Expose the default port (Render overrides via $PORT at runtime)
EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]

# Default: start the FastAPI web server.
# To run the background worker instead, override CMD in a separate Render service:
#   CMD ["python", "-m", "app.worker"]
CMD ["uvicorn", "app.main:app"]
