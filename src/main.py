"""
Main entry point for Audio Stream Recorder application.
Container initialization and service startup with proper dependency injection.
"""

import logging
import sys
import signal
import os
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any

from src.config import config


class ServiceContainer:
    """
    Service container for dependency injection and service coordination.
    Manages service lifecycle and dependencies.
    """
    
    def __init__(self):
        self.services: Dict[str, Any] = {}
        self._initialized = False
        self._shutdown_handlers = []
    
    def register_service(self, name: str, service: Any, shutdown_handler: Optional[callable] = None):
        """Register a service with optional shutdown handler."""
        self.services[name] = service
        if shutdown_handler:
            self._shutdown_handlers.append((name, shutdown_handler))
    
    def get_service(self, name: str) -> Any:
        """Get a registered service."""
        return self.services.get(name)
    
    def shutdown_all(self):
        """Shutdown all services in reverse order of registration."""
        for name, handler in reversed(self._shutdown_handlers):
            try:
                print(f"Shutting down {name}...")
                handler()
            except Exception as e:
                print(f"Error shutting down {name}: {e}")


# Global service container
service_container = ServiceContainer()


def initialize_database():
    """Initialize database and create tables if they don't exist."""
    try:
        from src.models.database import init_db, create_tables
        
        # Initialize database connection
        init_db(config.DATABASE_URL)
        
        # Create tables if they don't exist
        create_tables()
        
        print("Database initialized successfully")
        return True
        
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        return False


def setup_logging_and_monitoring():
    """Initialize logging and monitoring services with proper registration."""
    from src.services.logging_service import init_logging_service
    from src.services.monitoring_service import init_monitoring_service
    
    # Initialize structured logging service
    logging_service = init_logging_service(
        log_dir=config.LOG_DIR,
        log_level=config.LOG_LEVEL
    )
    
    # Initialize monitoring service
    monitoring_service = init_monitoring_service(
        monitoring_interval=int(os.getenv('MONITORING_INTERVAL', '60')),
        disk_warning_threshold=float(os.getenv('DISK_WARNING_THRESHOLD', '80.0')),
        disk_critical_threshold=float(os.getenv('DISK_CRITICAL_THRESHOLD', '90.0')),
        memory_warning_threshold=float(os.getenv('MEMORY_WARNING_THRESHOLD', '80.0')),
        memory_critical_threshold=float(os.getenv('MEMORY_CRITICAL_THRESHOLD', '90.0'))
    )
    
    # Register services in container
    service_container.register_service(
        'logging', 
        logging_service,
        lambda: logging_service.log_system_shutdown()
    )
    
    service_container.register_service(
        'monitoring', 
        monitoring_service,
        lambda: monitoring_service.stop_monitoring()
    )
    
    # Start monitoring
    monitoring_service.start_monitoring()
    
    # Log system startup
    logging_service.log_system_startup()
    
    return logging_service, monitoring_service


def initialize_scheduler():
    """Initialize and start the scheduler service with proper registration."""
    try:
        from src.services.scheduler_service import SchedulerService
        from src.models.database import get_db_manager
        
        # Get the database manager instance
        db_manager = get_db_manager()
        scheduler_service = SchedulerService(db_manager=db_manager)
        scheduler_service.start()
        
        # Register scheduler service
        service_container.register_service(
            'scheduler',
            scheduler_service,
            lambda: scheduler_service.stop()
        )
        
        print("Scheduler service started successfully")
        return scheduler_service
        
    except Exception as e:
        print(f"Failed to start scheduler service: {e}")
        return None


def create_web_app():
    """Create and configure the Flask web application with service integration."""
    try:
        from src.web.app import create_app
        
        # Pass service container to web app for dependency injection
        app = create_app(service_container=service_container)
        
        # Add health check endpoint for container monitoring
        @app.route('/health')
        def health_check():
            """Health check endpoint for container monitoring."""
            try:
                # Check database connection
                from src.models.database import get_db_session
                from sqlalchemy import text
                with get_db_session() as session:
                    session.execute(text("SELECT 1"))
                
                # Check service statuses using service container
                scheduler_service = service_container.get_service('scheduler')
                monitoring_service = service_container.get_service('monitoring')
                
                scheduler_status = scheduler_service.is_running() if scheduler_service else False
                monitoring_status = monitoring_service.is_running() if monitoring_service else False
                
                return {
                    'status': 'healthy',
                    'timestamp': time.time(),
                    'services': {
                        'database': 'ok',
                        'scheduler': 'ok' if scheduler_status else 'error',
                        'monitoring': 'ok' if monitoring_status else 'error'
                    }
                }, 200
                
            except Exception as e:
                return {
                    'status': 'unhealthy',
                    'timestamp': time.time(),
                    'error': str(e)
                }, 503
        
        print("Web application created successfully")
        return app
        
    except Exception as e:
        print(f"Failed to create web application: {e}")
        return None


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown using service container."""
    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully."""
        print(f"\nReceived signal {signum}, initiating graceful shutdown...")
        
        # Use service container for coordinated shutdown
        service_container.shutdown_all()
        
        print("Graceful shutdown complete")
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def run_web_server(app):
    """Run the Flask web server."""
    try:
        # Run the Flask application
        app.run(
            host='0.0.0.0',
            port=config.WEB_PORT,
            debug=False,
            threaded=True,
            use_reloader=False
        )
    except Exception as e:
        print(f"Web server error: {e}")
        raise


