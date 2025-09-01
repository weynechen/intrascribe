#!/bin/bash

# Intrascribe Local Development Environment Startup Script
# Author: Intrascribe Team
# Description: Automated script to check dependencies and start all services for local development

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
WEB_DIR="$SCRIPT_DIR/web"
LOG_DIR="$SCRIPT_DIR/logs"

# Create logs directory
mkdir -p "$LOG_DIR"

# PID storage for cleanup
PIDS=()

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_section() {
    echo -e "\n${PURPLE}==== $1 ====${NC}"
}

# Function to cleanup processes on exit
cleanup() {
    print_section "Cleaning up processes..."
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            print_status "Stopping process $pid"
            kill "$pid" 2>/dev/null || true
        fi
    done
    exit 0
}

# Trap signals to cleanup
trap cleanup SIGINT SIGTERM

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if port is in use
port_in_use() {
    lsof -i :"$1" >/dev/null 2>&1
}

# Function to wait for service to be ready
wait_for_service() {
    local url="$1"
    local service_name="$2"
    local max_attempts=30
    local attempt=0
    
    print_status "Waiting for $service_name to be ready..."
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s "$url" >/dev/null 2>&1; then
            print_success "$service_name is ready!"
            return 0
        fi
        
        ((attempt++))
        echo -n "."
        sleep 2
    done
    
    print_error "$service_name failed to start within $((max_attempts * 2)) seconds"
    return 1
}

