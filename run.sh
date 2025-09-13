#!/bin/bash

# Intrascribe LAN HTTPS Deployment Script
# Supports local development and LAN access with HTTPS reverse proxy
# Author: Intrascribe Team

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
NGINX_CONFIG_DIR="/etc/nginx/sites-available"
NGINX_ENABLED_DIR="/etc/nginx/sites-enabled"
CERTS_DIR="$SCRIPT_DIR/certs"

# Get primary network interface IP
get_local_ip() {
    local ip=$(ip route get 1.1.1.1 | awk '{print $7; exit}' 2>/dev/null)
    if [[ -z "$ip" ]]; then
        # Fallback method
        ip=$(hostname -I | awk '{print $1}' 2>/dev/null)
    fi
    if [[ -z "$ip" ]]; then
        # Another fallback
        ip=$(ifconfig | grep 'inet ' | grep -v '127.0.0.1' | head -1 | awk '{print $2}' | cut -d: -f2 2>/dev/null)
    fi
    echo "$ip"
}

LOCAL_IP=$(get_local_ip)
# 去掉域名，直接使用IP访问
DOMAIN_NAME="$LOCAL_IP"

# Service Ports
declare -A SERVICE_PORTS=(
    ["web"]="3000"
    ["api"]="8000"
    ["stt"]="8001"
    ["diarization"]="8002"
    ["redis"]="6379"
    ["livekit"]="7880"
    ["supabase_api"]="54321"
    ["supabase_studio"]="54323"
)

# HTTPS Ports for nginx proxy
HTTPS_PORT=443
HTTP_PORT=80

# PID storage for cleanup
PIDS=()

# Create directories
mkdir -p "$LOG_DIR"
mkdir -p "$CERTS_DIR"

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
    
    # Clean up nginx config if we created it
    if [[ -f "/etc/nginx/sites-enabled/intrascribe.conf" ]]; then
        print_status "Removing nginx configuration..."
        sudo rm -f "/etc/nginx/sites-enabled/intrascribe.conf" 2>/dev/null || true
        sudo nginx -s reload 2>/dev/null || true
    fi
    
    print_success "Cleanup completed"
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

