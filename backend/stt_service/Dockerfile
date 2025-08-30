# STT Service Dockerfile
FROM docker.xuanyuan.me/library/python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including uv
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

# Copy pyproject.toml and uv.lock for dependency installation
COPY ./stt_service/pyproject.toml ./stt_service/uv.lock ./
RUN uv sync --frozen --no-dev

# Copy shared components
COPY ./shared ./shared

# Copy service code
COPY ./stt_service .

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run the service using uv
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
