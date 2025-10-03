"""
Utility functions for web interface.
"""
import os
import secrets
from functools import wraps
from flask import request, jsonify, session, current_app
from werkzeug.exceptions import BadRequest, Forbidden
from pydantic import ValidationError
import logging

logger = logging.getLogger(__name__)


def generate_csrf_token():
    """Generate a CSRF token for form protection."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(16)
    return session['csrf_token']


def validate_csrf_token(token):
    """Validate CSRF token."""
    return token and session.get('csrf_token') == token


def csrf_protect(f):
    """Decorator to protect routes with CSRF validation."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            # Check for CSRF token in headers or form data
            token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
            if not validate_csrf_token(token):
                if request.is_json:
                    return jsonify({
                        'error': 'CSRF Token Missing or Invalid',
                        'message': 'CSRF token is required for this operation',
                        'status_code': 403
                    }), 403
                else:
                    raise Forbidden('CSRF token is required for this operation')
        return f(*args, **kwargs)
    return decorated_function


def validate_json(model_class):
    """Validate request JSON against Pydantic model."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                if not request.is_json:
                    raise BadRequest("Request must contain valid JSON")
                
                data = model_class(**request.get_json())
                return f(data, *args, **kwargs)
            except ValidationError as e:
                return handle_validation_error(e)
            except Exception as e:
                logger.error(f"JSON validation error in {f.__name__}: {str(e)}")
                raise BadRequest(f"Invalid request data: {str(e)}")
        return wrapper
    return decorator


def handle_validation_error(error: ValidationError):
    """Handle Pydantic validation errors and return formatted response."""
    errors = []
    for err in error.errors():
        field = '.'.join(str(x) for x in err['loc'])
        errors.append({
            'field': field,
            'message': err['msg'],
            'type': err['type']
        })
    
    return jsonify({
        'error': 'Validation Error',
        'message': 'Invalid input data',
        'details': errors,
        'status_code': 400
    }), 400


def validate_file_upload(file, allowed_extensions=None, max_size_mb=10):
    """Validate uploaded file."""
    if not file or file.filename == '':
        raise BadRequest("No file selected")
    
    if allowed_extensions:
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            raise BadRequest(f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}")
    
    # Check file size (seek to end to get size, then reset)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        raise BadRequest(f"File too large. Maximum size: {max_size_mb}MB")
    
    return True


def sanitize_filename(filename):
    """Sanitize filename for safe storage."""
    import re
    # Remove or replace dangerous characters
    filename = re.sub(r'[^\w\s\-_\.]', '', filename)
    # Replace spaces with underscores
    filename = re.sub(r'\s+', '_', filename)
    # Remove multiple consecutive dots or underscores
    filename = re.sub(r'[_\.]{2,}', '_', filename)
    return filename.strip('_.')


def get_client_ip():
    """Get client IP address from request."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return request.remote_addr


def log_api_request(endpoint, method, client_ip, user_agent=None):
    """Log API request for monitoring."""
    logger.info(f"API Request: {method} {endpoint} from {client_ip} - {user_agent}")


def require_local_network(f):
    """Decorator to restrict access to local network only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = get_client_ip()
        
        # Allow localhost and private network ranges
        allowed_networks = [
            '127.0.0.1',
            '::1',
            '10.',
            '172.16.',
            '172.17.',
            '172.18.',
            '172.19.',
            '172.20.',
            '172.21.',
            '172.22.',
            '172.23.',
            '172.24.',
            '172.25.',
            '172.26.',
            '172.27.',
            '172.28.',
            '172.29.',
            '172.30.',
            '172.31.',
            '192.168.'
        ]
        
        if not any(client_ip.startswith(network) for network in allowed_networks):
            logger.warning(f"Access denied for IP: {client_ip}")
            if request.is_json:
                return jsonify({
                    'error': 'Access Denied',
                    'message': 'Access restricted to local network only',
                    'status_code': 403
                }), 403
            else:
                raise Forbidden('Access restricted to local network only')
        
        return f(*args, **kwargs)
    return decorated_function


def format_file_size(size_bytes):
    """Format file size in human readable format."""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


def format_duration(seconds):
    """Format duration in human readable format."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds}s"
    else:
        hours = seconds // 3600
        remaining_minutes = (seconds % 3600) // 60
        return f"{hours}h {remaining_minutes}m"