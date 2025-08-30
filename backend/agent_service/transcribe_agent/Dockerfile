# Lightweight LiveKit Agent Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared components
COPY ../shared ./shared

# Copy agent code
COPY . .

# Health check (simple process check)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep -f "python.*agent.py" || exit 1

# Run the agent
CMD ["python", "agent.py"]
