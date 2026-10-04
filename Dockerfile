FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install curl and dos2unix
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    dos2unix \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reliable package installations
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install python package dependencies
COPY pyproject.toml /app/
RUN uv pip install --system --no-cache ".[dev]"

# Copy project files
COPY alembic.ini /app/
COPY alembic /app/alembic
COPY app /app/app
COPY tests /app/tests
COPY entrypoint.sh /app/entrypoint.sh

# Ensure executable permissions and LF line endings on entrypoint
RUN dos2unix /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
