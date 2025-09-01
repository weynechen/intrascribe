# Lightweight LiveKit Agent Dockerfile
FROM docker.xuanyuan.me/library/python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including uv and build tools
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    gcc \
    g++ \
    python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

# Copy pyproject.toml and uv.lock for dependency installation
COPY ./agent_service/transcribe_agent/pyproject.toml ./agent_service/transcribe_agent/uv.lock ./
RUN uv sync --frozen --no-dev

# Copy shared components
COPY ./shared ./shared

# Copy agent code
COPY ./agent_service/transcribe_agent .

# Health check (simple process check)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep -f "python.*agent.py" || exit 1

# Run the agent using uv
CMD ["uv", "run", "python", "agent.py"]
