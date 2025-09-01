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

echo "📦 Building Web Application..."
docker build -t intrascribe/web-app:latest -f ../web/Dockerfile ../web

echo "✅ All services built successfully!"

# Optional: Push to registry
if [ "$1" = "--push" ]; then
    echo "🚢 Pushing images to registry..."
    docker push intrascribe/stt-service:latest
    docker push intrascribe/diarization-service:latest
    docker push intrascribe/api-service:latest
    docker push intrascribe/agent-service:latest
    docker push intrascribe/web-app:latest
    echo "✅ All images pushed to registry!"
fi

echo "🎉 Build process completed!"
echo ""
echo "启动选项:"
echo "  完整Docker环境 (包括Web):  docker-compose up -d"
echo "  仅后端微服务:             docker-compose up -d redis stt-service diarization-service api-service"
echo "  查看日志:                 docker-compose logs -f"
echo ""
echo "Web应用选项:"
echo "  Docker版本:               docker-compose up -d web-app"
echo "  开发版本:                 cd ../web && npm run dev"
echo ""
echo "Agent服务:"
echo "  启动Agent:                docker-compose up --scale agent-service=1 -d"
echo ""
echo "注意: Supabase和LiveKit需要单独启动"
echo "  Supabase:                 cd ../supabase && supabase start"  
echo "  LiveKit:                  livekit-server --config livekit.yaml"
