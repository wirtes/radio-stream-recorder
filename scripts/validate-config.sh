#!/bin/bash

# Audio Stream Recorder - Configuration Validation Script
# Validates system configuration and deployment readiness

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
ERRORS=0
WARNINGS=0
CHECKS=0

# Functions
print_check() {
    echo -e "${BLUE}[CHECK]${NC} $1"
    ((CHECKS++))
}

print_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARNINGS++))
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    ((ERRORS++))
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Header
echo "=========================================="
echo "Audio Stream Recorder Configuration Validator"
echo "=========================================="
echo ""

# Check Docker installation
print_check "Checking Docker installation..."
if command -v docker &> /dev/null; then
    docker_version=$(docker --version | cut -d' ' -f3 | cut -d',' -f1)
    print_pass "Docker installed (version $docker_version)"
else
    print_error "Docker is not installed or not in PATH"
fi

# Check Docker Compose
print_check "Checking Docker Compose installation..."
if docker compose version &> /dev/null; then
    compose_version=$(docker compose version --short 2>/dev/null || docker compose version | head -1 | cut -d' ' -f4)
    print_pass "Docker Compose installed (version $compose_version)"
else
    print_error "Docker Compose is not installed or not available"
fi

# Check Docker daemon
print_check "Checking Docker daemon..."
if docker info &> /dev/null; then
    print_pass "Docker daemon is running"
else
    print_error "Docker daemon is not running or not accessible"
fi

# Check required files
print_check "Checking required files..."

required_files=("Dockerfile" "requirements.txt" "src/main.py")
for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        print_pass "Found $file"
    else
        print_error "Missing required file: $file"
    fi
done

# Check docker-compose files
if [ -f "docker-compose.yml" ]; then
    print_pass "Found docker-compose.yml"
else
    if [ -f "docker-compose.yml.example" ]; then
        print_warning "docker-compose.yml not found, but example exists"
        print_info "Run: cp docker-compose.yml.example docker-compose.yml"
    else
        print_error "No docker-compose.yml or example found"
    fi
fi

if [ -f "docker-compose.prod.yml" ]; then
    print_pass "Found docker-compose.prod.yml"
else
    print_warning "docker-compose.prod.yml not found (optional for production)"
fi

# Check environment configuration
print_check "Checking environment configuration..."

if [ -f ".env" ]; then
    print_pass "Found .env file"
    
    # Check for required variables
    required_vars=("WEB_PORT" "LOG_LEVEL" "MAX_CONCURRENT_RECORDINGS" "SECRET_KEY")
    for var in "${required_vars[@]}"; do
        if grep -q "^${var}=" .env; then
            value=$(grep "^${var}=" .env | cut -d'=' -f2)
            if [ -n "$value" ]; then
                print_pass "Environment variable $var is set"
            else
                print_warning "Environment variable $var is empty"
            fi
        else
            print_warning "Environment variable $var is not set"
        fi
    done
    
    # Check for security issues
    if grep -q "SECRET_KEY=your-secret-key-here" .env; then
        print_error "Default secret key detected - change SECRET_KEY in .env"
    fi
    
    if grep -q "FLASK_DEBUG=true" .env; then
        print_warning "Debug mode enabled - disable for production"
    fi
    
else
    if [ -f ".env.example" ]; then
        print_warning ".env file not found, but example exists"
        print_info "Run: cp .env.example .env"
    else
        print_error "No .env or .env.example file found"
    fi
fi

# Check directories
print_check "Checking required directories..."

required_dirs=("data" "recordings" "logs" "artwork" "config")
for dir in "${required_dirs[@]}"; do
    if [ -d "$dir" ]; then
        # Check permissions
        if [ -w "$dir" ]; then
            print_pass "Directory $dir exists and is writable"
        else
            print_warning "Directory $dir exists but is not writable"
        fi
    else
        print_warning "Directory $dir does not exist (will be created automatically)"
    fi
done

# Check SSH configuration
print_check "Checking SSH configuration..."

if [ -d "config" ]; then
    if [ -f "config/ssh_key" ]; then
        # Check SSH key permissions
        ssh_key_perms=$(stat -c "%a" config/ssh_key 2>/dev/null || echo "000")
        if [ "$ssh_key_perms" = "600" ]; then
            print_pass "SSH key found with correct permissions"
        else
            print_warning "SSH key found but permissions are $ssh_key_perms (should be 600)"
            print_info "Run: chmod 600 config/ssh_key"
        fi
        
        # Check if it's a valid private key
        if grep -q "BEGIN.*PRIVATE KEY" config/ssh_key; then
            print_pass "SSH key appears to be a valid private key"
        else
            print_warning "SSH key file doesn't appear to be a private key"
        fi
    else
        print_warning "SSH key not found at config/ssh_key (required for SCP transfers)"
        print_info "Copy your SSH private key: cp ~/.ssh/id_rsa config/ssh_key"
    fi
