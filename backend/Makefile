# Intrascribe Microservices Makefile
# Commands for managing the microservices infrastructure

.PHONY: help build up down logs clean dev test health

# Default target
help:
	@echo "Intrascribe Microservices Management"
	@echo ""
	@echo "Available commands:"
	@echo "  build     - Build all Docker images"
	@echo "  up        - Start all services"
	@echo "  down      - Stop all services"
	@echo "  logs      - Show logs from all services"
	@echo "  clean     - Clean up containers and volumes"
	@echo "  dev       - Start development environment"
	@echo "  test      - Run health checks on all services"
	@echo "  health    - Check service health status"
	@echo "  agent     - Start LiveKit agent manually"
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
	@echo "API Service:"
	@curl -s http://localhost:8000/health | python -m json.tool || echo "❌ API Service not responding"
	@echo ""
	@echo "STT Service:"
	@curl -s http://localhost:8001/health | python -m json.tool || echo "❌ STT Service not responding"
	@echo ""
	@echo "Diarization Service:"
	@curl -s http://localhost:8002/health | python -m json.tool || echo "❌ Diarization Service not responding"
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
		cp .env.example .env; \
		echo "⚠️  Please edit .env file with your configuration"; \
	fi
	@echo "🔨 Building images..."
	make build
	@echo "✅ Initialization completed"

# Show resource usage
stats:
	docker stats --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"
