"""
API routes blueprint for REST endpoints with service integration.
"""
from flask import Blueprint, request, jsonify, current_app
from werkzeug.exceptions import BadRequest, NotFound, InternalServerError
from pydantic import ValidationError
from datetime import datetime
import logging
import os

from src.web.models import (
    StreamConfigurationCreate, StreamConfigurationUpdate, StreamConfigurationResponse,
    RecordingScheduleCreate, RecordingScheduleUpdate, RecordingScheduleResponse,
    RecordingSessionResponse, SystemStatusResponse, LogResponse, ErrorResponse,
    ConfigurationImport
)
from src.web.utils import validate_json, handle_validation_error

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)


def get_service(service_name: str):
    """
    Get a service from the service container.
    
    Args:
        service_name: Name of the service to retrieve
        
    Returns:
        Service instance or None if not found
    """
    try:
        service_container = getattr(current_app, 'service_container', None)
        if service_container:
            return service_container.get_service(service_name)
        return None
    except Exception as e:
        logger.error(f"Error getting service {service_name}: {e}")
        return None


def describe_cron_expression(cron_expression):
    """Generate a human-readable description of a cron expression."""
    try:
        parts = cron_expression.strip().split()
        if len(parts) != 5:
            return "Invalid cron expression"
        
        minute, hour, day, month, weekday = parts
        
        description_parts = []
        
        # Handle minute
        if minute == '*':
            minute_desc = "every minute"
        elif minute == '0':
            minute_desc = "at the top of the hour"
        else:
            minute_desc = f"at minute {minute}"
        
        # Handle hour
        if hour == '*':
            hour_desc = "every hour"
        elif ',' in hour:
            hours = hour.split(',')
            hour_desc = f"at {', '.join(hours)} o'clock"
        elif '-' in hour:
            start, end = hour.split('-')
            hour_desc = f"between {start}:00 and {end}:00"
        else:
            hour_desc = f"at {hour}:00"
        
        # Handle day
        if day == '*':
            day_desc = "every day"
        elif ',' in day:
            days = day.split(',')
            day_desc = f"on days {', '.join(days)}"
        else:
            day_desc = f"on day {day}"
        
        # Handle month
        if month == '*':
            month_desc = "every month"
        else:
            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            if month.isdigit() and 1 <= int(month) <= 12:
                month_desc = f"in {month_names[int(month) - 1]}"
            else:
                month_desc = f"in month {month}"
        
        # Handle weekday
        if weekday == '*':
            weekday_desc = ""
        else:
            weekday_names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
            if weekday.isdigit() and 0 <= int(weekday) <= 6:
                weekday_desc = f"on {weekday_names[int(weekday)]}"
            else:
                weekday_desc = f"on weekday {weekday}"
        
        # Combine parts
        if hour == '*' and minute == '*':
            return "Every minute"
        elif day == '*' and month == '*' and weekday == '*':
            return f"Daily {hour_desc} {minute_desc}"
        else:
            parts = [minute_desc, hour_desc, day_desc, month_desc, weekday_desc]
            return ' '.join(filter(None, parts)).capitalize()
            
    except Exception:
        return "Unable to describe cron expression"


# Utility decorator for JSON validation
def validate_request_json(model_class):
    """Decorator to validate request JSON against Pydantic model."""
    def decorator(f):
        def wrapper(*args, **kwargs):
            try:
                if request.is_json:
                    data = model_class(**request.get_json())
                    return f(data, *args, **kwargs)
                else:
                    raise BadRequest("Request must contain valid JSON")
            except ValidationError as e:
                return handle_validation_error(e)
            except Exception as e:
                logger.error(f"Validation error in {f.__name__}: {str(e)}")
                raise BadRequest(f"Invalid request data: {str(e)}")
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator


# Health check endpoint
@api_bp.route('/health')
def health_check():
    """Health check endpoint for container monitoring."""
    return jsonify({
        'status': 'healthy',
        'service': 'audio-stream-recorder',
        'version': '1.0.0'
    })


# Stream Configuration API endpoints
@api_bp.route('/streams', methods=['GET'])
def get_streams():
    """Get all stream configurations."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ConfigurationRepository
        
        db_manager = DatabaseManager()
        config_repo = ConfigurationRepository(db_manager)
        
        # Get query parameters
        skip = int(request.args.get('skip', 0))
        limit = int(request.args.get('limit', 100))
        search = request.args.get('search', '').strip()
        
        if search:
            streams = config_repo.search(search, skip=skip, limit=limit)
        else:
            streams = config_repo.get_all(skip=skip, limit=limit)
        
        # Convert to response models
        response_data = [StreamConfigurationResponse.from_orm(stream) for stream in streams]
        return jsonify([stream.dict() for stream in response_data])
        
    except Exception as e:
        logger.error(f"Error getting streams: {str(e)}")
        raise InternalServerError(f"Failed to retrieve streams: {str(e)}")


@api_bp.route('/streams', methods=['POST'])
@validate_request_json(StreamConfigurationCreate)
def create_stream(data: StreamConfigurationCreate):
    """Create a new stream configuration."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ConfigurationRepository
        
        db_manager = DatabaseManager()
        config_repo = ConfigurationRepository(db_manager)
        
        # Create the stream configuration
        stream = config_repo.create(data)
        
        # Convert to response model
        response_data = StreamConfigurationResponse.from_orm(stream)
        return jsonify(response_data.dict()), 201
        
    except ValueError as e:
        logger.warning(f"Validation error creating stream: {str(e)}")
        raise BadRequest(str(e))
    except Exception as e:
        logger.error(f"Error creating stream: {str(e)}")
        raise InternalServerError(f"Failed to create stream: {str(e)}")


