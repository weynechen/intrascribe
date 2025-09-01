# Main API Service Dockerfile
FROM docker.xuanyuan.me/library/python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including uv and basic build tools
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    gcc \
    g++ \
    python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

# Copy pyproject.toml and uv.lock for dependency installation
COPY ./api_service/pyproject.toml ./api_service/uv.lock ./
RUN uv sync --frozen --no-dev

# Copy shared components
COPY ./shared ./shared

# Copy service code
COPY ./api_service .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the service using uv
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