else
    print_warning "Config directory not found"
fi

# Check system resources
print_check "Checking system resources..."

# Check available disk space
available_space_kb=$(df . | tail -1 | awk '{print $4}')
available_space_gb=$((available_space_kb / 1024 / 1024))

if [ "$available_space_gb" -ge 5 ]; then
    print_pass "Sufficient disk space available (${available_space_gb}GB)"
elif [ "$available_space_gb" -ge 1 ]; then
    print_warning "Limited disk space available (${available_space_gb}GB) - consider cleanup"
else
    print_error "Insufficient disk space (${available_space_gb}GB) - need at least 1GB"
fi

# Check available memory
if command -v free &> /dev/null; then
    available_memory_mb=$(free -m | awk 'NR==2{print $7}')
    if [ "$available_memory_mb" -ge 1024 ]; then
        print_pass "Sufficient memory available (${available_memory_mb}MB)"
    elif [ "$available_memory_mb" -ge 512 ]; then
        print_warning "Limited memory available (${available_memory_mb}MB)"
    else
        print_warning "Low memory available (${available_memory_mb}MB) - may affect performance"
    fi
fi

# Check network connectivity
print_check "Checking network connectivity..."

if ping -c 1 8.8.8.8 &> /dev/null; then
    print_pass "Internet connectivity available"
else
    print_warning "No internet connectivity detected"
fi

# Check port availability
print_check "Checking port availability..."

web_port=${WEB_PORT:-8666}
if [ -f ".env" ]; then
    web_port=$(grep "^WEB_PORT=" .env | cut -d'=' -f2 || echo "8666")
fi

if command -v netstat &> /dev/null; then
    if netstat -tuln | grep -q ":${web_port} "; then
        print_warning "Port $web_port is already in use"
    else
        print_pass "Port $web_port is available"
    fi
elif command -v ss &> /dev/null; then
    if ss -tuln | grep -q ":${web_port} "; then
        print_warning "Port $web_port is already in use"
    else
        print_pass "Port $web_port is available"
    fi
else
    print_info "Cannot check port availability (netstat/ss not available)"
fi

# Validate docker-compose syntax
print_check "Validating Docker Compose configuration..."

if [ -f "docker-compose.yml" ]; then
    if docker compose -f docker-compose.yml config &> /dev/null; then
        print_pass "docker-compose.yml syntax is valid"
    else
        print_error "docker-compose.yml has syntax errors"
        print_info "Run: docker compose -f docker-compose.yml config"
    fi
fi

if [ -f "docker-compose.prod.yml" ]; then
    if docker compose -f docker-compose.prod.yml config &> /dev/null; then
        print_pass "docker-compose.prod.yml syntax is valid"
    else
        print_error "docker-compose.prod.yml has syntax errors"
    fi
fi

# Check for common issues
print_check "Checking for common configuration issues..."

# Check for Windows line endings
if command -v file &> /dev/null; then
    if [ -f ".env" ]; then
        if file .env | grep -q "CRLF"; then
            print_warning ".env file has Windows line endings (CRLF)"
            print_info "Convert to Unix format: dos2unix .env"
        fi
    fi
fi

# Check timezone setting
if [ -f ".env" ]; then
    if grep -q "^TZ=" .env; then
        tz_value=$(grep "^TZ=" .env | cut -d'=' -f2)
        print_pass "Timezone configured: $tz_value"
    else
        print_warning "Timezone not configured (will use UTC)"
        print_info "Add to .env: TZ=America/New_York"
    fi
fi

# Summary
echo ""
echo "=========================================="
echo "Validation Summary"
echo "=========================================="
echo "Total checks: $CHECKS"
echo -e "Errors: ${RED}$ERRORS${NC}"
echo -e "Warnings: ${YELLOW}$WARNINGS${NC}"
echo -e "Passed: ${GREEN}$((CHECKS - ERRORS - WARNINGS))${NC}"
echo ""

if [ "$ERRORS" -eq 0 ]; then
    if [ "$WARNINGS" -eq 0 ]; then
        echo -e "${GREEN}✅ Configuration is ready for deployment!${NC}"
        echo ""
        echo "Next steps:"
        echo "  ./deploy.sh start      # Start with development config"
        echo "  ./deploy.sh start prod # Start with production config"
    else
        echo -e "${YELLOW}⚠️  Configuration has warnings but should work${NC}"
        echo ""
        echo "Consider addressing the warnings above for optimal operation."
        echo ""
        echo "To start anyway:"
        echo "  ./deploy.sh start      # Start with development config"
        echo "  ./deploy.sh start prod # Start with production config"
    fi
else
    echo -e "${RED}❌ Configuration has errors that must be fixed${NC}"
    echo ""
    echo "Please address the errors above before deployment."
    exit 1
fi

echo ""