# Function to check if services are already running
check_running_services() {
    print_section "Checking for Running Services"
    
    declare -A service_ports=(
        ["Web Application"]="3000"
        ["API Service"]="8000"
        ["STT Service"]="8001"
        ["Diarization Service"]="8002"
    )
    
    local running_services=()
    local running_pids=()
    
    for service in "${!service_ports[@]}"; do
        local port="${service_ports[$service]}"
        if port_in_use "$port"; then
            local pid=$(lsof -ti :"$port" 2>/dev/null | head -1)
            print_warning "$service is already running on port $port (PID: $pid)"
            running_services+=("$service")
            running_pids+=("$pid")
        fi
    done
    
    if [ ${#running_services[@]} -gt 0 ]; then
        print_warning "Found ${#running_services[@]} running service(s)"
        echo ""
        read -p "Do you want to stop these services and continue? (y/N): " stop_services
        if [[ "$stop_services" =~ ^[Yy]$ ]]; then
            for pid in "${running_pids[@]}"; do
                if kill -0 "$pid" 2>/dev/null; then
                    print_status "Stopping process $pid"
                    kill "$pid" 2>/dev/null || true
                    sleep 1
                fi
            done
            print_success "Stopped running services"
        else
            print_status "You can manually stop services with: kill <PID>"
            print_status "Or use the stop_services function below"
            exit 0
        fi
    else
        print_success "No conflicting services are running"
    fi
}

# Function to stop specific services
stop_services() {
    print_section "Stopping Services"
    
    declare -A service_ports=(
        ["web"]="3000"
        ["api"]="8000"
        ["stt"]="8001"
        ["diarization"]="8002"
        ["redis"]="6379"
    )
    
    if [ "$1" = "all" ]; then
        print_status "Stopping all services..."
        for service in "${!service_ports[@]}"; do
            local port="${service_ports[$service]}"
            if port_in_use "$port"; then
                local pid=$(lsof -ti :"$port" 2>/dev/null | head -1)
                if [ -n "$pid" ]; then
                    print_status "Stopping $service (PID: $pid)"
                    kill "$pid" 2>/dev/null || true
                fi
            fi
        done
        
        # Also kill any uv run processes
        pkill -f "uv run" 2>/dev/null || true
        
        # Stop Redis if it was started manually
        if [ -f "$LOG_DIR/redis.pid" ]; then
            local redis_pid=$(cat "$LOG_DIR/redis.pid" 2>/dev/null)
            if [ -n "$redis_pid" ] && kill -0 "$redis_pid" 2>/dev/null; then
                print_status "Stopping Redis (PID: $redis_pid)"
                kill "$redis_pid" 2>/dev/null || true
                rm -f "$LOG_DIR/redis.pid"
            fi
        fi
        
        print_success "All services stopped"
        return 0
    fi
    
    if [ -n "$1" ] && [ -n "${service_ports[$1]}" ]; then
        local port="${service_ports[$1]}"
        if port_in_use "$port"; then
            local pid=$(lsof -ti :"$port" 2>/dev/null | head -1)
            if [ -n "$pid" ]; then
                print_status "Stopping $1 service (PID: $pid)"
                kill "$pid" 2>/dev/null || true
                
                # Special handling for Redis
                if [ "$1" = "redis" ] && [ -f "$LOG_DIR/redis.pid" ]; then
                    rm -f "$LOG_DIR/redis.pid"
                fi
                
                print_success "$1 service stopped"
            else
                print_warning "$1 service is not running"
            fi
        else
            print_warning "$1 service is not running on port $port"
        fi
        return 0
    fi
    
    print_error "Usage: stop_services [all|web|api|stt|diarization|redis]"
    print_status "Available services: ${!service_ports[*]}"
}

# Function to show running services status
show_services_status() {
    print_section "Services Status"
    
    declare -A service_ports=(
        ["Web Application"]="3000"
        ["API Service"]="8000"
        ["STT Service"]="8001"
        ["Diarization Service"]="8002"
        ["Redis"]="6379"
    )
    
    for service in "${!service_ports[@]}"; do
        local port="${service_ports[$service]}"
        if port_in_use "$port"; then
            local pid=$(lsof -ti :"$port" 2>/dev/null | head -1)
            if [ "$service" = "Redis" ]; then
                # Special check for Redis connectivity
                if redis-cli ping >/dev/null 2>&1; then
                    print_success "$service: ✅ Running on port $port (PID: $pid) - Responding"
                else
                    print_warning "$service: ⚠️ Running on port $port (PID: $pid) - Not responding"
                fi
            else
                print_success "$service: ✅ Running on port $port (PID: $pid)"
            fi
        else
            print_error "$service: ❌ Not running"
        fi
    done
}

# Function to check Supabase
check_supabase() {
    print_section "Checking Supabase"
    
    # Check if supabase CLI is installed
    if ! command_exists supabase; then
        print_error "Supabase CLI is not installed!"
        print_status "Install it with: npm install -g supabase"
        print_status "Or follow: https://supabase.com/docs/guides/cli/getting-started"
        exit 1
    fi
    
    print_success "Supabase CLI is installed"
    
    # Check if Supabase is running
    if curl -s http://127.0.0.1:54321/health >/dev/null 2>&1; then
        print_success "Supabase is already running"
        return 0
    fi
    
    print_warning "Supabase is not running. Starting Supabase..."
    
    # Navigate to supabase directory and start
    cd "$SCRIPT_DIR/supabase"
    
    if supabase start; then
        print_success "Supabase started successfully"
        # Wait for Supabase to be fully ready
        wait_for_service "http://127.0.0.1:54321/health" "Supabase"
    else
        print_error "Failed to start Supabase"
        exit 1
    fi
    
    cd "$SCRIPT_DIR"
}

# Function to check Redis
check_redis() {
    print_section "Checking Redis"
    
    # Check if redis-server is installed
    if ! command_exists redis-server; then
        print_error "Redis server is not installed!"
        print_status "Install it with:"
        print_status "  Ubuntu/Debian: sudo apt install redis-server"
        print_status "  CentOS/RHEL: sudo yum install redis"
        print_status "  macOS: brew install redis"
        exit 1
    fi
    
    print_success "Redis server is installed"
    
    # Check if Redis is responding (more reliable than port check)
    if redis-cli ping >/dev/null 2>&1; then
        print_success "Redis is already running and responding"
        return 0
    fi
    
    # Check if Redis service is running via systemctl
    if command_exists systemctl; then
        if systemctl is-active --quiet redis-server 2>/dev/null; then
            print_success "Redis service is active"
            # Wait a moment and test connection again
            sleep 1
            if redis-cli ping >/dev/null 2>&1; then
                print_success "Redis is now responding to ping"
                return 0
            else
                print_warning "Redis service is running but not responding on default connection"
                print_status "This might be a configuration issue (binding address, port, etc.)"
                print_status "Continuing anyway - please check Redis configuration if needed"
                return 0
            fi
        elif systemctl is-active --quiet redis 2>/dev/null; then
            print_success "Redis service is active (alternative service name)"
            # Wait a moment and test connection again
            sleep 1
            if redis-cli ping >/dev/null 2>&1; then
                print_success "Redis is now responding to ping"
                return 0
            else
                print_warning "Redis service is running but not responding on default connection"
                print_status "This might be a configuration issue (binding address, port, etc.)"
                print_status "Continuing anyway - please check Redis configuration if needed"
                return 0
            fi
        fi
    fi
    
    # If not running, try to start it
    print_warning "Redis is not running. Starting Redis server..."
    
    # Try to start Redis server
    if command_exists systemctl; then
        # Using systemd
        if sudo systemctl start redis-server 2>/dev/null; then
            print_success "Redis started using systemctl (redis-server)"
            sleep 2
        elif sudo systemctl start redis 2>/dev/null; then
            print_success "Redis started using systemctl (redis)"
            sleep 2
        else
            print_warning "Failed to start Redis with systemctl, trying manual start..."
            redis-server --daemonize yes --logfile "$LOG_DIR/redis.log" --pidfile "$LOG_DIR/redis.pid"
            sleep 2
        fi
    else
        # Manual start
        redis-server --daemonize yes --logfile "$LOG_DIR/redis.log" --pidfile "$LOG_DIR/redis.pid"
        sleep 2
    fi
    
    # Final check
    if redis-cli ping >/dev/null 2>&1; then
        print_success "Redis is now running and responding to ping"
    else
        print_error "Failed to start Redis server or it's not responding"
        print_status "Please check Redis configuration and try starting manually:"
        print_status "  sudo systemctl start redis-server"
        print_status "  redis-cli ping"
        exit 1
    fi
}

# Function to check LiveKit Server
check_livekit() {
    print_section "Checking LiveKit Server"
    
    # Check if livekit-server is installed
    if ! command_exists livekit-server; then
        print_warning "LiveKit Server is not installed locally"
        print_status "You can either:"
        print_status "1. Install locally: https://docs.livekit.io/home/self-hosting/local/"
        print_status "2. Use LiveKit Cloud: https://cloud.livekit.io/"
        print_status "3. Skip this check if using external LiveKit service"
        
        read -p "Do you want to continue without local LiveKit server? (y/N): " continue_without_livekit
        if [[ ! "$continue_without_livekit" =~ ^[Yy]$ ]]; then
            exit 1
        fi
        return 0
    fi
    
    print_success "LiveKit Server is installed"
    
    # Check if LiveKit is running (default port 7880)
    if port_in_use 7880; then
        print_success "LiveKit Server is already running"
        return 0
    fi
    
    print_warning "LiveKit Server is not running. Starting LiveKit Server..."
    
    # Start LiveKit server in background
    livekit-server --dev >"$LOG_DIR/livekit.log" 2>&1 &
    local livekit_pid=$!
    PIDS+=("$livekit_pid")
    
    # Wait for LiveKit to be ready
    if wait_for_service "http://localhost:7880" "LiveKit Server"; then
        print_success "LiveKit Server started successfully (PID: $livekit_pid)"
    else
        print_error "Failed to start LiveKit Server"
        exit 1
    fi
}

# Function to check environment files
check_environment() {
    print_section "Checking Environment Configuration"
    
    # Check backend .env
    if [ ! -f "$BACKEND_DIR/.env" ]; then
        print_warning "Backend .env file not found"
        if [ -f "$BACKEND_DIR/.env.example" ]; then
            print_status "Copying .env.example to .env"
            cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
            print_warning "Please edit $BACKEND_DIR/.env with your actual configuration"
        else
            print_error "Neither .env nor .env.example found in backend directory"
            print_status "Please create $BACKEND_DIR/.env with required environment variables"
            exit 1
        fi
    else
        print_success "Backend .env file exists"
    fi
    
    # Check web .env.local
    if [ ! -f "$WEB_DIR/.env.local" ]; then
        print_warning "Web .env.local file not found"
        print_status "Creating basic .env.local file"
        cat > "$WEB_DIR/.env.local" << EOF
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-supabase-anon-key
NEXT_PUBLIC_LIVEKIT_URL=ws://localhost:7880
EOF
        print_warning "Please edit $WEB_DIR/.env.local with your actual configuration"
    else
        print_success "Web .env.local file exists"
    fi
}

# Function to start web application
start_web() {
    print_section "Starting Web Application"
    
    cd "$WEB_DIR"
    
    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        print_status "Installing web dependencies..."
        npm install
    fi
    
    print_status "Starting Next.js development server..."
    npm run dev >"$LOG_DIR/web.log" 2>&1 &
    local web_pid=$!
    PIDS+=("$web_pid")
    
    # Wait for web app to be ready
    if wait_for_service "http://localhost:3000" "Web Application"; then
        print_success "Web Application started successfully (PID: $web_pid)"
        print_status "Web app available at: ${CYAN}http://localhost:3000${NC}"
    else
        print_error "Failed to start Web Application"
        exit 1
    fi
    
    cd "$SCRIPT_DIR"
}

# Function to start basic microservices (STT and Diarization first)
start_basic_microservices() {
    print_section "Starting Basic Microservices"
    
    # Array of basic services (excluding API service)
    declare -A basic_services=(
        ["stt_service"]="8001"
        ["diarization_service"]="8002"
    )
    
    for service in "${!basic_services[@]}"; do
        local port="${basic_services[$service]}"
        local service_dir="$BACKEND_DIR/$service"
        
        if [ ! -d "$service_dir" ]; then
            print_warning "Service directory $service_dir not found, skipping..."
            continue
        fi
        
        print_status "Starting $service on port $port..."
        
        cd "$service_dir"
        
        # Check if uv is installed
        if ! command_exists uv; then
            print_error "uv is not installed! Please install it first."
            print_status "Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
            exit 1
        fi
        
        # Install/sync dependencies if needed
        if [ ! -f "uv.lock" ] || [ "pyproject.toml" -nt "uv.lock" ]; then
            print_status "Syncing dependencies for $service..."
            # Set HuggingFace mirror for dependency sync (especially for diarization service)
            if [ "$service" = "diarization_service" ]; then
                print_status "Setting HuggingFace mirror for faster model download..."
                export HF_ENDPOINT=https://hf-mirror.com
            fi
            uv sync
        fi
        
        # Start the service with appropriate environment variables
        if [ "$service" = "diarization_service" ]; then
            print_status "Setting HuggingFace mirror for Diarization service..."
            export HF_ENDPOINT=https://hf-mirror.com
            HF_ENDPOINT=https://hf-mirror.com uv run main.py >"$LOG_DIR/${service}.log" 2>&1 &
        else
            uv run main.py >"$LOG_DIR/${service}.log" 2>&1 &
        fi
        
        local service_pid=$!
        PIDS+=("$service_pid")
        
        print_success "$service started (PID: $service_pid)"
        
        # Wait for service to be ready
        local health_url="http://localhost:$port/health"
        if wait_for_service "$health_url" "$service"; then
            print_success "$service is healthy at port $port"
        else
            print_error "$service failed to start properly"
            exit 1
        fi
    done
    
    cd "$SCRIPT_DIR"
}

# Function to start API service (must be last)
start_api_service() {
    print_section "Starting API Service"
    
    local service="api_service"
    local port="8000"
    local service_dir="$BACKEND_DIR/$service"
    
    if [ ! -d "$service_dir" ]; then
        print_error "API Service directory $service_dir not found!"
        exit 1
    fi
    
    cd "$service_dir"
    
    print_status "Starting $service on port $port..."
    
    # Install/sync dependencies if needed
    if [ ! -f "uv.lock" ] || [ "pyproject.toml" -nt "uv.lock" ]; then
        print_status "Syncing dependencies for $service..."
        uv sync
    fi
    
    # Start the API service
    uv run main.py >"$LOG_DIR/${service}.log" 2>&1 &
    local service_pid=$!
    PIDS+=("$service_pid")
    
    print_success "$service started (PID: $service_pid)"
    
    # Wait for API service to be ready and validate other services
    local health_url="http://localhost:$port/health"
    if wait_for_service "$health_url" "$service"; then
        print_success "API Service is healthy and has validated other microservices"
    else
        print_error "API Service failed to start or validate other services"
        exit 1
    fi
    
    cd "$SCRIPT_DIR"
}

# Function to start LiveKit agent (required)
start_agent() {
    print_section "Starting LiveKit Agent"
    
    local agent_dir="$BACKEND_DIR/agent_service/transcribe_agent"
    
    if [ ! -d "$agent_dir" ]; then
        print_error "Agent service directory not found at $agent_dir"
        print_error "The LiveKit agent is required for real-time transcription"
        exit 1
    fi
    
    cd "$agent_dir"
    
    print_status "Starting LiveKit transcription agent..."
    
    # Install/sync dependencies if needed
    if [ ! -f "uv.lock" ] || [ "pyproject.toml" -nt "uv.lock" ]; then
        print_status "Syncing dependencies for agent..."
        # Ensure HuggingFace mirror is set for agent dependencies
        export HF_ENDPOINT=https://hf-mirror.com
        uv sync
    fi
    
    # Start the agent with HuggingFace mirror
    HF_ENDPOINT=https://hf-mirror.com uv run agent.py dev >"$LOG_DIR/agent.log" 2>&1 &
    local agent_pid=$!
    PIDS+=("$agent_pid")
    
    print_success "LiveKit Agent started (PID: $agent_pid)"
    
    # Wait for agent to be ready
    sleep 3
    if kill -0 "$agent_pid" 2>/dev/null; then
        print_success "LiveKit Agent is running successfully"
    else
        print_error "LiveKit Agent failed to start properly"
        print_error "Check the log file: $LOG_DIR/agent.log"
        exit 1
    fi
    
    cd "$SCRIPT_DIR"
}

# Function to display summary
display_summary() {
    print_section "Development Environment Ready!"
    
    echo -e "${GREEN}🎉 All services are running!${NC}\n"
    
    echo -e "${CYAN}📊 Service URLs:${NC}"
    echo -e "  • Web Application:     ${YELLOW}http://localhost:3000${NC}"
    echo -e "  • API Service:         ${YELLOW}http://localhost:8000/docs${NC}"
    echo -e "  • STT Service:         ${YELLOW}http://localhost:8001/docs${NC}"
    echo -e "  • Diarization Service: ${YELLOW}http://localhost:8002/docs${NC}"
    echo -e "  • Supabase Studio:     ${YELLOW}http://127.0.0.1:54323${NC}"
    echo ""
    
    echo -e "${CYAN}📝 Log Files:${NC}"
    echo -e "  • Web:          $LOG_DIR/web.log"
    echo -e "  • API Service:  $LOG_DIR/api_service.log"
    echo -e "  • STT Service:  $LOG_DIR/stt_service.log"
    echo -e "  • Diarization:  $LOG_DIR/diarization_service.log"
    echo -e "  • LiveKit Agent: $LOG_DIR/agent.log"
    if [ -f "$LOG_DIR/redis.log" ]; then
        echo -e "  • Redis:        $LOG_DIR/redis.log"
    fi
    if [ -f "$LOG_DIR/livekit.log" ]; then
        echo -e "  • LiveKit:      $LOG_DIR/livekit.log"
    fi
    echo ""
    
    echo -e "${YELLOW}⚡ Development Tips:${NC}"
    echo -e "  • Use ${CYAN}Ctrl+C${NC} to stop all services"
    echo -e "  • Check logs with: ${CYAN}tail -f $LOG_DIR/<service>.log${NC}"
    echo -e "  • Show status: ${CYAN}./start-dev.sh status${NC}"
    echo -e "  • Stop services: ${CYAN}./start-dev.sh stop [service]${NC}"
    echo -e "  • Edit .env files to configure services"
    echo ""
    
    echo -e "${GREEN}Happy coding! 🚀${NC}"
}

# Main execution
main() {
    clear
    echo -e "${PURPLE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                  Intrascribe Development Environment         ║"
    echo "║                     Local Startup Script                    ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}\n"
    
    # Check prerequisites
    check_environment
    check_supabase
    check_redis
    check_livekit
    
    # Set HuggingFace mirror for Chinese users (improves model download speed)
    print_status "Setting HuggingFace mirror for faster model downloads..."
    export HF_ENDPOINT=https://hf-mirror.com
    
    # Check for running services before starting
    check_running_services
    
    # Start services in correct order
    start_web
    start_basic_microservices  # STT and Diarization first
    start_agent               # Agent needs basic services
    start_api_service        # API service last (validates others)
    
    # Display summary
    display_summary
    
    # Keep script running
    print_status "Press Ctrl+C to stop all services and exit"
    
    # Wait for user interrupt
    while true; do
        sleep 1
    done
}

# Handle command line arguments
case "${1:-}" in
    "stop")
        stop_services "${2:-all}"
        exit 0
        ;;
    "status")
        show_services_status
        exit 0
        ;;
    "help"|"-h"|"--help")
        echo "Intrascribe Development Environment Manager"
        echo ""
        echo "Usage:"
        echo "  ./start-dev.sh          Start all services"
        echo "  ./start-dev.sh stop     Stop all services"
        echo "  ./start-dev.sh stop <service>  Stop specific service"
        echo "  ./start-dev.sh status   Show services status"
        echo ""
        echo "Available services for stop: web, api, stt, diarization, redis"
        echo ""
        exit 0
        ;;
    "")
        # Default behavior - start services
        ;;
    *)
        echo "Unknown command: $1"
        echo "Use './start-dev.sh help' for usage information"
        exit 1
        ;;
esac

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
