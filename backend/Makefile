# Intrascribe Microservices Makefile
# Commands for managing the microservices infrastructure

.PHONY: help build up down logs clean dev test health init agent agent-stop agent-scale status stats info quickstart

# Default target
help:
	@echo "Intrascribe Microservices Management"
	@echo ""
	@echo "Available commands:"
	@echo ""
	@echo "🚀 Quick Start:"
	@echo "  quickstart - Complete setup for new developers"
	@echo "  init      - Initialize development environment"
	@echo "  up        - Start all services"
	@echo "  health    - Check service health status"
	@echo ""
	@echo "🔧 Development:"
	@echo "  build     - Build all Docker images"
	@echo "  dev       - Start development environment (with rebuild)"
	@echo "  logs      - Show logs from all services"
	@echo "  stats     - Show resource usage statistics"
	@echo ""
	@echo "🎧 Agent Management:"
	@echo "  agent     - Start LiveKit agent manually"
	@echo "  agent-stop - Stop LiveKit agent"
	@echo "  agent-scale - Scale agent instances"
	@echo ""
	@echo "🛠️  Service Management:"
	@echo "  status    - Show service status"
	@echo "  restart-<service> - Restart specific service"
	@echo "  logs-<service> - Show logs for specific service"
	@echo "  update-<service> - Update and rebuild specific service"
	@echo ""
	@echo "🧹 Cleanup:"
	@echo "  down      - Stop all services"
	@echo "  clean     - Clean up containers and volumes"
	@echo ""
	@echo "📊 Monitoring:"
	@echo "  test      - Run health checks on all services"
	@echo "  info      - Show detailed service information"
	@echo ""

# Build all Docker images
build:
	@echo "🔨 Building Docker images..."
	docker-compose build

# Start all services
up:
	@echo "🚀 Starting all microservices..."
	docker-compose up -d --remove-orphans
	@echo "✅ All services started"
	@echo "📊 API Service: http://localhost:8000"
	@echo "🎙️  STT Service: http://localhost:8001"
	@echo "👥 Diarization Service: http://localhost:8002"

# Stop all services
down:
	@echo "🛑 Stopping all microservices..."
	docker-compose down
	@echo "✅ All services stopped"

# Show logs from all services
logs:
	docker-compose logs -f

# Show logs from specific service
logs-%:
	docker-compose logs -f $*

# Clean up containers and volumes
clean:
	@echo "🧹 Cleaning up containers and volumes..."
	docker-compose down -v --remove-orphans
	docker system prune -f
	@echo "✅ Cleanup completed"

# Start development environment (with rebuilding)
dev:
	@echo "🔧 Starting development environment..."
	docker-compose up -d --build
	@echo "✅ Development environment ready"

# Run health checks
test: health

# Check service health
health:
	@echo "🏥 Checking service health..."
	@echo ""
	@echo "📊 API Service (Port 8000):"
	@curl -s http://localhost:8000/health 2>/dev/null | python -m json.tool 2>/dev/null || echo "❌ API Service not responding"
	@echo ""
	@echo "🎙️  STT Service (Port 8001):"
	@curl -s http://localhost:8001/health 2>/dev/null | python -m json.tool 2>/dev/null || echo "❌ STT Service not responding"
	@echo ""
	@echo "👥 Diarization Service (Port 8002):"
	@curl -s http://localhost:8002/health 2>/dev/null | python -m json.tool 2>/dev/null || echo "❌ Diarization Service not responding"
	@echo ""
	@echo "💾 Redis Status:"
	@docker-compose exec redis redis-cli ping 2>/dev/null || echo "❌ Redis not responding"
	@echo ""

# Start Agent service manually
agent:
	@echo "🎧 Starting Agent service..."
	docker-compose up -d agent-service
	@echo "✅ Agent service started"

# Stop Agent service
agent-stop:
	@echo "🛑 Stopping Agent service..."
	docker-compose stop agent-service
	@echo "✅ Agent service stopped"

# Scale LiveKit agents
agent-scale:
	@echo "📈 Scaling LiveKit agents..."
	@read -p "Number of agent instances: " count; \
	docker-compose up -d --scale agent-service=$$count agent-service

# Show service status
status:
	@echo "📊 Service Status:"
	@docker-compose ps

# Restart specific service
restart-%:
	@echo "🔄 Restarting $* service..."
	docker-compose restart $*
	@echo "✅ $* service restarted"

# View service logs in real-time
tail-%:
	docker-compose logs -f --tail=100 $*

# Run a command in a service container
exec-%:
	@echo "💻 Entering $* container..."
	docker-compose exec $* bash

# Update and rebuild a specific service
update-%:
	@echo "🔄 Updating $* service..."
	docker-compose build $*
	docker-compose up -d $*
	@echo "✅ $* service updated"

# Initialize development environment
init:
	@echo "🏗️  Initializing development environment..."
	@if [ ! -f .env ]; then \
		echo "📝 Creating .env file from template..."; \
		if [ -f .env.example ]; then \
			cp .env.example .env; \
		else \
			echo "⚠️  .env.example not found, creating basic .env file"; \
			echo "# Please configure the following environment variables" > .env; \
			echo "SUPABASE_URL=http://127.0.0.1:54321" >> .env; \
			echo "SUPABASE_ANON_KEY=your-supabase-anon-key" >> .env; \
			echo "SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key" >> .env; \
			echo "LIVEKIT_API_URL=wss://your-livekit-instance.livekit.cloud" >> .env; \
			echo "LIVEKIT_API_KEY=your-livekit-api-key" >> .env; \
			echo "LIVEKIT_API_SECRET=your-livekit-api-secret" >> .env; \
			echo "HUGGINGFACE_TOKEN=hf_your-huggingface-token" >> .env; \
		fi; \
		echo "⚠️  Please edit .env file with your actual configuration"; \
	else \
		echo "✅ .env file already exists"; \
	fi
	@echo "🔨 Building images..."
	make build
	@echo "✅ Initialization completed"

# Show resource usage
stats:
	@echo "📊 Resource Usage Statistics:"
	@echo ""
	@docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}" || echo "❌ Failed to get stats"

# Show detailed service info
info:
	@echo "ℹ️  Service Information:"
	@echo ""
	@echo "📊 API Service Info:"
	@curl -s http://localhost:8000/info 2>/dev/null | python -m json.tool 2>/dev/null || echo "❌ API Service info not available"
	@echo ""
	@echo "🎙️  STT Service Info:"
	@curl -s http://localhost:8001/info 2>/dev/null | python -m json.tool 2>/dev/null || echo "❌ STT Service info not available"
	@echo ""
	@echo "👥 Diarization Service Info:"
	@curl -s http://localhost:8002/info 2>/dev/null | python -m json.tool 2>/dev/null || echo "❌ Diarization Service info not available"

# Quick setup for new developers
quickstart:
	@echo "🚀 Quick Start for New Developers:"
	@echo ""
	@echo "1. Initializing environment..."
	@make init
	@echo ""
	@echo "2. Starting all services..."
	@make up
	@echo ""
	@echo "3. Waiting for services to start..."
	@sleep 10
	@echo ""
	@echo "4. Checking health..."
	@make health
	@echo ""
	@echo "✅ Setup complete! Services available at:"
	@echo "   📊 API Service: http://localhost:8000/docs"
	@echo "   🎙️  STT Service: http://localhost:8001/docs"
	@echo "   👥 Diarization Service: http://localhost:8002/docs"