@api_bp.route('/streams/<int:stream_id>', methods=['GET'])
def get_stream(stream_id):
    """Get a specific stream configuration."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ConfigurationRepository
        
        db_manager = DatabaseManager()
        config_repo = ConfigurationRepository(db_manager)
        
        stream = config_repo.get_by_id(stream_id)
        if not stream:
            raise NotFound(f"Stream configuration with ID {stream_id} not found")
        
        # Convert to response model
        response_data = StreamConfigurationResponse.from_orm(stream)
        return jsonify(response_data.dict())
        
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error getting stream {stream_id}: {str(e)}")
        raise InternalServerError(f"Failed to retrieve stream: {str(e)}")


@api_bp.route('/streams/<int:stream_id>', methods=['PUT'])
@validate_request_json(StreamConfigurationUpdate)
def update_stream(data: StreamConfigurationUpdate, stream_id):
    """Update an existing stream configuration."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ConfigurationRepository
        
        db_manager = DatabaseManager()
        config_repo = ConfigurationRepository(db_manager)
        
        stream = config_repo.update(stream_id, data)
        if not stream:
            raise NotFound(f"Stream configuration with ID {stream_id} not found")
        
        # Convert to response model
        response_data = StreamConfigurationResponse.from_orm(stream)
        return jsonify(response_data.dict())
        
    except ValueError as e:
        logger.warning(f"Validation error updating stream {stream_id}: {str(e)}")
        raise BadRequest(str(e))
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error updating stream {stream_id}: {str(e)}")
        raise InternalServerError(f"Failed to update stream: {str(e)}")


@api_bp.route('/streams/<int:stream_id>', methods=['DELETE'])
def delete_stream(stream_id):
    """Delete a stream configuration."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ConfigurationRepository
        
        db_manager = DatabaseManager()
        config_repo = ConfigurationRepository(db_manager)
        
        success = config_repo.delete(stream_id)
        if not success:
            raise NotFound(f"Stream configuration with ID {stream_id} not found")
        
        return jsonify({'message': f'Stream configuration {stream_id} deleted successfully'})
        
    except ValueError as e:
        logger.warning(f"Cannot delete stream {stream_id}: {str(e)}")
        raise BadRequest(str(e))
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error deleting stream {stream_id}: {str(e)}")
        raise InternalServerError(f"Failed to delete stream: {str(e)}")


@api_bp.route('/streams/<int:stream_id>/test', methods=['POST'])
def test_stream_connection(stream_id):
    """Test stream URL connection."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ConfigurationRepository
        from src.services.stream_recorder import StreamRecorder
        
        db_manager = DatabaseManager()
        config_repo = ConfigurationRepository(db_manager)
        
        stream = config_repo.get_by_id(stream_id)
        if not stream:
            raise NotFound(f"Stream configuration with ID {stream_id} not found")
        
        # Test the stream connection
        recorder = StreamRecorder()
        test_result = recorder.test_stream_connection(stream.stream_url)
        
        return jsonify({
            'stream_id': stream_id,
            'stream_url': stream.stream_url,
            'connection_test': test_result
        })
        
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error testing stream {stream_id}: {str(e)}")
        return jsonify({
            'stream_id': stream_id,
            'connection_test': {
                'success': False,
                'error': str(e),
                'message': 'Failed to test stream connection'
            }
        }), 500


@api_bp.route('/streams/test-url', methods=['POST'])
def test_stream_url():
    """Test a stream URL without saving it."""
    try:
        data = request.get_json()
        if not data or 'stream_url' not in data:
            raise BadRequest("stream_url is required")
        
        stream_url = data['stream_url']
        
        from src.services.stream_recorder import StreamRecorder
        recorder = StreamRecorder()
        test_result = recorder.test_stream_connection(stream_url)
        
        return jsonify({
            'stream_url': stream_url,
            'connection_test': test_result
        })
        
    except BadRequest:
        raise
    except Exception as e:
        logger.error(f"Error testing stream URL: {str(e)}")
        return jsonify({
            'stream_url': data.get('stream_url', 'unknown'),
            'connection_test': {
                'success': False,
                'error': str(e),
                'message': 'Failed to test stream URL'
            }
        }), 500


