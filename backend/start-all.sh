#!/bin/bash

# Intrascribe Complete Environment Startup Script
# 启动所有服务的统一脚本

set -e

echo "🚀 启动Intrascribe完整环境..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ 错误: 未找到 .env 文件"
    echo "请在 backend 目录下创建 .env 文件并配置环境变量"
    exit 1
fi

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Function to wait for service to be ready
wait_for_service() {
    local url=$1
    local service_name=$2
    local max_attempts=30
    local attempt=1
    
    echo "⏳ 等待 $service_name 启动..."
    while [ $attempt -le $max_attempts ]; do
        if curl -f -s "$url" >/dev/null 2>&1; then
            echo "✅ $service_name 已就绪"
            return 0
        fi
        echo "   尝试 $attempt/$max_attempts..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "❌ $service_name 启动超时"
    return 1
}

echo ""
echo "📋 启动计划:"
echo "  1. 检查Supabase状态"
echo "  2. 检查LiveKit状态" 
echo "  3. 启动后端微服务"
echo "  4. 启动Web应用"
echo ""

# Step 1: Check Supabase
echo "🗄️  检查Supabase状态..."
if check_port 54321; then
    echo "✅ Supabase API 已运行 (端口 54321)"
else
    echo "⚠️  Supabase未启动，请先运行:"
    echo "   cd ../supabase && supabase start"
    echo ""
    read -p "是否继续启动其他服务? (y/N): " continue_without_supabase
    if [ "$continue_without_supabase" != "y" ] && [ "$continue_without_supabase" != "Y" ]; then
        exit 1
    fi
fi

# Step 2: Check LiveKit
echo "📡 检查LiveKit状态..."
if check_port 7880; then
    echo "✅ LiveKit 已运行 (端口 7880)"
else
    echo "⚠️  LiveKit未启动，请确保LiveKit Server已启动"
    echo ""
    read -p "是否继续启动其他服务? (y/N): " continue_without_livekit
    if [ "$continue_without_livekit" != "y" ] && [ "$continue_without_livekit" != "Y" ]; then
        exit 1
    fi
fi

# Step 3: Start backend microservices
echo "🔧 启动后端微服务..."
if [ "$1" = "--web-only" ]; then
    echo "   跳过后端微服务 (仅启动Web应用)"
else
    docker-compose up -d redis stt-service diarization-service api-service
    
    # Wait for API service to be ready
    wait_for_service "http://localhost:8000/health" "API Service"
fi

# Step 4: Start web application
echo "🌐 启动Web应用..."
if [ "$1" = "--docker-web" ]; then
    echo "   使用Docker启动Web应用..."
    docker-compose up -d web-app
    wait_for_service "http://localhost:3000/" "Web Application"
else
    echo "   使用Node.js启动Web应用..."
    echo "   请在另一个终端运行: cd ../web && npm run dev"
fi

echo ""
echo "🎉 Intrascribe环境启动完成！"
echo ""
echo "📊 服务状态检查:"
echo "  - Redis:          http://localhost:6379"
echo "  - STT Service:    http://localhost:8001/docs"
echo "  - Diarization:    http://localhost:8002/docs" 
echo "  - API Service:    http://localhost:8000/docs"
echo "  - Web App:        http://localhost:3000"
echo "  - Supabase API:   http://localhost:54321"
echo "  - Supabase Studio: http://localhost:54323"
echo ""
echo "🔧 管理命令:"
echo "  查看日志:     docker-compose logs -f"
echo "  停止服务:     docker-compose down"
echo "  重启服务:     docker-compose restart"
echo "  启动Agent:    docker-compose up --scale agent-service=1 -d"
