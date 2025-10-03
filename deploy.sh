#!/bin/bash

# Audio Stream Recorder - Enhanced Deployment Script
# Comprehensive deployment and management script for Audio Stream Recorder

set -e

# Script version
SCRIPT_VERSION="1.0.0"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
DEFAULT_WEB_PORT=8666
CONTAINER_NAME="audio-stream-recorder"
PROJECT_NAME="audio-stream-recorder"

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

print_header() {
    echo -e "${PURPLE}[DEPLOY]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check Docker daemon access
    if ! docker info &> /dev/null; then
        print_error "Cannot connect to Docker daemon. This usually means:"
        print_error "1. Docker daemon is not running, or"
        print_error "2. Your user doesn't have permission to access Docker"
        print_error ""
        print_error "To fix permission issues, run:"
        print_error "  sudo usermod -aG docker \$USER"
        print_error "  newgrp docker"
        print_error ""
        print_error "Then try again."
        exit 1
    fi
    
    # Additional check: try to run a simple docker command
    if ! docker version &> /dev/null; then
        print_error "Docker permission issue detected."
        print_error "Run: sudo usermod -aG docker \$USER && newgrp docker"
        exit 1
    fi
    
    print_status "Docker and Docker Compose are installed and accessible"
}

# Create required directories
create_directories() {
    print_status "Creating required directories..."
    
    mkdir -p data
    mkdir -p recordings
    mkdir -p config
    mkdir -p logs
    mkdir -p artwork
    
    # Set proper permissions
    chmod 755 data recordings config logs artwork
    
    print_status "Directories created successfully"
}

# Create .env file if it doesn't exist
setup_env() {
    if [ ! -f .env ]; then
        print_status "Creating .env file from template..."
        cp .env.example .env
        print_warning "Please review and modify .env file with your configuration"
    else
        print_status ".env file already exists"
    fi
}

# Build and start the container
deploy() {
    local compose_file="docker-compose.yml"
    
    # Check if production flag is set
    if [ "$1" = "prod" ]; then
        compose_file="docker-compose.prod.yml"
        print_status "Using production configuration"
    else
        print_status "Using development configuration"
    fi
    
    print_status "Building Docker image..."
    docker compose -f "$compose_file" build
    
    print_status "Starting Audio Stream Recorder..."
    docker compose -f "$compose_file" up -d
    
    # Wait for health check
    print_status "Waiting for application to start..."
    sleep 10
    
    # Check if container is running
    if docker compose -f "$compose_file" ps | grep -q "Up"; then
        print_status "Audio Stream Recorder is running successfully!"
        
        # Get the port from environment or default
        PORT=${WEB_PORT:-8666}
        print_status "Web interface available at: http://localhost:$PORT"
        print_status "Health check endpoint: http://localhost:$PORT/health"
        
        # Show logs
        print_status "Recent logs:"
        docker compose -f "$compose_file" logs --tail=20
    else
        print_error "Failed to start Audio Stream Recorder"
        docker compose -f "$compose_file" logs
        exit 1
    fi
}

# Stop the container
stop() {
    local compose_file="docker-compose.yml"
    
    if [ "$1" = "prod" ]; then
        compose_file="docker-compose.prod.yml"
    fi
    
    print_status "Stopping Audio Stream Recorder..."
    docker compose -f "$compose_file" down
    print_status "Audio Stream Recorder stopped"
}

# Check system requirements
check_system_requirements() {
    print_header "Checking system requirements..."
    
    # Check available disk space (minimum 1GB)
    available_space=$(df . | tail -1 | awk '{print $4}')
    if [ "$available_space" -lt 1048576 ]; then  # 1GB in KB
        print_warning "Low disk space detected. Ensure at least 1GB free space for recordings."
    fi
    
    # Check memory (minimum 512MB)
    if command -v free &> /dev/null; then
        available_memory=$(free -m | awk 'NR==2{print $7}')
        if [ "$available_memory" -lt 512 ]; then
            print_warning "Low available memory detected. Consider increasing system memory."
        fi
    fi
    
    print_status "System requirements check completed"
}

# Setup SSH configuration
setup_ssh() {
    print_status "Setting up SSH configuration..."
    
    if [ ! -d "config" ]; then
        mkdir -p config
        chmod 755 config
    fi
    
    if [ ! -f "config/ssh_key" ]; then
        print_warning "SSH key not found at config/ssh_key"
        print_warning "For SCP transfers, copy your SSH private key to config/ssh_key"
        print_warning "Example: cp ~/.ssh/id_rsa config/ssh_key && chmod 600 config/ssh_key"
    else
        # Check SSH key permissions
        ssh_key_perms=$(stat -c "%a" config/ssh_key 2>/dev/null || echo "000")
        if [ "$ssh_key_perms" != "600" ]; then
            print_status "Fixing SSH key permissions..."
            chmod 600 config/ssh_key
        fi
        print_status "SSH key found and configured"
    fi
}

