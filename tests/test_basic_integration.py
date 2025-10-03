#!/usr/bin/env python3
"""
Basic integration test for Audio Stream Recorder.
Tests core functionality without external dependencies.
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path

# Add src to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    
    try:
        # Test core imports
        from src.config import config
        print("  ✓ Config imported")
        
        from src.main import ServiceContainer, initialize_database
        print("  ✓ Main module imported")
        
        from src.services.workflow_coordinator import WorkflowCoordinator
        print("  ✓ Workflow coordinator imported")
        
        from src.services.scheduler_service import SchedulerService
        print("  ✓ Scheduler service imported")
        
        from src.services.transfer_queue import TransferQueue
        print("  ✓ Transfer queue imported")
        
        from src.models.stream_configuration import StreamConfiguration
        from src.models.recording_schedule import RecordingSchedule
        from src.models.repositories import ConfigurationRepository, ScheduleRepository
        print("  ✓ Models and repositories imported")
        
        from src.web.app import create_app
        print("  ✓ Web app imported")
        
        return True
        
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        return False


def test_config_validation():
    """Test configuration validation."""
    print("Testing configuration validation...")
    
    try:
        from src.config import config
        
        # Test valid configuration
        config.validate_config()
        print("  ✓ Configuration validation passed")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Configuration validation failed: {e}")
        return False


def test_database_initialization():
    """Test database initialization."""
    print("Testing database initialization...")
    
    try:
        from src.main import initialize_database
        from src.config import config
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        
        # Override database URL
        original_db_url = config.DATABASE_URL
        config.DATABASE_URL = f"sqlite:///{temp_dir}/test.db"
        
        try:
            # Test database initialization
            result = initialize_database()
            
            if result:
                print("  ✓ Database initialization successful")
                return True
            else:
                print("  ✗ Database initialization failed")
                return False
                
        finally:
            # Restore original config
            config.DATABASE_URL = original_db_url
            # Cleanup
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    except Exception as e:
        print(f"  ✗ Database initialization error: {e}")
        return False


def test_service_container():
    """Test service container functionality."""
    print("Testing service container...")
    
    try:
        from src.main import ServiceContainer
        
        # Create service container
        container = ServiceContainer()
        
        # Test service registration
        test_service = {"name": "test"}
        container.register_service("test", test_service)
        
        # Test service retrieval
        retrieved = container.get_service("test")
        assert retrieved == test_service
        
        print("  ✓ Service container working")
        return True
        
    except Exception as e:
        print(f"  ✗ Service container error: {e}")
        return False


def test_workflow_coordinator_creation():
    """Test workflow coordinator creation."""
    print("Testing workflow coordinator creation...")
    
    try:
        from src.services.workflow_coordinator import WorkflowCoordinator
        from src.services.scheduler_service import SchedulerService
        from src.services.transfer_queue import TransferQueue
        from unittest.mock import Mock
        
        # Create mock services
        mock_scheduler = Mock(spec=SchedulerService)
        mock_transfer_queue = Mock(spec=TransferQueue)
        mock_logging = Mock()
        
        # Create workflow coordinator
        coordinator = WorkflowCoordinator(
            scheduler_service=mock_scheduler,
            transfer_queue=mock_transfer_queue,
            logging_service=mock_logging
        )
        
        # Test basic functionality
        active_sessions = coordinator.get_active_sessions()
        assert isinstance(active_sessions, dict)
        
        print("  ✓ Workflow coordinator created successfully")
        return True
        
    except Exception as e:
        print(f"  ✗ Workflow coordinator creation error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_web_app_creation():
    """Test web application creation."""
    print("Testing web application creation...")
    
    try:
        from src.web.app import create_app
        from src.main import ServiceContainer
        from unittest.mock import Mock
        
        # Create service container with mock services
        container = ServiceContainer()
        mock_logging = Mock()
        container.register_service('logging', mock_logging)
        
        # Create Flask app
        app = create_app(service_container=container)
        
        # Test that app was created
        assert app is not None
        assert hasattr(app, 'service_container')
        
        print("  ✓ Web application created successfully")
        return True
        
    except Exception as e:
        print(f"  ✗ Web application creation error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_model_creation():
    """Test model creation and basic operations."""
    print("Testing model creation...")
    
    try:
        from src.models.stream_configuration import StreamConfiguration
        from src.models.recording_schedule import RecordingSchedule
        
        # Create stream configuration
        stream_config = StreamConfiguration(
            name="Test Stream",
            stream_url="http://example.com/test.mp3",
            artist="Test Artist",
            album="Test Album",
            album_artist="Test Album Artist",
            output_filename_pattern="{date}_{title}.mp3",
            scp_destination="/test/"
        )
        
        assert stream_config.name == "Test Stream"
        assert stream_config.stream_url == "http://example.com/test.mp3"
        
        # Create recording schedule
        schedule = RecordingSchedule(
            stream_config_id=1,
            cron_expression="0 * * * *",
            duration_minutes=30,
            is_active=True
        )
        
        assert schedule.cron_expression == "0 * * * *"
        assert schedule.duration_minutes == 30
        assert schedule.is_active is True
        
        print("  ✓ Models created successfully")
        return True
        
    except Exception as e:
        print(f"  ✗ Model creation error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run basic integration tests."""
    print("=== Audio Stream Recorder Basic Integration Tests ===\n")
    
    tests = [
        ("Import Test", test_imports),
        ("Config Validation", test_config_validation),
        ("Database Initialization", test_database_initialization),
        ("Service Container", test_service_container),
        ("Model Creation", test_model_creation),
        ("Workflow Coordinator Creation", test_workflow_coordinator_creation),
        ("Web App Creation", test_web_app_creation),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"  ✗ Unexpected error: {e}")
            results.append((test_name, False))
    
    # Print summary
    print("\n" + "="*50)
    print("TEST SUMMARY")
    print("="*50)
    
    passed = 0
    total = len(results)
    
    for test_name, success in results:
        status = "PASSED" if success else "FAILED"
        symbol = "✓" if success else "✗"
        print(f"{symbol} {test_name}: {status}")
        if success:
            passed += 1
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All basic integration tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1


if __name__ == '__main__':
    sys.exit(main())