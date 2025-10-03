#!/usr/bin/env python3
"""
Integration test runner for Audio Stream Recorder.
Runs comprehensive end-to-end tests to validate complete system integration.
"""

import sys
import os
import subprocess
import tempfile
import shutil
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def setup_test_environment():
    """Set up test environment with temporary directories."""
    temp_dir = tempfile.mkdtemp(prefix='audio_recorder_test_')
    
    # Set environment variables for testing
    test_env = os.environ.copy()
    test_env.update({
        'DATA_DIR': os.path.join(temp_dir, 'data'),
        'RECORDINGS_DIR': os.path.join(temp_dir, 'recordings'),
        'LOG_DIR': os.path.join(temp_dir, 'logs'),
        'ARTWORK_DIR': os.path.join(temp_dir, 'artwork'),
        'SSH_CONFIG_DIR': os.path.join(temp_dir, 'ssh'),
        'DATABASE_URL': f"sqlite:///{temp_dir}/data/test_audio_recorder.db",
        'LOG_LEVEL': 'DEBUG',
        'MAX_CONCURRENT_RECORDINGS': '2',
        'WEB_PORT': '8667'  # Different port for testing
    })
    
    return temp_dir, test_env


def run_pytest_tests(test_env):
    """Run pytest integration tests."""
    print("Running pytest integration tests...")
    
    # Run integration tests
    cmd = [
        sys.executable, '-m', 'pytest',
        'tests/test_integration_workflow.py',
        '-v',
        '--tb=short',
        '--disable-warnings'
    ]
    
    result = subprocess.run(cmd, env=test_env, capture_output=True, text=True)
    
    print("STDOUT:")
    print(result.stdout)
    
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    return result.returncode == 0