@api_bp.route('/streams/<int:stream_id>/artwork', methods=['POST'])
def upload_stream_artwork(stream_id):
    """Upload artwork for a stream configuration."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ConfigurationRepository
        from src.web.utils import validate_file_upload, sanitize_filename
        from src.config import Config
        import os
        from werkzeug.utils import secure_filename
        
        db_manager = DatabaseManager()
        config_repo = ConfigurationRepository(db_manager)
        
        # Check if stream exists
        stream = config_repo.get_by_id(stream_id)
        if not stream:
            raise NotFound(f"Stream configuration with ID {stream_id} not found")
        
        # Check if file was uploaded
        if 'artwork' not in request.files:
            raise BadRequest("No artwork file provided")
        
        file = request.files['artwork']
        
        # Validate file
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
        validate_file_upload(file, allowed_extensions, Config.MAX_ARTWORK_SIZE_MB)
        
        # Generate secure filename
        filename = secure_filename(file.filename)
        filename = sanitize_filename(filename)
        
        # Add stream ID to filename to avoid conflicts
        name, ext = os.path.splitext(filename)
        filename = f"stream_{stream_id}_{name}{ext}"
        
        # Ensure artwork directory exists
        Config.ensure_directories()
        artwork_path = os.path.join(Config.ARTWORK_DIR, filename)
        
        # Save file
        file.save(artwork_path)
        
        # Update stream configuration with artwork path
        from src.web.models import StreamConfigurationUpdate
        update_data = StreamConfigurationUpdate(artwork_path=artwork_path)
        updated_stream = config_repo.update(stream_id, update_data)
        
        return jsonify({
            'stream_id': stream_id,
            'artwork_path': artwork_path,
            'filename': filename,
            'file_size': os.path.getsize(artwork_path),
            'message': 'Artwork uploaded successfully'
        })
        
    except (BadRequest, NotFound):
        raise
    except Exception as e:
        logger.error(f"Error uploading artwork for stream {stream_id}: {str(e)}")
        raise InternalServerError(f"Failed to upload artwork: {str(e)}")


@api_bp.route('/streams/<int:stream_id>/artwork', methods=['DELETE'])
def delete_stream_artwork(stream_id):
    """Delete artwork for a stream configuration."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ConfigurationRepository
        import os
        
        db_manager = DatabaseManager()
        config_repo = ConfigurationRepository(db_manager)
        
        # Check if stream exists
        stream = config_repo.get_by_id(stream_id)
        if not stream:
            raise NotFound(f"Stream configuration with ID {stream_id} not found")
        
        if not stream.artwork_path:
            raise BadRequest("Stream has no artwork to delete")
        
        # Delete file if it exists
        if os.path.exists(stream.artwork_path):
            os.remove(stream.artwork_path)
        
        # Update stream configuration to remove artwork path
        from src.web.models import StreamConfigurationUpdate
        update_data = StreamConfigurationUpdate(artwork_path=None)
        updated_stream = config_repo.update(stream_id, update_data)
        
        return jsonify({
            'stream_id': stream_id,
            'message': 'Artwork deleted successfully'
        })
        
    except (BadRequest, NotFound):
        raise
    except Exception as e:
        logger.error(f"Error deleting artwork for stream {stream_id}: {str(e)}")
        raise InternalServerError(f"Failed to delete artwork: {str(e)}")


# Recording Schedule API endpoints
@api_bp.route('/schedules', methods=['GET'])
def get_schedules():
    """Get all recording schedules."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ScheduleRepository
        
        db_manager = DatabaseManager()
        schedule_repo = ScheduleRepository(db_manager)
        
        # Get query parameters
        skip = int(request.args.get('skip', 0))
        limit = int(request.args.get('limit', 100))
        active_only = request.args.get('active', '').lower() == 'true'
        stream_config_id = request.args.get('stream_config_id')
        
        if stream_config_id:
            # Get schedules for specific stream
            schedules = schedule_repo.get_by_stream_config(int(stream_config_id))
        elif active_only:
            # Get only active schedules
            schedules = schedule_repo.get_active_schedules()
        else:
            # Get all schedules
            schedules = schedule_repo.get_all(skip=skip, limit=limit)
        
        # Convert to response models
        response_data = [RecordingScheduleResponse.from_orm(schedule) for schedule in schedules]
        return jsonify([schedule.dict() for schedule in response_data])
        
    except Exception as e:
        logger.error(f"Error getting schedules: {str(e)}")
        raise InternalServerError(f"Failed to retrieve schedules: {str(e)}")


@api_bp.route('/schedules', methods=['POST'])
@validate_request_json(RecordingScheduleCreate)
def create_schedule(data: RecordingScheduleCreate):
    """Create a new recording schedule."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ScheduleRepository, ConfigurationRepository
        
        db_manager = DatabaseManager()
        schedule_repo = ScheduleRepository(db_manager)
        config_repo = ConfigurationRepository(db_manager)
        
        # Validate that the stream configuration exists
        stream_config = config_repo.get_by_id(data.stream_config_id)
        if not stream_config:
            raise BadRequest(f"Stream configuration with ID {data.stream_config_id} not found")
        
        # Create the schedule
        schedule = schedule_repo.create(data)
        
        # Convert to response model
        response_data = RecordingScheduleResponse.from_orm(schedule)
        return jsonify(response_data.dict()), 201
        
    except ValueError as e:
        logger.warning(f"Validation error creating schedule: {str(e)}")
        raise BadRequest(str(e))
    except Exception as e:
        logger.error(f"Error creating schedule: {str(e)}")
        raise InternalServerError(f"Failed to create schedule: {str(e)}")


@api_bp.route('/schedules/<int:schedule_id>', methods=['GET'])
def get_schedule(schedule_id):
    """Get a specific recording schedule."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ScheduleRepository
        
        db_manager = DatabaseManager()
        schedule_repo = ScheduleRepository(db_manager)
        
        schedule = schedule_repo.get_by_id(schedule_id)
        if not schedule:
            raise NotFound(f"Recording schedule with ID {schedule_id} not found")
        
        # Convert to response model
        response_data = RecordingScheduleResponse.from_orm(schedule)
        return jsonify(response_data.dict())
        
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error getting schedule {schedule_id}: {str(e)}")
        raise InternalServerError(f"Failed to retrieve schedule: {str(e)}")


@api_bp.route('/schedules/<int:schedule_id>', methods=['PUT'])
@validate_request_json(RecordingScheduleUpdate)
def update_schedule(data: RecordingScheduleUpdate, schedule_id):
    """Update an existing recording schedule."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ScheduleRepository
        
        db_manager = DatabaseManager()
        schedule_repo = ScheduleRepository(db_manager)
        
        schedule = schedule_repo.update(schedule_id, data)
        if not schedule:
            raise NotFound(f"Recording schedule with ID {schedule_id} not found")
        
        # Convert to response model
        response_data = RecordingScheduleResponse.from_orm(schedule)
        return jsonify(response_data.dict())
        
    except ValueError as e:
        logger.warning(f"Validation error updating schedule {schedule_id}: {str(e)}")
        raise BadRequest(str(e))
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error updating schedule {schedule_id}: {str(e)}")
        raise InternalServerError(f"Failed to update schedule: {str(e)}")