# Validate configuration
validate_config() {
    print_status "Validating configuration..."
    
    if [ -f ".env" ]; then
        # Check for required variables
        required_vars=("WEB_PORT" "LOG_LEVEL" "MAX_CONCURRENT_RECORDINGS")
        
        for var in "${required_vars[@]}"; do
            if ! grep -q "^${var}=" .env; then
                print_warning "Missing configuration variable: $var"
            fi
        done
        
        # Check for dangerous settings
        if grep -q "SECRET_KEY=your-secret-key-here" .env; then
            print_warning "Default secret key detected. Change SECRET_KEY in .env for production!"
        fi
        
        if grep -q "FLASK_DEBUG=true" .env; then
            print_warning "Debug mode enabled. Disable for production deployment."
        fi
        
        print_status "Configuration validation completed"
    else
        print_warning "No .env file found. Using defaults from .env.example"
    fi
}

# Health check function
health_check() {
    local port=${WEB_PORT:-$DEFAULT_WEB_PORT}
    local max_attempts=30
    local attempt=1
    
    print_status "Performing health check..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f -s "http://localhost:$port/health" > /dev/null 2>&1; then
            print_success "Health check passed!"
            return 0
        fi
        
        print_debug "Health check attempt $attempt/$max_attempts failed, retrying..."
        sleep 2
        ((attempt++))
    done
    
    print_error "Health check failed after $max_attempts attempts"
    return 1
}

# Backup function
backup_data() {
    print_status "Creating data backup..."
    
    local backup_dir="backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"
    
    # Backup database and configuration
    if [ -d "data" ]; then
        cp -r data "$backup_dir/"
        print_status "Database backed up to $backup_dir/data"
    fi
    
    if [ -f ".env" ]; then
        cp .env "$backup_dir/"
        print_status "Environment configuration backed up"
    fi
    
    if [ -d "config" ]; then
        cp -r config "$backup_dir/"
        print_status "SSH configuration backed up"
    fi
    
    print_success "Backup created at $backup_dir"
}

# Update function
update() {
    print_header "Updating Audio Stream Recorder..."
    
    # Create backup before update
    backup_data
    
    # Pull latest changes (if in git repository)
    if [ -d ".git" ]; then
        print_status "Pulling latest changes..."
        git pull
    fi
    
    # Rebuild and restart
    local compose_file="docker-compose.yml"
    if [ "$1" = "prod" ]; then
        compose_file="docker-compose.prod.yml"
    fi
    
    print_status "Rebuilding container..."
    docker compose -f "$compose_file" build --no-cache
    
    print_status "Restarting services..."
    docker compose -f "$compose_file" down
    docker compose -f "$compose_file" up -d
    
    # Health check after update
    if health_check; then
        print_success "Update completed successfully!"
    else
        print_error "Update failed - service not healthy"
        exit 1
    fi
}

# Cleanup function
cleanup() {
    print_status "Cleaning up Docker resources..."
    
    # Remove stopped containers
    docker container prune -f
    
    # Remove unused images
    docker image prune -f
    
    # Remove unused volumes (be careful with this)
    if [ "$1" = "--volumes" ]; then
        print_warning "Removing unused volumes..."
        docker volume prune -f
    fi
    
    print_success "Cleanup completed"
}

# Show detailed status
detailed_status() {
    local compose_file="docker-compose.yml"
    if [ "$1" = "prod" ]; then
        compose_file="docker-compose.prod.yml"
    fi
    
    print_header "Audio Stream Recorder Status"
    echo ""
    
    # Container status
    print_status "Container Status:"
    docker compose -f "$compose_file" ps
    echo ""
    
    # Resource usage
    if docker ps --format "table {{.Names}}" | grep -q "$CONTAINER_NAME"; then
        print_status "Resource Usage:"
        docker stats --no-stream "$CONTAINER_NAME" 2>/dev/null || echo "Resource stats not available"
        echo ""
    fi
    
    # Health check
    local port=${WEB_PORT:-$DEFAULT_WEB_PORT}
    print_status "Health Check:"
    if curl -f -s "http://localhost:$port/health" > /dev/null 2>&1; then
        echo "✅ Service is healthy"
        echo "🌐 Web interface: http://localhost:$port"
    else
        echo "❌ Service is not responding"
    fi
    echo ""
    
    # Disk usage
    print_status "Disk Usage:"
    du -sh data recordings logs artwork config 2>/dev/null || echo "Directories not found"
    echo ""
    
    # Recent logs
    print_status "Recent Logs (last 10 lines):"
    docker compose -f "$compose_file" logs --tail=10 2>/dev/null || echo "No logs available"
}

