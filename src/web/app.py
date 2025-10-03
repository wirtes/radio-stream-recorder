"""
Flask application factory and configuration.
"""
import os
import time
from flask import Flask, render_template, request, jsonify, g
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
import logging

from src.config import Config
from src.models.database import init_db
from src.web.utils import generate_csrf_token


def create_app(config_class=Config, service_container=None):
    """Create and configure Flask application with service integration."""
    app = Flask(__name__, 
                template_folder='../../templates',
                static_folder='../../static')
    
    # Load configuration
    app.config.from_object(config_class)
    
    # Store service container for dependency injection
    app.service_container = service_container
    
    # Enable CORS for API endpoints
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # Initialize database
    init_db(app.config['DATABASE_URL'])
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, app.config.get('LOG_LEVEL', 'INFO')),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Request logging middleware
    @app.before_request
    def before_request():
        """Log request start and set timing."""
        g.start_time = time.time()
        
    @app.after_request
    def after_request(response):
        """Log request completion with timing and status."""
        try:
            from src.services.logging_service import get_logging_service
            
            # Calculate response time
            response_time_ms = (time.time() - g.start_time) * 1000
            
            # Get user IP
            user_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
            
            # Log web request
            logging_service = get_logging_service()
            logging_service.log_web_request(
                method=request.method,
                path=request.path,
                status_code=response.status_code,
                response_time_ms=response_time_ms,
                user_ip=user_ip
            )
        except Exception as e:
            # Don't let logging errors break the response
            app.logger.error(f"Error logging request: {str(e)}")
            
        return response
    
    # Add CSRF token function to template context
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf_token)
    
    # Register blueprints
    from src.web.routes.api import api_bp
    from src.web.routes.main import main_bp
    
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(main_bp)
    
    # Error handlers
    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        """Handle HTTP exceptions."""
        # Log the error
        try:
            from src.services.logging_service import get_logging_service, OperationType, LogLevel
            logging_service = get_logging_service()
            logging_service.log_operation(
                OperationType.WEB_REQUEST,
                f"HTTP {e.code} error: {e.description}",
                LogLevel.WARNING,
                context={
                    'method': request.method,
                    'path': request.path,
                    'status_code': e.code,
                    'error': e.name
                }
            )
        except Exception:
            pass  # Don't let logging errors break error handling
            
        if request.path.startswith('/api/'):
            return jsonify({
                'error': e.name,
                'message': e.description,
                'status_code': e.code
            }), e.code
        return render_template('error.html', error=e), e.code
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        """Handle unexpected exceptions."""
        app.logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
        
        # Log the error
        try:
            from src.services.logging_service import get_logging_service, OperationType, LogLevel
            logging_service = get_logging_service()
            logging_service.log_operation(
                OperationType.ERROR,
                f"Unhandled exception in web request: {str(e)}",
                LogLevel.ERROR,
                context={
                    'method': request.method,
                    'path': request.path,
                    'exception_type': type(e).__name__
                },
                exc_info=True
            )
        except Exception:
            pass  # Don't let logging errors break error handling
            
        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Internal Server Error',
                'message': 'An unexpected error occurred',
                'status_code': 500
            }), 500
        return render_template('error.html', 
                             error={'name': 'Internal Server Error', 
                                   'description': 'An unexpected error occurred'}), 500
    
    return app