@api_bp.route('/schedules/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    """Delete a recording schedule."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ScheduleRepository
        
        db_manager = DatabaseManager()
        schedule_repo = ScheduleRepository(db_manager)
        
        success = schedule_repo.delete(schedule_id)
        if not success:
            raise NotFound(f"Recording schedule with ID {schedule_id} not found")
        
        return jsonify({'message': f'Recording schedule {schedule_id} deleted successfully'})
        
    except ValueError as e:
        logger.warning(f"Cannot delete schedule {schedule_id}: {str(e)}")
        raise BadRequest(str(e))
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error deleting schedule {schedule_id}: {str(e)}")
        raise InternalServerError(f"Failed to delete schedule: {str(e)}")


@api_bp.route('/schedules/validate-cron', methods=['POST'])
def validate_cron_expression():
    """Validate a cron expression and calculate next run times."""
    try:
        data = request.get_json()
        if not data or 'cron_expression' not in data:
            raise BadRequest("cron_expression is required")
        
        cron_expression = data['cron_expression']
        
        from croniter import croniter
        from datetime import datetime, timedelta
        
        # Validate cron expression
        if not croniter.is_valid(cron_expression):
            return jsonify({
                'valid': False,
                'error': 'Invalid cron expression format'
            }), 400
        
        # Calculate next few run times
        base_time = datetime.utcnow()
        cron = croniter(cron_expression, base_time)
        
        next_runs = []
        for i in range(5):  # Get next 5 run times
            next_run = cron.get_next(datetime)
            next_runs.append(next_run.isoformat())
        
        return jsonify({
            'valid': True,
            'cron_expression': cron_expression,
            'next_run_time': next_runs[0],
            'next_runs': next_runs,
            'description': describe_cron_expression(cron_expression)
        })
        
    except BadRequest:
        raise
    except Exception as e:
        logger.error(f"Error validating cron expression: {str(e)}")
        return jsonify({
            'valid': False,
            'error': str(e)
        }), 400


@api_bp.route('/schedules/<int:schedule_id>/activate', methods=['POST'])
def activate_schedule(schedule_id):
    """Activate a recording schedule."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ScheduleRepository
        from src.web.models import RecordingScheduleUpdate
        
        db_manager = DatabaseManager()
        schedule_repo = ScheduleRepository(db_manager)
        
        # Update schedule to active
        update_data = RecordingScheduleUpdate(is_active=True)
        schedule = schedule_repo.update(schedule_id, update_data)
        
        if not schedule:
            raise NotFound(f"Recording schedule with ID {schedule_id} not found")
        
        # Update next run time
        schedule_repo.update_next_run_time(schedule_id)
        
        return jsonify({
            'schedule_id': schedule_id,
            'is_active': True,
            'message': 'Schedule activated successfully'
        })
        
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error activating schedule {schedule_id}: {str(e)}")
        raise InternalServerError(f"Failed to activate schedule: {str(e)}")


@api_bp.route('/schedules/<int:schedule_id>/deactivate', methods=['POST'])
def deactivate_schedule(schedule_id):
    """Deactivate a recording schedule."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ScheduleRepository
        from src.web.models import RecordingScheduleUpdate
        
        db_manager = DatabaseManager()
        schedule_repo = ScheduleRepository(db_manager)
        
        # Update schedule to inactive
        update_data = RecordingScheduleUpdate(is_active=False)
        schedule = schedule_repo.update(schedule_id, update_data)
        
        if not schedule:
            raise NotFound(f"Recording schedule with ID {schedule_id} not found")
        
        return jsonify({
            'schedule_id': schedule_id,
            'is_active': False,
            'message': 'Schedule deactivated successfully'
        })
        
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error deactivating schedule {schedule_id}: {str(e)}")
        raise InternalServerError(f"Failed to deactivate schedule: {str(e)}")


@api_bp.route('/schedules/<int:schedule_id>/next-run', methods=['GET'])
def get_schedule_next_run(schedule_id):
    """Get the next run time for a schedule."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ScheduleRepository
        
        db_manager = DatabaseManager()
        schedule_repo = ScheduleRepository(db_manager)
        
        schedule = schedule_repo.get_by_id(schedule_id)
        if not schedule:
            raise NotFound(f"Recording schedule with ID {schedule_id} not found")
        
        # Recalculate next run time
        updated_schedule = schedule_repo.update_next_run_time(schedule_id)
        
        return jsonify({
            'schedule_id': schedule_id,
            'next_run_time': updated_schedule.next_run_time.isoformat() if updated_schedule.next_run_time else None,
            'is_active': updated_schedule.is_active,
            'cron_expression': updated_schedule.cron_expression
        })
        
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error getting next run time for schedule {schedule_id}: {str(e)}")
        raise InternalServerError(f"Failed to get next run time: {str(e)}")


# System Monitoring API endpoints
@api_bp.route('/system/status')
def get_system_status():
    """Get current system status with integrated service information."""
    try:
        # Get services from service container
        monitoring_service = get_service('monitoring')
        workflow_coordinator = get_service('workflow_coordinator')
        
        if not monitoring_service:
            # Fallback if monitoring service not available
            return jsonify({
                'status': 'unknown',
                'message': 'Monitoring service not available',
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'active_recordings': 0
            })
        
        # Get current metrics and health status
        current_metrics = monitoring_service.get_current_metrics()
        health_status = monitoring_service.get_health_status()
        
        # Get active recordings from workflow coordinator
        active_recordings_count = 0
        if workflow_coordinator:
            active_sessions = workflow_coordinator.get_active_sessions()
            active_recordings_count = len(active_sessions)
        
        # Get database statistics
        from src.models.database import DatabaseManager
        from src.models.repositories import SessionRepository
        db_manager = DatabaseManager()
        session_repo = SessionRepository(db_manager)
        session_stats = session_repo.get_statistics()
        
        status_data = {
            'status': health_status['status'],
            'message': health_status['message'],
            'timestamp': health_status['timestamp'],
            'uptime_seconds': current_metrics.uptime_seconds,
            'active_recordings': active_recordings_count,
            'total_recordings': session_stats.get('total_sessions', 0),
            'cpu_percent': current_metrics.cpu_percent,
            'memory_percent': current_metrics.memory_percent,
            'memory_used_mb': current_metrics.memory_used_mb,
            'memory_total_mb': current_metrics.memory_total_mb,
            'disk_percent': current_metrics.disk_percent,
            'disk_used_gb': current_metrics.disk_used_gb,
            'disk_total_gb': current_metrics.disk_total_gb,
            'disk_free_gb': current_metrics.disk_free_gb,
            'components': health_status['components']
        }
        
        return jsonify(status_data)
        
    except Exception as e:
        logger.error(f"Error getting system status: {str(e)}")
        # Return basic status even if detailed monitoring fails
        return jsonify({
            'status': 'unknown',
            'message': f'Error retrieving system status: {str(e)}',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'uptime_seconds': 0,
            'active_recordings': 0,
            'total_recordings': 0,
            'cpu_percent': 0,
            'memory_percent': 0,
            'disk_percent': 0,
            'error': str(e)
        }), 500


@api_bp.route('/system/health')
def get_system_health():
    """Get detailed system health check results."""
    try:
        from src.services.monitoring_service import get_monitoring_service
        
        monitoring_service = get_monitoring_service()
        health_status = monitoring_service.get_health_status()
        
        return jsonify(health_status)
        
    except Exception as e:
        logger.error(f"Error getting system health: {str(e)}")
        return jsonify({
            'status': 'unknown',
            'message': f'Error retrieving health status: {str(e)}',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'components': {}
        }), 500


@api_bp.route('/system/metrics')
def get_system_metrics():
    """Get system performance metrics."""
    try:
        from src.services.monitoring_service import get_monitoring_service
        
        monitoring_service = get_monitoring_service()
        
        # Get query parameters
        hours = int(request.args.get('hours', 1))
        summary = request.args.get('summary', 'false').lower() == 'true'
        
        if summary:
            # Return performance summary
            performance_summary = monitoring_service.get_performance_summary()
            return jsonify(performance_summary)
        else:
            # Return metrics history
            metrics_history = monitoring_service.get_metrics_history(hours=hours)
            return jsonify({
                'metrics': [metric.to_dict() for metric in metrics_history],
                'count': len(metrics_history),
                'hours': hours
            })
        
    except Exception as e:
        logger.error(f"Error getting system metrics: {str(e)}")
        return jsonify({
            'error': str(e),
            'metrics': [],
            'count': 0
        }), 500


@api_bp.route('/system/metrics/current')
def get_current_metrics():
    """Get current system metrics snapshot."""
    try:
        from src.services.monitoring_service import get_monitoring_service
        
        monitoring_service = get_monitoring_service()
        current_metrics = monitoring_service.get_current_metrics()
        
        return jsonify(current_metrics.to_dict())
        
    except Exception as e:
        logger.error(f"Error getting current metrics: {str(e)}")
        return jsonify({
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }), 500


@api_bp.route('/system/logs')
def get_logs():
    """Get system logs with optional filtering."""
    try:
        from src.services.logging_service import get_logging_service, OperationType
        from datetime import datetime
        
        # Get query parameters
        operation_type = request.args.get('operation_type', '').lower()
        limit = int(request.args.get('limit', 100))
        
        # Map operation type string to enum
        operation_filter = None
        if operation_type:
            operation_map = {
                'recording': OperationType.RECORDING,
                'processing': OperationType.PROCESSING,
                'transfer': OperationType.TRANSFER,
                'scheduling': OperationType.SCHEDULING,
                'web_request': OperationType.WEB_REQUEST,
                'system': OperationType.SYSTEM,
                'database': OperationType.DATABASE,
                'configuration': OperationType.CONFIGURATION,
                'error': OperationType.ERROR
            }
            operation_filter = operation_map.get(operation_type)
        
        logging_service = get_logging_service()
        log_entries = logging_service.get_recent_logs(
            operation_type=operation_filter,
            limit=limit
        )
        
        return jsonify({
            'logs': log_entries,
            'count': len(log_entries),
            'operation_type': operation_type or 'all',
            'limit': limit
        })
        
    except Exception as e:
        logger.error(f"Error getting logs: {str(e)}")
        return jsonify({
            'error': str(e),
            'logs': [],
            'count': 0
        }), 500


@api_bp.route('/sessions')
def get_recording_sessions():
    """Get recording sessions with optional filtering."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import SessionRepository
        
        db_manager = DatabaseManager()
        session_repo = SessionRepository(db_manager)
        
        # Get query parameters
        skip = int(request.args.get('skip', 0))
        limit = int(request.args.get('limit', 50))
        status = request.args.get('status')
        schedule_id = request.args.get('schedule_id')
        recent_days = request.args.get('recent_days')
        
        if schedule_id:
            # Get sessions for specific schedule
            sessions = session_repo.get_by_schedule(int(schedule_id), skip=skip, limit=limit)
        elif status:
            # Get sessions by status
            from src.models.database import RecordingStatus
            try:
                status_enum = RecordingStatus(status.lower())
                sessions = session_repo.get_by_status(status_enum)
                # Apply pagination manually for status filter
                sessions = sessions[skip:skip + limit]
            except ValueError:
                raise BadRequest(f"Invalid status: {status}")
        elif recent_days:
            # Get recent sessions
            sessions = session_repo.get_recent_sessions(days=int(recent_days), limit=limit)
        else:
            # Get all sessions
            sessions = session_repo.get_all(skip=skip, limit=limit)
        
        # Convert to response models
        response_data = [RecordingSessionResponse.from_orm(session) for session in sessions]
        return jsonify([session.dict() for session in response_data])
        
    except BadRequest:
        raise
    except Exception as e:
        logger.error(f"Error getting recording sessions: {str(e)}")
        raise InternalServerError(f"Failed to retrieve recording sessions: {str(e)}")


@api_bp.route('/sessions/<int:session_id>')
def get_recording_session(session_id):
    """Get a specific recording session."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import SessionRepository
        
        db_manager = DatabaseManager()
        session_repo = SessionRepository(db_manager)
        
        session = session_repo.get_by_id(session_id)
        if not session:
            raise NotFound(f"Recording session with ID {session_id} not found")
        
        # Convert to response model
        response_data = RecordingSessionResponse.from_orm(session)
        return jsonify(response_data.dict())
        
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error getting recording session {session_id}: {str(e)}")
        raise InternalServerError(f"Failed to retrieve recording session: {str(e)}")


@api_bp.route('/sessions/statistics')
def get_session_statistics():
    """Get recording session statistics."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import SessionRepository
        
        db_manager = DatabaseManager()
        session_repo = SessionRepository(db_manager)
        
        stats = session_repo.get_statistics()
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error getting session statistics: {str(e)}")
        raise InternalServerError(f"Failed to retrieve session statistics: {str(e)}")


@api_bp.route('/sessions/active')
def get_active_sessions():
    """Get currently active recording sessions."""
    try:
        workflow_coordinator = get_service('workflow_coordinator')
        if not workflow_coordinator:
            return jsonify({
                'active_sessions': [],
                'message': 'Workflow coordinator not available'
            })
        
        active_sessions = workflow_coordinator.get_active_sessions()
        
        return jsonify({
            'active_sessions': list(active_sessions.values()),
            'count': len(active_sessions)
        })
        
    except Exception as e:
        logger.error(f"Error getting active sessions: {str(e)}")
        raise InternalServerError(f"Failed to retrieve active sessions: {str(e)}")


@api_bp.route('/sessions/<int:session_id>/stop', methods=['POST'])
def stop_recording_session(session_id):
    """Stop an active recording session."""
    try:
        workflow_coordinator = get_service('workflow_coordinator')
        if not workflow_coordinator:
            raise InternalServerError("Workflow coordinator not available")
        
        success = workflow_coordinator.stop_session(session_id)
        
        if success:
            return jsonify({
                'message': f'Recording session {session_id} stopped successfully',
                'session_id': session_id
            })
        else:
            raise NotFound(f"Active recording session {session_id} not found")
        
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error stopping session {session_id}: {str(e)}")
        raise InternalServerError(f"Failed to stop recording session: {str(e)}")


@api_bp.route('/system/health')
def health_check_detailed():
    """Detailed health check for container orchestration."""
    try:
        import psutil
        from src.models.database import DatabaseManager
        
        health_status = {
            'status': 'healthy',
            'checks': {},
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Check database connectivity
        try:
            from sqlalchemy import text
            db_manager = DatabaseManager()
            with db_manager.get_session() as session:
                session.execute(text('SELECT 1'))
            health_status['checks']['database'] = {'status': 'healthy', 'message': 'Database connection OK'}
        except Exception as e:
            health_status['checks']['database'] = {'status': 'unhealthy', 'message': f'Database error: {str(e)}'}
            health_status['status'] = 'unhealthy'
        
        # Check disk space
        try:
            disk_usage = psutil.disk_usage('/')
            free_percent = (disk_usage.free / disk_usage.total) * 100
            if free_percent < 10:
                health_status['checks']['disk'] = {'status': 'warning', 'message': f'Low disk space: {free_percent:.1f}% free'}
                if health_status['status'] == 'healthy':
                    health_status['status'] = 'warning'
            elif free_percent < 5:
                health_status['checks']['disk'] = {'status': 'unhealthy', 'message': f'Critical disk space: {free_percent:.1f}% free'}
                health_status['status'] = 'unhealthy'
            else:
                health_status['checks']['disk'] = {'status': 'healthy', 'message': f'Disk space OK: {free_percent:.1f}% free'}
        except Exception as e:
            health_status['checks']['disk'] = {'status': 'unknown', 'message': f'Cannot check disk space: {str(e)}'}
        
        # Check memory usage
        try:
            memory = psutil.virtual_memory()
            if memory.percent > 90:
                health_status['checks']['memory'] = {'status': 'warning', 'message': f'High memory usage: {memory.percent:.1f}%'}
                if health_status['status'] == 'healthy':
                    health_status['status'] = 'warning'
            elif memory.percent > 95:
                health_status['checks']['memory'] = {'status': 'unhealthy', 'message': f'Critical memory usage: {memory.percent:.1f}%'}
                health_status['status'] = 'unhealthy'
            else:
                health_status['checks']['memory'] = {'status': 'healthy', 'message': f'Memory usage OK: {memory.percent:.1f}%'}
        except Exception as e:
            health_status['checks']['memory'] = {'status': 'unknown', 'message': f'Cannot check memory: {str(e)}'}
        
        # Check if required directories exist
        try:
            from src.config import Config
            required_dirs = [Config.RECORDINGS_DIR, Config.ARTWORK_DIR, Config.LOG_DIR]
            missing_dirs = [d for d in required_dirs if not os.path.exists(d)]
            
            if missing_dirs:
                health_status['checks']['directories'] = {
                    'status': 'warning', 
                    'message': f'Missing directories: {", ".join(missing_dirs)}'
                }
                if health_status['status'] == 'healthy':
                    health_status['status'] = 'warning'
            else:
                health_status['checks']['directories'] = {'status': 'healthy', 'message': 'All required directories exist'}
        except Exception as e:
            health_status['checks']['directories'] = {'status': 'unknown', 'message': f'Cannot check directories: {str(e)}'}
        
        # Return appropriate HTTP status code
        if health_status['status'] == 'healthy':
            return jsonify(health_status), 200
        elif health_status['status'] == 'warning':
            return jsonify(health_status), 200  # Still OK but with warnings
        else:
            return jsonify(health_status), 503  # Service unavailable
            
    except Exception as e:
        logger.error(f"Error in health check: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 503


@api_bp.route('/system/metrics/detailed')
def get_detailed_system_metrics():
    """Get detailed system metrics."""
    try:
        import psutil
        from datetime import datetime
        
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        # Memory metrics
        memory = psutil.virtual_memory()
        
        # Disk metrics
        disk_usage = psutil.disk_usage('/')
        
        # Network metrics (if available)
        try:
            network = psutil.net_io_counters()
            network_metrics = {
                'bytes_sent': network.bytes_sent,
                'bytes_recv': network.bytes_recv,
                'packets_sent': network.packets_sent,
                'packets_recv': network.packets_recv
            }
        except Exception:
            network_metrics = None
        
        metrics = {
            'timestamp': datetime.utcnow().isoformat(),
            'cpu': {
                'usage_percent': cpu_percent,
                'count': cpu_count
            },
            'memory': {
                'total_gb': memory.total / (1024**3),
                'available_gb': memory.available / (1024**3),
                'used_gb': memory.used / (1024**3),
                'usage_percent': memory.percent
            },
            'disk': {
                'total_gb': disk_usage.total / (1024**3),
                'free_gb': disk_usage.free / (1024**3),
                'used_gb': disk_usage.used / (1024**3),
                'usage_percent': (disk_usage.used / disk_usage.total) * 100
            },
            'network': network_metrics
        }
        
        return jsonify(metrics)
        
    except Exception as e:
        logger.error(f"Error getting system metrics: {str(e)}")
        raise InternalServerError(f"Failed to retrieve system metrics: {str(e)}")


# Error handlers for API blueprint
@api_bp.errorhandler(ValidationError)
def handle_validation_error_api(e):
    """Handle Pydantic validation errors."""
    return jsonify({
        'error': 'Validation Error',
        'message': 'Invalid request data',
        'details': e.errors(),
        'status_code': 400
    }), 400


@api_bp.errorhandler(BadRequest)
def handle_bad_request_api(e):
    """Handle bad request errors."""
    return jsonify({
        'error': 'Bad Request',
        'message': e.description,
        'status_code': 400
    }), 400


@api_bp.errorhandler(NotFound)
def handle_not_found_api(e):
    """Handle not found errors."""
    return jsonify({
        'error': 'Not Found',
        'message': e.description,
        'status_code': 404
    }), 404


@api_bp.errorhandler(InternalServerError)
def handle_internal_error_api(e):
    """Handle internal server errors."""
    logger.error(f"Internal server error: {str(e)}")
    return jsonify({
        'error': 'Internal Server Error',
        'message': 'An unexpected error occurred',
        'status_code': 500
    }), 500


@api_bp.route('/streams/export', methods=['GET'])
def export_stream_configurations():
    """Export all stream configurations."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ConfigurationRepository, ScheduleRepository
        from src.web.models import ConfigurationExport
        from datetime import datetime
        
        db_manager = DatabaseManager()
        config_repo = ConfigurationRepository(db_manager)
        schedule_repo = ScheduleRepository(db_manager)
        
        # Get all streams and schedules
        streams = config_repo.get_all(limit=1000)  # Get all streams
        all_schedules = schedule_repo.get_all(limit=1000)  # Get all schedules
        
        # Convert to response models
        stream_responses = [StreamConfigurationResponse.from_orm(stream) for stream in streams]
        schedule_responses = [RecordingScheduleResponse.from_orm(schedule) for schedule in all_schedules]
        
        # Create export data
        export_data = ConfigurationExport(
            streams=[stream.dict() for stream in stream_responses],
            schedules=[schedule.dict() for schedule in schedule_responses],
            exported_at=datetime.utcnow()
        )
        
        return jsonify(export_data.dict())
        
    except Exception as e:
        logger.error(f"Error exporting configurations: {str(e)}")
        raise InternalServerError(f"Failed to export configurations: {str(e)}")


@api_bp.route('/streams/import', methods=['POST'])
@validate_request_json(ConfigurationImport)
def import_stream_configurations(data: ConfigurationImport):
    """Import stream configurations."""
    try:
        from src.models.database import DatabaseManager
        from src.models.repositories import ConfigurationRepository, ScheduleRepository
        
        db_manager = DatabaseManager()
        config_repo = ConfigurationRepository(db_manager)
        schedule_repo = ScheduleRepository(db_manager)
        
        imported_streams = []
        imported_schedules = []
        errors = []
        
        # Import streams
        for stream_data in data.streams:
            try:
                stream = config_repo.create(stream_data)
                imported_streams.append(stream.id)
            except ValueError as e:
                errors.append(f"Stream '{stream_data.name}': {str(e)}")
        
        # Import schedules (need to map to new stream IDs if necessary)
        for schedule_data in data.schedules:
            try:
                # Validate that the stream_config_id exists
                stream_exists = config_repo.get_by_id(schedule_data['stream_config_id'])
                if not stream_exists:
                    errors.append(f"Schedule for stream ID {schedule_data['stream_config_id']}: Stream not found")
                    continue
                
                from src.web.models import RecordingScheduleCreate
                schedule_create = RecordingScheduleCreate(**schedule_data)
                schedule = schedule_repo.create(schedule_create)
                imported_schedules.append(schedule.id)
            except (ValueError, KeyError) as e:
                errors.append(f"Schedule: {str(e)}")
        
        return jsonify({
            'imported_streams': len(imported_streams),
            'imported_schedules': len(imported_schedules),
            'stream_ids': imported_streams,
            'schedule_ids': imported_schedules,
            'errors': errors,
            'message': f'Import completed: {len(imported_streams)} streams, {len(imported_schedules)} schedules'
        })
        
    except ValidationError as e:
        return handle_validation_error(e)
    except Exception as e:
        logger.error(f"Error importing configurations: {str(e)}")
        raise InternalServerError(f"Failed to import configurations: {str(e)}")

# Configuration Backup and Restore API endpoints
@api_bp.route('/backup/create', methods=['POST'])
def create_backup():
    """Create a configuration backup."""
    try:
        from src.services.backup_service import BackupService
        from src.models.database import DatabaseManager
        
        db_manager = DatabaseManager()
        backup_service = BackupService(db_manager)
        
        # Get request parameters
        data = request.get_json() or {}
        backup_name = data.get('backup_name')
        include_artwork = data.get('include_artwork', True)
        
        # Create backup
        backup_info = backup_service.create_backup(
            backup_name=backup_name,
            include_artwork=include_artwork
        )
        
        if backup_info['success']:
            return jsonify(backup_info), 201
        else:
            return jsonify(backup_info), 500
            
    except Exception as e:
        logger.error(f"Error creating backup: {str(e)}")
        raise InternalServerError(f"Failed to create backup: {str(e)}")


@api_bp.route('/backup/list', methods=['GET'])
def list_backups():
    """List all available backups."""
    try:
        from src.services.backup_service import BackupService
        from src.models.database import DatabaseManager
        
        db_manager = DatabaseManager()
        backup_service = BackupService(db_manager)
        
        backups = backup_service.list_backups()
        return jsonify(backups)
        
    except Exception as e:
        logger.error(f"Error listing backups: {str(e)}")
        raise InternalServerError(f"Failed to list backups: {str(e)}")


@api_bp.route('/backup/restore', methods=['POST'])
def restore_backup():
    """Restore configuration from a backup."""
    try:
        from src.services.backup_service import BackupService
        from src.models.database import DatabaseManager
        
        db_manager = DatabaseManager()
        backup_service = BackupService(db_manager)
        
        # Get request parameters
        data = request.get_json()
        if not data or 'backup_filename' not in data:
            raise BadRequest("backup_filename is required")
        
        backup_filename = data['backup_filename']
        overwrite_existing = data.get('overwrite_existing', False)
        
        # Restore backup
        restore_info = backup_service.restore_backup(
            backup_filename=backup_filename,
            overwrite_existing=overwrite_existing
        )
        
        if restore_info['success']:
            return jsonify(restore_info)
        else:
            return jsonify(restore_info), 400
            
    except BadRequest:
        raise
    except Exception as e:
        logger.error(f"Error restoring backup: {str(e)}")
        raise InternalServerError(f"Failed to restore backup: {str(e)}")


@api_bp.route('/backup/validate', methods=['POST'])
def validate_backup():
    """Validate a backup file."""
    try:
        from src.services.backup_service import BackupService
        from src.models.database import DatabaseManager
        
        db_manager = DatabaseManager()
        backup_service = BackupService(db_manager)
        
        # Get request parameters
        data = request.get_json()
        if not data or 'backup_filename' not in data:
            raise BadRequest("backup_filename is required")
        
        backup_filename = data['backup_filename']
        
        # Validate backup
        validation_result = backup_service.validate_backup(backup_filename)
        return jsonify(validation_result)
        
    except BadRequest:
        raise
    except Exception as e:
        logger.error(f"Error validating backup: {str(e)}")
        raise InternalServerError(f"Failed to validate backup: {str(e)}")


@api_bp.route('/backup/delete', methods=['DELETE'])
def delete_backup():
    """Delete a backup file."""
    try:
        from src.services.backup_service import BackupService
        from src.models.database import DatabaseManager
        
        db_manager = DatabaseManager()
        backup_service = BackupService(db_manager)
        
        # Get request parameters
        data = request.get_json()
        if not data or 'backup_filename' not in data:
            raise BadRequest("backup_filename is required")
        
        backup_filename = data['backup_filename']
        
        # Delete backup
        delete_result = backup_service.delete_backup(backup_filename)
        
        if delete_result['success']:
            return jsonify(delete_result)
        else:
            return jsonify(delete_result), 400
            
    except BadRequest:
        raise
    except Exception as e:
        logger.error(f"Error deleting backup: {str(e)}")
        raise InternalServerError(f"Failed to delete backup: {str(e)}")


@api_bp.route('/backup/auto-create', methods=['POST'])
def create_automatic_backup():
    """Create an automatic backup."""
    try:
        from src.services.backup_service import BackupService
        from src.models.database import DatabaseManager
        
        db_manager = DatabaseManager()
        backup_service = BackupService(db_manager)
        
        # Create automatic backup
        backup_info = backup_service.create_automatic_backup()
        
        if backup_info and backup_info['success']:
            return jsonify(backup_info), 201
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to create automatic backup'
            }), 500
            
    except Exception as e:
        logger.error(f"Error creating automatic backup: {str(e)}")
        raise InternalServerError(f"Failed to create automatic backup: {str(e)}")