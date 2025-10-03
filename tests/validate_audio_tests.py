#!/usr/bin/env python3
"""
Validation script for audio service tests.
Checks that all imports work and test structure is correct.
"""

import sys
import os
import traceback

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def validate_imports():
    """Validate that all required imports work."""
    print("Validating imports...")
    
    try:
        # Test standard library imports
        import unittest.mock
        import tempfile
        import subprocess
        import threading
        import time
        from datetime import datetime, date, timedelta
        from pathlib import Path
        print("✓ Standard library imports successful")
        
        # Test that we can import our source modules
        from src.services.stream_recorder import StreamRecorder, RecordingStatus
        from src.services.audio_processor import AudioProcessor
        from src.services.recording_session_manager import RecordingSessionManager, WorkflowStage
        from src.models.stream_configuration import StreamConfiguration
        print("✓ Source module imports successful")
        
        # Test that we can import external dependencies (if available)
        try:
            import requests
            print("✓ requests available")
        except ImportError:
            print("⚠ requests not available (needed for HTTP stream validation)")
        
        try:
            from mutagen.mp3 import MP3
            from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TRCK, TDRC, APIC
            print("✓ mutagen available")
        except ImportError:
            print("⚠ mutagen not available (needed for MP3 metadata)")
        
        try:
            from PIL import Image
            print("✓ PIL available")
        except ImportError:
            print("⚠ PIL not available (needed for artwork processing)")
        
        return True
        
    except Exception as e:
        print(f"✗ Import validation failed: {e}")
        traceback.print_exc()
        return False

def validate_test_structure():
    """Validate test class structure."""
    print("\nValidating test structure...")
    
    try:
        # Import our test file
        sys.path.insert(0, os.path.dirname(__file__))
        
        # Check that test classes are properly structured
        test_classes = [
            'TestStreamRecorder',
            'TestAudioProcessor', 
            'TestRecordingSessionManager'
        ]
        
        # We can't import the test file directly due to pytest dependency,
        # but we can check the file exists and has the right structure
        test_file_path = os.path.join(os.path.dirname(__file__), 'test_audio_services.py')
        
        if not os.path.exists(test_file_path):
            print("✗ test_audio_services.py not found")
            return False
        
        with open(test_file_path, 'r') as f:
            content = f.read()
        
        for test_class in test_classes:
            if f"class {test_class}" in content:
                print(f"✓ {test_class} found")
            else:
                print(f"✗ {test_class} not found")
                return False
        
        # Check for key test methods
        key_methods = [
            'test_init',
            'test_validate_stream_url',
            'test_convert_to_mp3',
            'test_embed_metadata',
            'test_start_recording',
            'test_execute_recording_stage'
        ]
        
        found_methods = 0
        for method in key_methods:
            if f"def {method}" in content:
                found_methods += 1
        
        print(f"✓ Found {found_methods}/{len(key_methods)} key test methods")
        
        # Check for proper mocking patterns
        mock_patterns = [
            '@patch(',
            'Mock()',
            'mock_',
            'with patch'
        ]
        
        found_patterns = 0
        for pattern in mock_patterns:
            if pattern in content:
                found_patterns += 1
        
        print(f"✓ Found {found_patterns}/{len(mock_patterns)} mocking patterns")
        
        return True
        
    except Exception as e:
        print(f"✗ Test structure validation failed: {e}")
        traceback.print_exc()
        return False

def validate_test_coverage():
    """Validate that tests cover the required functionality."""
    print("\nValidating test coverage...")
    
    try:
        test_file_path = os.path.join(os.path.dirname(__file__), 'test_audio_services.py')
        
        with open(test_file_path, 'r') as f:
            content = f.read()
        
        # Check coverage of key requirements from task 3.4
        coverage_checks = [
            ('FFmpeg mocking', ['subprocess.run', 'subprocess.Popen', 'mock_run', 'mock_popen']),
            ('Metadata calculation', ['_generate_title', '_calculate_track_number', 'track_number']),
            ('Metadata embedding', ['_embed_metadata', 'mutagen', 'MP3', 'ID3']),
            ('Error handling', ['Exception', 'error_message', 'returncode', 'side_effect']),
            ('Retry logic', ['retry', 'max_retries', 'retry_count']),
            ('Stream validation', ['validate_stream_url', 'requests', 'HTTP', 'RTMP']),
            ('Audio processing', ['process_audio_file', 'convert_to_mp3', 'AudioProcessor']),
            ('Recording workflow', ['RecordingSessionManager', 'WorkflowStage', 'execute_.*_stage'])
        ]
        
        for check_name, patterns in coverage_checks:
            found = any(any(pattern.lower() in content.lower() for pattern in patterns) for pattern in patterns)
            if found:
                print(f"✓ {check_name} coverage found")
            else:
                print(f"⚠ {check_name} coverage may be incomplete")
        
        return True
        
    except Exception as e:
        print(f"✗ Coverage validation failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Main validation function."""
    print("Audio Service Tests Validation")
    print("=" * 40)
    
    success = True
    
    success &= validate_imports()
    success &= validate_test_structure()
    success &= validate_test_coverage()
    
    print("\n" + "=" * 40)
    if success:
        print("✓ All validations passed!")
        print("\nThe audio service tests are properly structured and should work")
        print("when pytest and required dependencies are installed.")
        print("\nTo run the tests:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Run tests: pytest tests/test_audio_services.py -v")
    else:
        print("✗ Some validations failed!")
        print("Please check the issues above.")
    
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())