# Check dependencies
check_dependencies() {
    print_section "Checking Dependencies"
    
    local missing_deps=()
    
    # Check NVIDIA GPU and CUDA
    if command_exists nvidia-smi; then
        local cuda_version=$(nvidia-smi | grep "CUDA Version" | awk '{print $9}' | head -1)
        if [[ -n "$cuda_version" ]]; then
            print_success "NVIDIA GPU detected with CUDA $cuda_version"
        else
            print_warning "NVIDIA GPU detected but CUDA version unclear"
        fi
    else
        print_warning "NVIDIA GPU/CUDA not detected (will use CPU mode)"
    fi
    
    # Check Node.js
    if command_exists node; then
        local node_version=$(node --version)
        local major_version=$(echo "$node_version" | cut -d'.' -f1 | sed 's/v//')
        if [[ $major_version -ge 18 ]]; then
            print_success "Node.js $node_version (OK)"
        else
            print_error "Node.js version $node_version is too old (need 18+)"
            missing_deps+=("nodejs")
        fi
    else
        print_error "Node.js not found"
        missing_deps+=("nodejs")
    fi
    
    # Check Python 3.12
    if command_exists python3.12; then
        local python_version=$(python3.12 --version)
        print_success "Python $python_version"
    elif command_exists python3; then
        local python_version=$(python3 --version | awk '{print $2}')
        local major=$(echo "$python_version" | cut -d'.' -f1)
        local minor=$(echo "$python_version" | cut -d'.' -f2)
        if [[ $major -eq 3 && $minor -ge 12 ]]; then
            print_success "Python $python_version (OK)"
        else
            print_error "Python version $python_version is too old (need 3.12+)"
            missing_deps+=("python3.12")
        fi
    else
        print_error "Python 3.12+ not found"
        missing_deps+=("python3.12")
    fi
    
    # Check uv
    if command_exists uv; then
        local uv_version=$(uv --version)
        print_success "uv $uv_version"
    else
        print_error "uv not found"
        missing_deps+=("uv")
    fi
    
    # Check ollama
    if command_exists ollama; then
        print_success "ollama is installed"
        # Check if qwen2.5:8b model is available
        if ollama list | grep -q "qwen2.5:8b\|qwen3:8b"; then
            print_success "qwen model is available"
        else
            print_warning "qwen model not found. You may need to run: ollama pull qwen2.5:8b , or change ai_config.yaml to use other model"
        fi
    else
        print_error "ollama not found"
        missing_deps+=("ollama")
    fi
    
    # Check FFmpeg
    if command_exists ffmpeg; then
        local ffmpeg_version=$(ffmpeg -version | head -1 | awk '{print $3}')
        print_success "FFmpeg $ffmpeg_version"
    else
        print_error "FFmpeg not found"
        missing_deps+=("ffmpeg")
    fi
    
    # Check supabase CLI
    if command_exists supabase; then
        local supabase_version=$(supabase --version)
        print_success "Supabase CLI $supabase_version"
    else
        print_error "Supabase CLI not found"
        missing_deps+=("supabase")
    fi
    
    # Check livekit-server
    if command_exists livekit-server; then
        print_success "LiveKit server is installed"
    else
        print_error "livekit-server not found"
        missing_deps+=("livekit-server")
    fi
    
    # Check redis-server
    if command_exists redis-server; then
        print_success "Redis server is installed"
    else
        print_error "Redis server not found"
        missing_deps+=("redis-server")
    fi
    
    # Check nginx
    if command_exists nginx; then
        local nginx_version=$(nginx -v 2>&1 | cut -d' ' -f3)
        print_success "Nginx $nginx_version"
    else
        print_error "Nginx not found"
        missing_deps+=("nginx")
    fi
    
    
    # Report missing dependencies
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        print_error "Missing dependencies found!"
        echo ""
        print_status "Installation instructions:"
        
        for dep in "${missing_deps[@]}"; do
            case "$dep" in
                "nodejs")
                    echo "  • Node.js 18+: https://nodejs.org/ or use nvm"
                    echo "    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash"
                    echo "    nvm install 18"
                    ;;
                "python3.12")
                    echo "  • Python 3.12: sudo apt install python3.12 python3.12-venv"
                    ;;
                "uv")
                    echo "  • uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
                    ;;
                "ollama")
                    echo "  • ollama: curl -fsSL https://ollama.com/install.sh | sh"
                    echo "    ollama pull qwen2.5:8b"
                    ;;
                "ffmpeg")
                    echo "  • FFmpeg: sudo apt install ffmpeg"
                    ;;
                "supabase")
                    echo "  • Supabase CLI: npm install supabase --save-dev"
                    echo "    Or download from: https://github.com/supabase/cli/releases"
                    ;;
                "redis-server")
                    echo "  • Redis: sudo apt install redis-server"
                    ;;
                "nginx")
                    echo "  • Nginx: sudo apt install nginx"
                    ;;
                "livekit-server")
                    echo "  • LiveKit Server: curl -sSL https://get.livekit.io | bash"
                    ;;
            esac
        done
        
        echo ""
        print_error "Please install missing dependencies and run again."
        exit 1
    fi
    
    print_success "All dependencies are installed!"
}