# Install function for first-time setup
install() {
    print_header "Installing Audio Stream Recorder..."
    
    # Check system requirements
    check_system_requirements
    
    # Check Docker
    check_docker
    
    # Create directories
    create_directories
    
    # Setup environment
    setup_env
    
    # Setup SSH
    setup_ssh
    
    # Validate configuration
    validate_config
    
    # Create docker-compose.yml if it doesn't exist
    if [ ! -f "docker-compose.yml" ]; then
        if [ -f "docker-compose.yml.example" ]; then
            print_status "Creating docker-compose.yml from example..."
            cp docker-compose.yml.example docker-compose.yml
        else
            print_error "docker-compose.yml.example not found!"
            exit 1
        fi
    fi
    
    print_success "Installation setup completed!"
    print_status "Run '$0 start' to start the application"
}

# Show usage
usage() {
    echo -e "${CYAN}Audio Stream Recorder Deployment Script v$SCRIPT_VERSION${NC}"
    echo ""
    echo "Usage: $0 {command} [options]"
    echo ""
    echo -e "${YELLOW}Commands:${NC}"
    echo "  install          - First-time installation setup"
    echo "  start            - Build and start the container"
    echo "  stop             - Stop the container"
    echo "  restart          - Restart the container"
    echo "  update           - Update and restart the application"
    echo "  logs             - Show container logs"
    echo "  status           - Show basic container status"
    echo "  detailed-status  - Show detailed system status"
    echo "  backup           - Create data backup"
    echo "  cleanup          - Clean up Docker resources"
    echo "  health           - Perform health check"
    echo ""
    echo -e "${YELLOW}Options:${NC}"
    echo "  prod             - Use production configuration"
    echo "  --volumes        - Include volumes in cleanup (use with cleanup)"
    echo "  -f, --follow     - Follow logs in real-time (use with logs)"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo "  $0 install                    # First-time setup"
    echo "  $0 start                      # Start with development config"
    echo "  $0 start prod                 # Start with production config"
    echo "  $0 logs -f                    # Follow logs in real-time"
    echo "  $0 detailed-status prod       # Show detailed production status"
    echo "  $0 update prod                # Update production deployment"
    echo "  $0 cleanup --volumes          # Clean up including volumes"
    echo ""
    echo -e "${YELLOW}Configuration Files:${NC}"
    echo "  .env                          # Environment variables"
    echo "  docker-compose.yml            # Development configuration"
    echo "  docker-compose.prod.yml       # Production configuration"
    echo "  config/ssh_key                # SSH private key for SCP transfers"
}

# Main script logic
case "$1" in
    install)
        install
        ;;
    start)
        check_docker
        create_directories
        setup_env
        setup_ssh
        validate_config
        deploy "$2"
        ;;
    stop)
        stop "$2"
        ;;
    restart)
        stop "$2"
        sleep 2
        check_docker
        create_directories
        setup_env
        setup_ssh
        validate_config
        deploy "$2"
        ;;
    update)
        update "$2"
        ;;
    logs)
        compose_file="docker-compose.yml"
        if [ "$2" = "prod" ]; then
            compose_file="docker-compose.prod.yml"
        fi
        
        if [ "$2" = "-f" ] || [ "$3" = "-f" ] || [ "$2" = "--follow" ] || [ "$3" = "--follow" ]; then
            docker compose -f "$compose_file" logs -f
        else
            docker compose -f "$compose_file" logs --tail=50
        fi
        ;;
    status)
        compose_file="docker-compose.yml"
        if [ "$2" = "prod" ]; then
            compose_file="docker-compose.prod.yml"
        fi
        docker compose -f "$compose_file" ps
        ;;
    detailed-status)
        detailed_status "$2"
        ;;
    backup)
        backup_data
        ;;
    cleanup)
        cleanup "$2"
        ;;
    health)
        health_check
        ;;
    --version|-v)
        echo "Audio Stream Recorder Deployment Script v$SCRIPT_VERSION"
        ;;
    --help|-h|help)
        usage
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        usage
        exit 1
        ;;
esac