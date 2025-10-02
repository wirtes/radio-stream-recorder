"""
Main entry point for Audio Stream Recorder application.
"""

import logging
import sys
from config import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'{config.LOG_DIR}/app.log')
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Main application entry point."""
    try:
        # Ensure required directories exist
        config.ensure_directories()
        
        # Validate configuration
        config.validate_config()
        
        logger.info("Starting Audio Stream Recorder application")
        logger.info(f"Web interface will be available on port {config.WEB_PORT}")
        
        # TODO: Initialize and start application services
        # This will be implemented in subsequent tasks
        
        logger.info("Application setup complete")
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()