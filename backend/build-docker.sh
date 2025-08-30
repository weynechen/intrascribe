#!/bin/bash

# Intrascribe Docker Build and Deploy Script
# This script builds all microservices and creates production images

set -e

echo "🚀 Starting Intrascribe Docker Build Process..."

# Load environment variables
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found in backend directory"
    echo "Please create .env file with required environment variables"
    exit 1
fi

source .env

# Build services
echo "📦 Building STT Service..."
docker build -t intrascribe/stt-service:latest -f ./stt_service/Dockerfile .

echo "📦 Building Diarization Service..."
docker build -t intrascribe/diarization-service:latest -f ./diarization_service/Dockerfile .

echo "📦 Building API Service..."
docker build -t intrascribe/api-service:latest -f ./api_service/Dockerfile .

echo "📦 Building Agent Service..."
docker build -t intrascribe/agent-service:latest -f ./agent_service/transcribe_agent/Dockerfile .

echo "✅ All services built successfully!"

# Optional: Push to registry
if [ "$1" = "--push" ]; then
    echo "🚢 Pushing images to registry..."
    docker push intrascribe/stt-service:latest
    docker push intrascribe/diarization-service:latest
    docker push intrascribe/api-service:latest
    docker push intrascribe/agent-service:latest
    echo "✅ All images pushed to registry!"
fi

echo "🎉 Build process completed!"
echo ""
echo "To start services:"
echo "  docker-compose up -d"
echo ""
echo "To start with logs:"
echo "  docker-compose up"
echo ""
echo "To scale agent service:"
echo "  docker-compose up --scale agent-service=1 -d"