def main():
    """Main application entry point with proper service coordination and dependency injection."""
    app_instance = None
    
    try:
        print("=== Audio Stream Recorder Container Initialization ===")
        
        # Ensure required directories exist
        print("Creating required directories...")
        config.ensure_directories()
        
        # Validate configuration
        print("Validating configuration...")
        config.validate_config()
        
        # Initialize database
        print("Initializing database...")
        if not initialize_database():
            sys.exit(1)
        
        # Initialize logging and monitoring services (registers in service container)
        print("Starting logging and monitoring services...")
        logging_service, monitoring_service = setup_logging_and_monitoring()
        
        # Initialize scheduler service (registers in service container)
        print("Starting scheduler service...")
        scheduler_service = initialize_scheduler()
        if not scheduler_service:
            sys.exit(1)
        
        # Initialize additional services for complete workflow integration
        print("Initializing workflow services...")
        initialize_workflow_services()
        
        # Create web application with service integration
        print("Creating web application...")
        app_instance = create_web_app()
        if not app_instance:
            sys.exit(1)
        
        # Register web app in service container
        service_container.register_service('web_app', app_instance)
        
        # Setup signal handlers for graceful shutdown
        setup_signal_handlers()
        
        # Log successful startup with service status
        log_startup_complete()
        
        # Start the web server (this blocks)
        run_web_server(app_instance)
        
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        service_container.shutdown_all()
    except Exception as e:
        print(f"Failed to start application: {e}")
        import traceback
        traceback.print_exc()
        
        # Attempt graceful shutdown even on startup failure
        try:
            service_container.shutdown_all()
        except Exception:
            pass
        
        sys.exit(1)


def initialize_workflow_services():
    """Initialize additional services needed for complete workflow integration."""
    try:
        # Initialize transfer queue service
        from src.services.transfer_queue import TransferQueue
        transfer_queue = TransferQueue()
        
        service_container.register_service(
            'transfer_queue',
            transfer_queue,
            lambda: transfer_queue.stop() if hasattr(transfer_queue, 'stop') else None
        )
        
        # Initialize job manager with service dependencies
        from src.services.job_manager import JobManager
        from src.models.database import get_db_manager
        
        db_manager = get_db_manager()
        job_manager = JobManager(
            scheduler_service=service_container.get_service('scheduler'),
            db_manager=db_manager
        )
        
        service_container.register_service('job_manager', job_manager)
        
        # Initialize workflow coordinator to wire everything together
        from src.services.workflow_coordinator import WorkflowCoordinator
        workflow_coordinator = WorkflowCoordinator(
            scheduler_service=service_container.get_service('scheduler'),
            transfer_queue=transfer_queue,
            logging_service=service_container.get_service('logging'),
            db_manager=db_manager
        )
        
        service_container.register_service(
            'workflow_coordinator',
            workflow_coordinator,
            lambda: workflow_coordinator.stop_all_sessions()
        )
        
        # Start background task for automatic backups
        start_backup_scheduler(workflow_coordinator)
        
        print("Workflow services initialized successfully")
        print("Complete recording workflow integration established")
        
    except Exception as e:
        print(f"Failed to initialize workflow services: {e}")
        raise


def start_backup_scheduler(workflow_coordinator):
    """Start background thread for automatic backup checks."""
    def backup_check_loop():
        """Background loop to check for automatic backups."""
        while True:
            try:
                # Check every hour for automatic backup needs
                time.sleep(3600)  # 1 hour
                workflow_coordinator.check_and_create_automatic_backup()
            except Exception as e:
                print(f"Error in backup check loop: {e}")
    
    # Start backup check thread
    backup_thread = threading.Thread(target=backup_check_loop, daemon=True)
    backup_thread.start()
    print("Automatic backup scheduler started")


def log_startup_complete():
    """Log successful startup with comprehensive service status."""
    logging_service = service_container.get_service('logging')
    
    print("=== Container Initialization Complete ===")
    print(f"Web interface available at: http://0.0.0.0:{config.WEB_PORT}")
    print(f"Health check endpoint: http://0.0.0.0:{config.WEB_PORT}/health")
    print(f"Data directory: {config.DATA_DIR}")
    print(f"Recordings directory: {config.RECORDINGS_DIR}")
    print(f"Logs directory: {config.LOG_DIR}")
    print(f"Artwork directory: {config.ARTWORK_DIR}")
    print(f"SSH config directory: {config.SSH_CONFIG_DIR}")
    print(f"Max concurrent recordings: {config.MAX_CONCURRENT_RECORDINGS}")
    
    # Log service status
    services_status = {}
    for service_name, service in service_container.services.items():
        try:
            if hasattr(service, 'is_running'):
                status = 'running' if service.is_running() else 'stopped'
            else:
                status = 'initialized'
            services_status[service_name] = status
        except Exception:
            services_status[service_name] = 'unknown'
    
    print("Service Status:")
    for name, status in services_status.items():
        print(f"  - {name}: {status}")
    
    print("Container is ready to accept requests")
    
    # Log to structured logging service
    if logging_service:
        try:
            from src.services.logging_service import OperationType, LogLevel
            logging_service.log_operation(
                OperationType.SYSTEM,
                "Application startup complete - all services initialized",
                LogLevel.INFO,
                context={
                    'services': services_status,
                    'config': {
                        'web_port': config.WEB_PORT,
                        'max_concurrent_recordings': config.MAX_CONCURRENT_RECORDINGS,
                        'cleanup_after_transfer': config.CLEANUP_AFTER_TRANSFER
                    }
                }
            )
        except Exception as e:
            print(f"Warning: Could not log startup to structured logging: {e}")


if __name__ == "__main__":
    main()