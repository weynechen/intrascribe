# 此docker file 是将各个微服务聚合在一起的镜像。为了缩小体积而设定，仅做测试使用。
# 使用了国内镜像，如果不在国内，需自行修改镜像地址。
# Use Python 3.12 with Ubuntu base for ML dependencies
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies for audio processing and ML
RUN apt-get update && apt-get install -y \
    # Audio processing dependencies
    ffmpeg \
    libsndfile1 \
    libsndfile1-dev \
    # Build dependencies for Python packages
    build-essential \
    gcc \
    g++ \
    # Network and utility tools
    curl \
    git \
    # Clean up to reduce image size
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster Python package management
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy dependency files first for better cache utilization
COPY pyproject.toml ./
COPY ai_config.yaml ./

# Create virtual environment and install dependencies using uv with Aliyun mirror
RUN uv venv /app/venv && \
    . /app/venv/bin/activate && \
    uv pip install -e . --index-url https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

# Copy only necessary backend files and directories
COPY api_service/ ./api_service/
COPY stt_service/ ./stt_service/
COPY diarization_service/ ./diarization_service/
COPY agent_service/ ./agent_service/
COPY shared/ ./shared/

# Create logs directory
RUN mkdir -p /app/logs

# Create service launcher script
RUN echo '#!/bin/bash' > /app/start_service.sh && \
    echo '' >> /app/start_service.sh && \
    echo '# Activate virtual environment' >> /app/start_service.sh && \
    echo '. /app/venv/bin/activate' >> /app/start_service.sh && \
    echo '' >> /app/start_service.sh && \
    echo '# Set PYTHONPATH to include current directory and shared modules' >> /app/start_service.sh && \
    echo 'export PYTHONPATH="/app:$PYTHONPATH"' >> /app/start_service.sh && \
    echo '' >> /app/start_service.sh && \
    echo '# Set Hugging Face mirror endpoint' >> /app/start_service.sh && \
    echo 'export HF_ENDPOINT=https://hf-mirror.com' >> /app/start_service.sh && \
    echo '' >> /app/start_service.sh && \
    echo '# Start the specified service' >> /app/start_service.sh && \
    echo 'case "$SERVICE_NAME" in' >> /app/start_service.sh && \
    echo '    "api-service")' >> /app/start_service.sh && \
    echo '        echo "Starting API Service..."' >> /app/start_service.sh && \
    echo '        cd /app/api_service' >> /app/start_service.sh && \
    echo '        exec python main.py' >> /app/start_service.sh && \
    echo '        ;;' >> /app/start_service.sh && \
    echo '    "stt-service")' >> /app/start_service.sh && \
    echo '        echo "Starting STT Service..."' >> /app/start_service.sh && \
    echo '        cd /app/stt_service' >> /app/start_service.sh && \
    echo '        exec python main.py' >> /app/start_service.sh && \
    echo '        ;;' >> /app/start_service.sh && \
    echo '    "diarization-service")' >> /app/start_service.sh && \
    echo '        echo "Starting Diarization Service..."' >> /app/start_service.sh && \
    echo '        cd /app/diarization_service' >> /app/start_service.sh && \
    echo '        exec python main.py' >> /app/start_service.sh && \
    echo '        ;;' >> /app/start_service.sh && \
    echo '    "transcribe-agent")' >> /app/start_service.sh && \
    echo '        echo "Starting Transcribe Agent..."' >> /app/start_service.sh && \
    echo '        cd /app/agent_service/transcribe_agent' >> /app/start_service.sh && \
    echo '        exec python agent.py' >> /app/start_service.sh && \
    echo '        ;;' >> /app/start_service.sh && \
    echo '    *)' >> /app/start_service.sh && \
    echo '        echo "Unknown service: $SERVICE_NAME"' >> /app/start_service.sh && \
    echo '        echo "Available services: api-service, stt-service, diarization-service, transcribe-agent"' >> /app/start_service.sh && \
    echo '        exit 1' >> /app/start_service.sh && \
    echo '        ;;' >> /app/start_service.sh && \
    echo 'esac' >> /app/start_service.sh

# Make the launcher script executable
RUN chmod +x /app/start_service.sh

# Create health check script for all services
RUN echo '#!/bin/bash' > /app/health_check.sh && \
    echo 'case "$SERVICE_NAME" in' >> /app/health_check.sh && \
    echo '    "api-service")' >> /app/health_check.sh && \
    echo '        curl -f http://localhost:8000/health || exit 1' >> /app/health_check.sh && \
    echo '        ;;' >> /app/health_check.sh && \
    echo '    "stt-service")' >> /app/health_check.sh && \
    echo '        curl -f http://localhost:8001/health || exit 1' >> /app/health_check.sh && \
    echo '        ;;' >> /app/health_check.sh && \
    echo '    "diarization-service")' >> /app/health_check.sh && \
    echo '        curl -f http://localhost:8002/health || exit 1' >> /app/health_check.sh && \
    echo '        ;;' >> /app/health_check.sh && \
    echo '    "transcribe-agent")' >> /app/health_check.sh && \
    echo '        # For agent, just check if process is running' >> /app/health_check.sh && \
    echo '        pgrep -f "python agent.py" > /dev/null || exit 1' >> /app/health_check.sh && \
    echo '        ;;' >> /app/health_check.sh && \
    echo '    *)' >> /app/health_check.sh && \
    echo '        exit 1' >> /app/health_check.sh && \
    echo '        ;;' >> /app/health_check.sh && \
    echo 'esac' >> /app/health_check.sh

RUN chmod +x /app/health_check.sh

# Expose common ports (can be overridden by specific services)
EXPOSE 8000 8001 8002

# Set default service (can be overridden)
ENV SERVICE_NAME=api-service

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD /app/health_check.sh

# Default command
CMD ["/app/start_service.sh"]