# Generate SSL certificates
generate_ssl_certs() {
    print_section "Setting up SSL Certificates"
    
    local cert_file="$CERTS_DIR/intrascribe.crt"
    local key_file="$CERTS_DIR/intrascribe.key"
    
    if [[ -f "$cert_file" && -f "$key_file" ]]; then
        print_success "SSL certificates already exist"
        return 0
    fi
    
    print_status "Generating self-signed SSL certificate..."
    
    # Create certificate configuration
    cat > "$CERTS_DIR/cert.conf" << EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = v3_req

[dn]
C=CN
ST=Local
L=Local
O=Intrascribe
OU=Development
CN=$DOMAIN_NAME

[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = $DOMAIN_NAME
DNS.2 = localhost
IP.1 = 127.0.0.1
IP.2 = $LOCAL_IP
EOF
    
    # Generate certificate
    openssl req -new -x509 -days 365 -nodes \
        -out "$cert_file" \
        -keyout "$key_file" \
        -config "$CERTS_DIR/cert.conf" \
        -extensions v3_req
    
    if [[ $? -eq 0 ]]; then
        print_success "SSL certificate generated successfully"
        print_status "Certificate: $cert_file"
        print_status "Private key: $key_file"
    else
        print_error "Failed to generate SSL certificate"
        exit 1
    fi
}

# Create nginx configuration
create_nginx_config() {
    print_section "Setting up Nginx HTTPS Reverse Proxy"
    
    local config_file="/etc/nginx/sites-available/intrascribe.conf"
    
    print_status "Creating nginx configuration..."
    
    sudo tee "$config_file" > /dev/null << EOF
# Intrascribe HTTPS Reverse Proxy Configuration
# Generated by run.sh script

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name $LOCAL_IP;
    return 301 https://\$server_name\$request_uri;
}

# Main HTTPS server block
server {
    listen 443 ssl http2;
    server_name $LOCAL_IP;
    
    # SSL Configuration
    ssl_certificate $CERTS_DIR/intrascribe.crt;
    ssl_certificate_key $CERTS_DIR/intrascribe.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    # Client max body size for file uploads
    client_max_body_size 100M;
    
    # Web Application (Default)
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 86400;
    }
    
    # API Service
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 75;
        proxy_send_timeout 300;
    }
    
    # API Documentation
    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Health checks
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
    }
    
    # STT Service
    location /stt/ {
        proxy_pass http://127.0.0.1:8001/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
    }
    
    # Diarization Service
    location /diarization/ {
        proxy_pass http://127.0.0.1:8002/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 600;  # Longer timeout for model processing
    }
    
    # Supabase API
    location /supabase/ {
        proxy_pass http://127.0.0.1:54321/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Handle Supabase realtime connections
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
    
    # Supabase Studio
    location /studio/ {
        proxy_pass http://127.0.0.1:54323/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# LiveKit WebRTC Server (separate server block for WebSocket support)
server {
    listen 7443 ssl http2;
    server_name $LOCAL_IP;
    
    # SSL Configuration (same as main server)
    ssl_certificate $CERTS_DIR/intrascribe.crt;
    ssl_certificate_key $CERTS_DIR/intrascribe.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    location / {
        proxy_pass http://127.0.0.1:7880;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        proxy_connect_timeout 86400;
    }
}
EOF
    
    # Enable the site
    sudo ln -sf "$config_file" "/etc/nginx/sites-enabled/intrascribe.conf"
    
    # Test nginx configuration
    if sudo nginx -t; then
        print_success "Nginx configuration is valid"
        sudo systemctl reload nginx
        print_success "Nginx reloaded successfully"
    else
        print_error "Nginx configuration test failed"
        exit 1
    fi
}

# Auto-update environment configuration for LAN access
auto_update_env_urls() {
    local env_file="$1"
    local file_type="$2"  # "backend" or "web"
    local updated=false
    
    if [[ ! -f "$env_file" ]]; then
        return 1
    fi
    
    print_status "Auto-updating URLs in $file_type environment file..."
    
    # update backend .env file
    if [[ "$file_type" == "backend" ]]; then
        # Backend .env file updates - 确保所有必要的URL都存在且正确配置
        
        # 1. SUPABASE_URL - 后端内部访问用localhost
        if ! grep -q "^SUPABASE_URL=" "$env_file"; then
            echo "SUPABASE_URL=http://localhost:54321" >> "$env_file"
            updated=true
        elif ! grep -q "SUPABASE_URL=http://localhost:54321" "$env_file"; then
            sed -i "s|SUPABASE_URL=.*|SUPABASE_URL=http://localhost:54321|g" "$env_file"
            updated=true
        fi
        
        # 2. LIVEKIT_API_URL - 返回给前端的地址，使用局域网IP
        if ! grep -q "^LIVEKIT_API_URL=" "$env_file"; then
            echo "LIVEKIT_API_URL=wss://$LOCAL_IP:7443" >> "$env_file"
            updated=true
        elif ! grep -q "LIVEKIT_API_URL=wss://$LOCAL_IP:7443" "$env_file"; then
            sed -i "s|LIVEKIT_API_URL=.*|LIVEKIT_API_URL=wss://$LOCAL_IP:7443|g" "$env_file"
            updated=true
        fi
        
        # 3. REDIS_URL - 内部服务
        if ! grep -q "^REDIS_URL=" "$env_file"; then
            echo "REDIS_URL=redis://localhost:6379" >> "$env_file"
            updated=true
        elif ! grep -q "REDIS_URL=redis://localhost:6379" "$env_file"; then
            sed -i "s|REDIS_URL=.*|REDIS_URL=redis://localhost:6379|g" "$env_file"
            updated=true
        fi
        
        # 4. API_SERVICE_URL - 微服务间通信
        if ! grep -q "^API_SERVICE_URL=" "$env_file"; then
            echo "API_SERVICE_URL=http://localhost:8000" >> "$env_file"
            updated=true
        elif ! grep -q "API_SERVICE_URL=http://localhost:8000" "$env_file"; then
            sed -i "s|API_SERVICE_URL=.*|API_SERVICE_URL=http://localhost:8000|g" "$env_file"
            updated=true
        fi
        
        # 5. STT_SERVICE_URL - 微服务间通信
        if ! grep -q "^STT_SERVICE_URL=" "$env_file"; then
            echo "STT_SERVICE_URL=http://localhost:8001" >> "$env_file"
            updated=true
        fi
        
        # 6. DIARIZATION_SERVICE_URL - 微服务间通信
        if ! grep -q "^DIARIZATION_SERVICE_URL=" "$env_file"; then
            echo "DIARIZATION_SERVICE_URL=http://localhost:8002" >> "$env_file"
            updated=true
        fi
        
    elif [[ "$file_type" == "web" ]]; then
        # Web .env.local file updates - 确保所有必要的URL都存在且正确配置
        
        # 1. NEXT_PUBLIC_SUPABASE_URL - 使用nginx反向代理
        if ! grep -q "^NEXT_PUBLIC_SUPABASE_URL=" "$env_file"; then
            echo "NEXT_PUBLIC_SUPABASE_URL=https://$LOCAL_IP/supabase" >> "$env_file"
            updated=true
        elif ! grep -q "NEXT_PUBLIC_SUPABASE_URL=https://$LOCAL_IP/supabase" "$env_file"; then
            sed -i "s|NEXT_PUBLIC_SUPABASE_URL=.*|NEXT_PUBLIC_SUPABASE_URL=https://$LOCAL_IP/supabase|g" "$env_file"
            updated=true
        fi
        
        # 2. NEXT_PUBLIC_LIVEKIT_URL - 直连LiveKit（不走nginx代理）
        if ! grep -q "^NEXT_PUBLIC_LIVEKIT_URL=" "$env_file"; then
            echo "NEXT_PUBLIC_LIVEKIT_URL=wss://$LOCAL_IP:7443" >> "$env_file"
            updated=true
        elif ! grep -q "NEXT_PUBLIC_LIVEKIT_URL=wss://$LOCAL_IP:7443" "$env_file"; then
            sed -i "s|NEXT_PUBLIC_LIVEKIT_URL=.*|NEXT_PUBLIC_LIVEKIT_URL=wss://$LOCAL_IP:7443|g" "$env_file"
            updated=true
        fi
        
        # 3. NEXT_PUBLIC_API_URL - 使用nginx反向代理
        if ! grep -q "^NEXT_PUBLIC_API_URL=" "$env_file"; then
            echo "NEXT_PUBLIC_API_URL=https://$LOCAL_IP/api" >> "$env_file"
            updated=true
        elif ! grep -q "NEXT_PUBLIC_API_URL=https://$LOCAL_IP/api" "$env_file"; then
            sed -i "s|NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=https://$LOCAL_IP/api|g" "$env_file"
            updated=true
        fi
        
        # 清理遗留的错误配置项
        if grep -q "^LIVEKIT_URL=" "$env_file"; then
            sed -i "/^LIVEKIT_URL=/d" "$env_file"
            updated=true
        fi
        
        if grep -q "^LIVEKIT_API_KEY=" "$env_file"; then
            sed -i "/^LIVEKIT_API_KEY=/d" "$env_file"
            updated=true
        fi
        
        if grep -q "^LIVEKIT_API_SECRET=" "$env_file"; then
            sed -i "/^LIVEKIT_API_SECRET=/d" "$env_file"
            updated=true
        fi
    fi
    
    if [[ "$updated" == "true" ]]; then
        print_success "Updated $file_type environment URLs for LAN access"
        return 0
    else
        print_status "$file_type environment URLs already configured correctly"
        return 1
    fi
}

# Check environment files and validate configuration
setup_environment() {
    print_section "Checking Environment Configuration"
    
    local backend_env="$BACKEND_DIR/.env"
    local web_env="$WEB_DIR/.env.local"
    local has_errors=false
    
    # 1. Check if environment files exist
    print_status "Checking environment files..."
    
    if [[ ! -f "$backend_env" ]]; then
        print_error "Backend environment file not found: $backend_env"
        if [[ -f "$BACKEND_DIR/.env.example" ]]; then
            print_status "Please run: cp $BACKEND_DIR/.env.example $backend_env"
        else
            print_error "No .env.example template found in backend directory"
        fi
        has_errors=true
    fi
    
    if [[ ! -f "$web_env" ]]; then
        print_error "Web environment file not found: $web_env"
        if [[ -f "$WEB_DIR/.env.local.example" ]]; then
            print_status "Please run: cp $WEB_DIR/.env.local.example $web_env"
        else
            print_error "No .env.local.example template found in web directory"
        fi
        has_errors=true
    fi
    
    if [[ "$has_errors" == "true" ]]; then
        echo ""
        print_error "Environment files missing! Please create them first:"
        echo ""
        print_status "1. Copy template files:"
        [[ -f "$BACKEND_DIR/.env.example" ]] && echo "   cp backend/.env.example backend/.env"
        [[ -f "$WEB_DIR/.env.local.example" ]] && echo "   cp web/.env.local.example web/.env.local"
        echo ""
        print_status "2. Configure the following keys:"
        echo "   • Supabase keys (run: cd supabase && supabase start -x edge-runtime)"
        echo "   • HuggingFace token (get from: https://huggingface.co/settings/tokens)"
        echo "   • LiveKit keys (devkey/secret for local, or real keys for production)"
        echo ""
        print_status "3. Then run this script again"
        exit 1
    fi
    
    print_success "Environment files exist"
    
    # 2. Validate critical keys
    print_status "Validating API keys and secrets..."
    
    local invalid_keys=()
    
    # Check backend keys
    if grep -q "your-supabase-service-role-key\|your-supabase-anon-key" "$backend_env"; then
        invalid_keys+=("Supabase keys in backend/.env")
    fi
    
    if grep -q "your-huggingface-token" "$backend_env"; then
        invalid_keys+=("HuggingFace token in backend/.env")
    fi
    
    # Check web keys  
    if [[ -f "$web_env" ]] && grep -q "your-supabase-anon-key" "$web_env"; then
        invalid_keys+=("Supabase anon key in web/.env.local")
    fi
    
    # Check for missing critical keys
    if ! grep -q "SUPABASE_SERVICE_ROLE_KEY=" "$backend_env"; then
        invalid_keys+=("Missing SUPABASE_SERVICE_ROLE_KEY in backend/.env")
    fi
    
    if ! grep -q "SUPABASE_ANON_KEY=" "$backend_env"; then
        invalid_keys+=("Missing SUPABASE_ANON_KEY in backend/.env")
    fi
    
    if [[ ${#invalid_keys[@]} -gt 0 ]]; then
        echo ""
        print_error "Invalid or missing API keys found:"
        for key in "${invalid_keys[@]}"; do
            echo -e "  ❌ $key"
        done
        echo ""
        print_status "🔧 How to get valid keys:"
        echo ""
        print_status "📊 Supabase keys:"
        echo "   1. cd supabase && supabase start -x edge-runtime"
        echo "   2. Copy the anon key and service_role key from output"
        echo "   3. Update SUPABASE_ANON_KEY and SUPABASE_SERVICE_ROLE_KEY"
        echo ""
        print_status "🤗 HuggingFace token:"
        echo "   1. Visit: https://huggingface.co/settings/tokens"
        echo "   2. Create a new token with read access"
        echo "   3. Update HUGGINGFACE_TOKEN in backend/.env"
        echo ""
        print_status "🎧 LiveKit keys (optional):"
        echo "   • For local testing: use devkey/secret (already in examples)"
        echo "   • For production: real keys you set livekit"
        echo ""
        print_error "Please configure valid keys and run the script again."
        exit 1
    fi
    
    print_success "All required API keys are configured"
    
    # 3. Auto-update URLs for LAN access
    print_status "Updating URLs for LAN access..."
    
    local needs_restart=false
    
    # Update backend URLs (internal services use localhost)
    if auto_update_env_urls "$backend_env" "backend"; then
        needs_restart=true
    fi
    
    # Update web URLs (browser access uses LAN IP)
    if auto_update_env_urls "$web_env" "web"; then
        needs_restart=true
    fi
    
    # 4. Display current configuration
    print_status "Current LAN configuration:"
    echo -e "  • Local IP: ${CYAN}$LOCAL_IP${NC}"
    echo -e "  • Backend Supabase: ${YELLOW}$(grep "SUPABASE_URL" "$backend_env" | cut -d'=' -f2)${NC} (internal)"
    echo -e "  • Backend LiveKit: ${YELLOW}$(grep "LIVEKIT_API_URL" "$backend_env" | cut -d'=' -f2)${NC} (returned to frontend)"
    echo -e "  • Frontend Supabase: ${YELLOW}$(grep "NEXT_PUBLIC_SUPABASE_URL" "$web_env" | cut -d'=' -f2)${NC} (browser access)"
    echo -e "  • Frontend LiveKit: ${YELLOW}$(grep "NEXT_PUBLIC_LIVEKIT_URL" "$web_env" | cut -d'=' -f2)${NC} (WebRTC)"
    echo -e "  • Frontend API: ${YELLOW}$(grep "NEXT_PUBLIC_API_URL" "$web_env" | cut -d'=' -f2 2>/dev/null || echo "Not set")${NC} (browser access)"
    
    if [[ "$needs_restart" == "true" ]]; then
        print_success "Environment URLs updated for LAN access"
    else
        print_success "Environment configuration is ready for LAN access"
    fi
}

# Wait for service to be ready
wait_for_service() {
    local url="$1"
    local service_name="$2"
    local max_attempts=300
    local attempt=0
    
    print_status "Waiting for $service_name to be ready..."
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s -k "$url" >/dev/null 2>&1; then
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

# Display access information
display_access_info() {
    print_section "🎉 Intrascribe is Ready for LAN Access!"
    
    echo ""
    echo -e "${GREEN}📍 Access URLs (HTTPS):${NC}"
    echo -e "  • Main Application:    ${CYAN}https://$LOCAL_IP${NC}"
    echo -e "  • API Documentation:   ${CYAN}https://$LOCAL_IP/docs${NC}"
    echo -e "  • Supabase Studio:     ${CYAN}https://$LOCAL_IP/studio${NC}"
    echo -e "  • Health Check:        ${CYAN}https://$LOCAL_IP/health${NC}"
    echo ""
    
    echo -e "${GREEN}🌐 LAN Access:${NC}"
    echo -e "  • Local IP: ${YELLOW}$LOCAL_IP${NC}"
    echo -e "  • Domain: ${YELLOW}$DOMAIN_NAME${NC}"
    echo ""
    
    echo -e "${BLUE}💡 Client Setup Instructions:${NC}"
    echo -e "  1. Add to client hosts file: ${YELLOW}$LOCAL_IP $DOMAIN_NAME${NC}"
    echo -e "     • Linux/Mac: sudo echo '$LOCAL_IP $DOMAIN_NAME' >> /etc/hosts"
    echo -e "     • Windows: Add '$LOCAL_IP $DOMAIN_NAME' to C:\\Windows\\System32\\drivers\\etc\\hosts"
    echo -e "  2. Accept the self-signed certificate in your browser"
    echo -e "  3. Access: ${CYAN}https://$DOMAIN_NAME${NC}"
    echo ""
    
    echo -e "${YELLOW}🔒 Security Notes:${NC}"
    echo -e "  • Using self-signed SSL certificate"
    echo -e "  • Browsers will show security warning (click 'Advanced' → 'Proceed')"
    echo -e "  • Certificate valid for: $DOMAIN_NAME, localhost, $LOCAL_IP"
    echo ""
    
    echo -e "${CYAN}📝 Log Files:${NC}"
    echo -e "  • Web:          $LOG_DIR/web.log"
    echo -e "  • API Service:  $LOG_DIR/api_service.log"
    echo -e "  • STT Service:  $LOG_DIR/stt_service.log"
    echo -e "  • Diarization:  $LOG_DIR/diarization_service.log"
    echo -e "  • LiveKit:      $LOG_DIR/livekit.log"
    echo -e "  • Agent:        $LOG_DIR/agent.log"
    echo ""
    
    echo -e "${PURPLE}⚡ Management:${NC}"
    echo -e "  • Stop all: ${CYAN}Ctrl+C${NC}"
    echo -e "  • View logs: ${CYAN}tail -f $LOG_DIR/<service>.log${NC}"
    echo -e "  • Nginx config: ${CYAN}/etc/nginx/sites-available/intrascribe.conf${NC}"
    echo ""
    
    echo -e "${GREEN}Happy coding! 🚀${NC}"
}

# Start services functions (based on start-dev.sh but modified for LAN access)

# Check Supabase
check_supabase() {
    print_section "Checking Supabase"
    
    # Check if Supabase is running
    if curl -s http://127.0.0.1:54321/health >/dev/null 2>&1; then
        print_success "Supabase is already running"
        return 0
    fi
    
    print_warning "Supabase is not running. Starting Supabase..."
    
    # Navigate to supabase directory and start
    cd "$SCRIPT_DIR/supabase"
    
    if supabase start -x edge-runtime; then
        print_success "Supabase started successfully"
        wait_for_service "http://127.0.0.1:54321/health" "Supabase"
    else
        print_error "Failed to start Supabase"
        exit 1
    fi
    
    cd "$SCRIPT_DIR"
}

# Check Redis
check_redis() {
    print_section "Checking Redis"
    
    # Check if Redis is responding
    if redis-cli ping >/dev/null 2>&1; then
        print_success "Redis is already running and responding"
        return 0
    fi
    
    # Try to start Redis service
    print_warning "Redis is not running. Starting Redis server..."
    
    if command_exists systemctl; then
        if sudo systemctl start redis-server 2>/dev/null; then
            print_success "Redis started using systemctl"
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
        redis-server --daemonize yes --logfile "$LOG_DIR/redis.log" --pidfile "$LOG_DIR/redis.pid"
        sleep 2
    fi
    
    # Final check
    if redis-cli ping >/dev/null 2>&1; then
        print_success "Redis is now running and responding"
    else
        print_error "Failed to start Redis server"
        exit 1
    fi
}

# Check/Start LiveKit Server
check_livekit() {
    print_section "Checking LiveKit Server"
    
    if ! command_exists livekit-server; then
        print_warning "LiveKit Server not installed locally"
        print_status "Make sure to configure LIVEKIT_API_URL to use LiveKit Cloud"
        return 0
    fi
    
    # Check if LiveKit is running
    if port_in_use 7880; then
        print_success "LiveKit Server is already running"
        return 0
    fi
    
    print_status "LiveKit Server is not running. Starting LiveKit Server..."
    
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

# Start web application
start_web() {
    print_section "Starting Web Application"
    
    cd "$WEB_DIR"
    
    # # Always install/update dependencies to avoid timeout issues
    # print_status "Installing/updating web dependencies..."
    # npm install
    
    print_status "Starting Next.js development server..."
    npm run dev >"$LOG_DIR/web.log" 2>&1 &
    local web_pid=$!
    PIDS+=("$web_pid")
    
    # Wait for web app to be ready
    if wait_for_service "http://localhost:3000" "Web Application"; then
        print_success "Web Application started successfully (PID: $web_pid)"
    else
        print_error "Failed to start Web Application"
        exit 1
    fi
    
    cd "$SCRIPT_DIR"
}

# Start microservices
start_microservices() {
    print_section "Starting Microservices"
    
    # Array of services (excluding API service)
    declare -A services=(
        ["stt_service"]="8001"
        ["diarization_service"]="8002"
    )
    
    for service in "${!services[@]}"; do
        local port="${services[$service]}"
        local service_dir="$BACKEND_DIR/$service"
        
        if [ ! -d "$service_dir" ]; then
            print_warning "Service directory $service_dir not found, skipping..."
            continue
        fi
        
        print_status "Starting $service on port $port..."
        
        cd "$service_dir"
        
        # Always sync dependencies to avoid timeout issues
        print_status "Syncing dependencies for $service..."
        if [ "$service" = "diarization_service" ]; then
            export HF_ENDPOINT=https://hf-mirror.com
        fi
        uv sync
        
        # Start the service
        if [ "$service" = "diarization_service" ]; then
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

# Start API service
start_api_service() {
    print_section "Starting API Service"
    
    local service="api_service"
    local port="8000"
    local service_dir="$BACKEND_DIR/$service"
    
    cd "$service_dir"
    
    print_status "Starting $service on port $port..."
    
    # Always sync dependencies to avoid timeout issues
    print_status "Syncing dependencies for $service..."
    uv sync
    
    # Start the API service
    uv run main.py >"$LOG_DIR/${service}.log" 2>&1 &
    local service_pid=$!
    PIDS+=("$service_pid")
    
    print_success "$service started (PID: $service_pid)"
    
    # Wait for API service to be ready
    local health_url="http://localhost:$port/health"
    if wait_for_service "$health_url" "$service"; then
        print_success "API Service is healthy and ready"
    else
        print_error "API Service failed to start"
        exit 1
    fi
    
    cd "$SCRIPT_DIR"
}

# Start LiveKit agent
start_agent() {
    print_section "Starting LiveKit Agent"
    
    local agent_dir="$BACKEND_DIR/agent_service/transcribe_agent"
    
    if [ ! -d "$agent_dir" ]; then
        print_error "Agent service directory not found at $agent_dir"
        exit 1
    fi
    
    cd "$agent_dir"
    
    print_status "Starting LiveKit transcription agent..."
    
    # Always sync dependencies to avoid timeout issues
    print_status "Syncing dependencies for agent..."
    export HF_ENDPOINT=https://hf-mirror.com
    uv sync
    
    # Start the agent
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
        exit 1
    fi
    
    cd "$SCRIPT_DIR"
}

# Main execution function
main() {
    clear
    echo -e "${PURPLE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║              Intrascribe LAN HTTPS Deployment               ║"
    echo "║                  Secure Network Access                      ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}\n"
    
    print_status "Local IP: $LOCAL_IP"
    print_status "Domain: $DOMAIN_NAME"
    echo ""
    
    # Check if running as root for nginx operations
    if [[ $EUID -eq 0 ]]; then
        print_error "Please do not run this script as root"
        print_status "The script will ask for sudo permissions when needed"
        exit 1
    fi
    
    # Check all dependencies first
    check_dependencies
    
    # Setup SSL certificates
    generate_ssl_certs
    
    # Setup nginx configuration  
    create_nginx_config
    
    # Setup environment files
    setup_environment
    
    # Start third-party services
    check_supabase
    check_redis  
    check_livekit
    
    # Start application services in order
    start_web
    start_microservices
    start_agent
    start_api_service
    
    # Display access information
    display_access_info
    
    # Keep script running in foreground
    print_status "All services are running. Press Ctrl+C to stop and cleanup."
    print_status "Monitoring services..."
    
    # Monitor services and wait for interrupt
    while true; do
        sleep 5
        
        # Check if any critical service has died
        local failed_services=()
        for pid in "${PIDS[@]}"; do
            if ! kill -0 "$pid" 2>/dev/null; then
                failed_services+=("$pid")
            fi
        done
        
        if [[ ${#failed_services[@]} -gt 0 ]]; then
            print_error "Some services have stopped unexpectedly!"
            print_status "Failed PIDs: ${failed_services[*]}"
            print_status "Check log files in $LOG_DIR/"
            break
        fi
    done
}

# Handle script execution
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