def run_manual_integration_test(test_env):
    """Run manual integration test to verify basic functionality."""
    print("Running manual integration test...")
    
    try:
        # Import after setting up environment
        from src.main import ServiceContainer, initialize_database
        from src.config import config
        from src.services.scheduler_service import SchedulerService
        from src.services.transfer_queue import TransferQueue
        from src.services.workflow_coordinator import WorkflowCoordinator
        from src.models.stream_configuration import StreamConfiguration
        from src.models.recording_schedule import RecordingSchedule
        from src.models.repositories import ConfigurationRepository, ScheduleRepository
        
        # Override config with test values
        for key, value in test_env.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        # Ensure directories exist
        config.ensure_directories()
        
        # Initialize database
        print("  - Initializing database...")
        if not initialize_database():
            print("  ✗ Database initialization failed")
            return False
        print("  ✓ Database initialized")
        
        # Create service container
        print("  - Creating service container...")
        container = ServiceContainer()
        
        # Initialize services
        print("  - Initializing services...")
        
        # Mock logging service
        from unittest.mock import Mock
        mock_logging = Mock()
        container.register_service('logging', mock_logging)
        
        # Transfer queue
        transfer_queue = TransferQueue()
        container.register_service('transfer_queue', transfer_queue)
        
        # Scheduler service
        scheduler_service = SchedulerService()
        container.register_service('scheduler', scheduler_service)
        
        # Workflow coordinator
        workflow_coordinator = WorkflowCoordinator(
            scheduler_service=scheduler_service,
            transfer_queue=transfer_queue,
            logging_service=mock_logging
        )
        container.register_service('workflow_coordinator', workflow_coordinator)
        
        print("  ✓ Services initialized")
        
        # Test basic functionality
        print("  - Testing basic functionality...")
        
        # Create test stream configuration
        config_repo = ConfigurationRepository()
        test_config = StreamConfiguration(
            name="Integration Test Stream",
            stream_url="http://example.com/test-stream.mp3",
            artist="Test Artist",
            album="Test Album",
            album_artist="Test Album Artist",
            output_filename_pattern="{date}_{title}.mp3",
            scp_destination="/test/destination/"
        )
        
        saved_config = config_repo.create(test_config)
        print(f"  ✓ Created stream configuration (ID: {saved_config.id})")
        
        # Create test schedule
        schedule_repo = ScheduleRepository()
        test_schedule = RecordingSchedule(
            stream_config_id=saved_config.id,
            cron_expression="0 * * * *",  # Every hour
            duration_minutes=30,
            is_active=True
        )
        
        saved_schedule = schedule_repo.create(test_schedule)
        print(f"  ✓ Created recording schedule (ID: {saved_schedule.id})")
        
        # Test scheduler
        print("  - Testing scheduler service...")
        assert scheduler_service.start()
        print("  ✓ Scheduler started")
        
        # Test workflow coordinator
        print("  - Testing workflow coordinator...")
        active_sessions = workflow_coordinator.get_active_sessions()
        assert isinstance(active_sessions, dict)
        print(f"  ✓ Workflow coordinator active (sessions: {len(active_sessions)})")
        
        # Cleanup
        print("  - Cleaning up...")
        container.shutdown_all()
        print("  ✓ Services shut down")
        
        print("✓ Manual integration test passed")
        return True
        
    except Exception as e:
        print(f"✗ Manual integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_web_interface_integration(test_env):
    """Test web interface integration."""
    print("Testing web interface integration...")
    
    try:
        # Import Flask app
        from src.web.app import create_app
        from src.main import ServiceContainer
        from unittest.mock import Mock
        
        # Create service container with mocks
        container = ServiceContainer()
        
        # Mock services
        mock_logging = Mock()
        mock_monitoring = Mock()
        mock_workflow = Mock()
        
        mock_monitoring.get_current_metrics = Mock(return_value=Mock(
            uptime_seconds=3600,
            cpu_percent=25.0,
            memory_percent=50.0,
            memory_used_mb=512,
            memory_total_mb=1024,
            disk_percent=60.0,
            disk_used_gb=30,
            disk_total_gb=50,
            disk_free_gb=20
        ))
        
        mock_monitoring.get_health_status = Mock(return_value={
            'status': 'healthy',
            'message': 'All systems operational',
            'timestamp': '2024-01-01T00:00:00Z',
            'components': {}
        })
        
        mock_workflow.get_active_sessions = Mock(return_value={})
        
        container.register_service('logging', mock_logging)
        container.register_service('monitoring', mock_monitoring)
        container.register_service('workflow_coordinator', mock_workflow)
        
        # Create Flask app
        app = create_app(service_container=container)
        app.config['TESTING'] = True
        
        with app.test_client() as client:
            # Test health endpoint
            response = client.get('/health')
            assert response.status_code == 200
            print("  ✓ Health endpoint working")
            
            # Test system status API
            response = client.get('/api/system/status')
            assert response.status_code == 200
            data = response.get_json()
            assert 'status' in data
            print("  ✓ System status API working")
            
            # Test active sessions API
            response = client.get('/api/sessions/active')
            assert response.status_code == 200
            data = response.get_json()
            assert 'active_sessions' in data
            print("  ✓ Active sessions API working")
        
        print("✓ Web interface integration test passed")
        return True
        
    except Exception as e:
        print(f"✗ Web interface integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all integration tests."""
    print("=== Audio Stream Recorder Integration Tests ===")
    
    # Setup test environment
    temp_dir, test_env = setup_test_environment()
    
    try:
        # Create required directories
        for dir_key in ['DATA_DIR', 'RECORDINGS_DIR', 'LOG_DIR', 'ARTWORK_DIR', 'SSH_CONFIG_DIR']:
            os.makedirs(test_env[dir_key], exist_ok=True)
        
        results = []
        
        # Run pytest tests
        print("\n1. Running pytest integration tests...")
        pytest_success = run_pytest_tests(test_env)
        results.append(("Pytest Integration Tests", pytest_success))
        
        # Run manual integration test
        print("\n2. Running manual integration test...")
        manual_success = run_manual_integration_test(test_env)
        results.append(("Manual Integration Test", manual_success))
        
        # Run web interface test
        print("\n3. Running web interface integration test...")
        web_success = test_web_interface_integration(test_env)
        results.append(("Web Interface Integration Test", web_success))
        
        # Print results
        print("\n=== Test Results ===")
        all_passed = True
        for test_name, success in results:
            status = "✓ PASSED" if success else "✗ FAILED"
            print(f"{test_name}: {status}")
            if not success:
                all_passed = False
        
        if all_passed:
            print("\n🎉 All integration tests passed!")
            return 0
        else:
            print("\n❌ Some integration tests failed!")
            return 1
            
    finally:
        # Cleanup temporary directory
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"\nCleaned up temporary directory: {temp_dir}")
        except Exception as e:
            print(f"Warning: Could not clean up temporary directory: {e}")


if __name__ == '__main__':
    sys.exit(main())