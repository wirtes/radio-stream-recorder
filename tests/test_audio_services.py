"""
Unit tests for audio service components.
Tests StreamRecorder, AudioProcessor, and RecordingSessionManager with mocked dependencies.
"""

import pytest
import os
import tempfile
import subprocess
import threading
import time
from unittest.mock import Mock, patch, MagicMock, call, mock_open
from datetime import datetime, date, timedelta
from pathlib import Path

import requests
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TRCK, TDRC, APIC
from PIL import Image

from src.services.stream_recorder import StreamRecorder, RecordingStatus
from src.services.audio_processor import AudioProcessor
from src.services.recording_session_manager import RecordingSessionManager, WorkflowStage
from src.models.stream_configuration import StreamConfiguration


class TestStreamRecorder:
    """Test StreamRecorder class with mocked FFmpeg operations."""
    
    @pytest.fixture
    def temp_output_path(self):
        """Create temporary output path for testing."""
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
            temp_path = f.name
        yield temp_path
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    
    @pytest.fixture
    def recorder(self, temp_output_path):
        """Create StreamRecorder instance for testing."""
        return StreamRecorder(
            stream_url="https://example.com/stream.mp3",
            output_path=temp_output_path,
            duration_minutes=5
        )
    
    def test_init(self, recorder, temp_output_path):
        """Test StreamRecorder initialization."""
        assert recorder.stream_url == "https://example.com/stream.mp3"
        assert recorder.output_path == temp_output_path
        assert recorder.duration_minutes == 5
        assert recorder.status == RecordingStatus.IDLE
        assert recorder.start_time is None
        assert recorder.end_time is None
        assert recorder.error_message is None
        assert recorder.bytes_recorded == 0
    
    def test_validate_stream_url_http_success(self, recorder):
        """Test successful HTTP stream URL validation."""
        with patch('requests.head') as mock_head:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {'content-type': 'audio/mpeg'}
            mock_head.return_value = mock_response
            
            result = recorder.validate_stream_url()
            
            assert result is True
            mock_head.assert_called_once_with(
                recorder.stream_url,
                timeout=10,
                allow_redirects=True,
                headers={'User-Agent': 'AudioStreamRecorder/1.0'}
            )
    
    def test_validate_stream_url_http_failure(self, recorder):
        """Test HTTP stream URL validation failure."""
        with patch('requests.head') as mock_head:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_head.return_value = mock_response
            
            result = recorder.validate_stream_url()
            
            assert result is False
            assert "HTTP error: 404" in recorder.error_message
    
    def test_validate_stream_url_connection_error(self, recorder):
        """Test HTTP stream URL validation with connection error."""
        with patch('requests.head') as mock_head:
            mock_head.side_effect = requests.exceptions.ConnectionError("Connection failed")
            
            result = recorder.validate_stream_url()
            
            assert result is False
            assert "Connection test failed" in recorder.error_message
    
    def test_validate_stream_url_invalid_protocol(self, temp_output_path):
        """Test stream URL validation with invalid protocol."""
        recorder = StreamRecorder(
            stream_url="ftp://example.com/stream.mp3",
            output_path=temp_output_path
        )
        
        result = recorder.validate_stream_url()
        
        assert result is False
        assert "Unsupported protocol: ftp" in recorder.error_message
    
    def test_validate_stream_url_rtmp_success(self, temp_output_path):
        """Test successful RTMP stream URL validation."""
        recorder = StreamRecorder(
            stream_url="rtmp://example.com/live/stream",
            output_path=temp_output_path
        )
        
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            result = recorder.validate_stream_url()
            
            assert result is True
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert 'ffprobe' in args
            assert recorder.stream_url in args
    
    def test_validate_stream_url_rtmp_failure(self, temp_output_path):
        """Test RTMP stream URL validation failure."""
        recorder = StreamRecorder(
            stream_url="rtmp://example.com/live/stream",
            output_path=temp_output_path
        )
        
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 1
            mock_result.stderr = "Connection failed"
            mock_run.return_value = mock_result
            
            result = recorder.validate_stream_url()
            
            assert result is False
            assert "RTMP stream test failed" in recorder.error_message
    
    @patch('src.services.stream_recorder.subprocess.Popen')
    @patch('src.services.stream_recorder.os.makedirs')
    def test_start_recording_success(self, mock_makedirs, mock_popen, recorder):
        """Test successful recording start."""
        # Mock validation
        with patch.object(recorder, 'validate_stream_url', return_value=True):
            # Mock FFmpeg process
            mock_process = Mock()
            mock_process.poll.return_value = None  # Process running
            mock_popen.return_value = mock_process
            
            result = recorder.start_recording()
            
            assert result is True
            assert recorder.status == RecordingStatus.CONNECTING
            # Wait a bit for thread to start
            time.sleep(0.1)
            mock_makedirs.assert_called_once()
    
    def test_start_recording_validation_failure(self, recorder):
        """Test recording start with validation failure."""
        with patch.object(recorder, 'validate_stream_url', return_value=False):
            recorder.error_message = "Stream validation failed"
            
            result = recorder.start_recording()
            
            assert result is False
            assert recorder.status == RecordingStatus.FAILED
    
    def test_start_recording_already_active(self, recorder):
        """Test starting recording when already active."""
        recorder.status = RecordingStatus.RECORDING
        
        result = recorder.start_recording()
        
        assert result is False
        assert "Cannot start recording" in recorder.error_message
    
    def test_build_ffmpeg_command(self, recorder):
        """Test FFmpeg command building."""
        with patch('src.config.config.FFMPEG_PATH', 'ffmpeg'):
            cmd = recorder._build_ffmpeg_command()
            
            expected_cmd = [
                'ffmpeg',
                '-y',
                '-i', recorder.stream_url,
                '-c', 'copy',
                '-f', 'mp3',
                '-t', '300',  # 5 minutes * 60 seconds
                recorder.output_path
            ]
            
            assert cmd == expected_cmd
    
    def test_build_ffmpeg_command_no_duration(self, temp_output_path):
        """Test FFmpeg command building without duration limit."""
        recorder = StreamRecorder(
            stream_url="https://example.com/stream.mp3",
            output_path=temp_output_path
        )
        
        with patch('src.config.config.FFMPEG_PATH', 'ffmpeg'):
            cmd = recorder._build_ffmpeg_command()
            
            expected_cmd = [
                'ffmpeg',
                '-y',
                '-i', recorder.stream_url,
                '-c', 'copy',
                '-f', 'mp3',
                recorder.output_path
            ]
            
            assert cmd == expected_cmd
    
    @patch('src.services.stream_recorder.os.killpg')
    @patch('src.services.stream_recorder.os.getpgid')
    def test_terminate_process(self, mock_getpgid, mock_killpg, recorder):
        """Test process termination."""
        mock_process = Mock()
        mock_process.poll.return_value = None  # Process running
        mock_process.pid = 12345
        mock_process.wait.return_value = None
        mock_getpgid.return_value = 12345
        
        recorder.process = mock_process
        
        recorder._terminate_process()
        
        mock_killpg.assert_called()
        mock_process.wait.assert_called_with(timeout=5)
    
    def test_stop_recording_success(self, recorder):
        """Test successful recording stop."""
        recorder.status = RecordingStatus.RECORDING
        recorder.recording_thread = Mock()
        recorder.recording_thread.is_alive.return_value = False
        
        result = recorder.stop_recording()
        
        assert result is True
        assert recorder.status == RecordingStatus.STOPPING
        assert recorder.stop_event.is_set()
    
    def test_stop_recording_invalid_status(self, recorder):
        """Test stopping recording with invalid status."""
        recorder.status = RecordingStatus.COMPLETED
        
        result = recorder.stop_recording()
        
        assert result is False
        assert "Cannot stop recording" in recorder.error_message
    
    def test_get_recording_info(self, recorder):
        """Test getting recording information."""
        recorder.start_time = datetime(2023, 1, 1, 12, 0, 0)
        recorder.end_time = datetime(2023, 1, 1, 12, 30, 0)
        recorder.bytes_recorded = 1024000
        
        info = recorder.get_recording_info()
        
        assert info['status'] == RecordingStatus.IDLE.value
        assert info['stream_url'] == recorder.stream_url
        assert info['output_path'] == recorder.output_path
        assert info['duration_seconds'] == 1800  # 30 minutes
        assert info['bytes_recorded'] == 1024000
    
    def test_status_callback(self, recorder):
        """Test status callback functionality."""
        callback_mock = Mock()
        recorder.set_status_callback(callback_mock)
        
        recorder._update_status(RecordingStatus.RECORDING, {'test': 'data'})
        
        callback_mock.assert_called_once()
        args = callback_mock.call_args
        assert args[0][0] == RecordingStatus.RECORDING
        assert 'test' in args[0][1]
        assert args[0][1]['test'] == 'data'
    
    def test_context_manager(self, temp_output_path):
        """Test context manager functionality."""
        with StreamRecorder("https://example.com/stream.mp3", temp_output_path) as recorder:
            assert isinstance(recorder, StreamRecorder)
        # Cleanup should be called automatically


class TestAudioProcessor:
    """Test AudioProcessor class with mocked FFmpeg and Mutagen operations."""
    
    @pytest.fixture
    def processor(self):
        """Create AudioProcessor instance for testing."""
        return AudioProcessor()
    
    @pytest.fixture
    def temp_files(self):
        """Create temporary input and output files for testing."""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as input_file:
            input_path = input_file.name
        
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as output_file:
            output_path = output_file.name
        
        yield input_path, output_path
        
        # Cleanup
        for path in [input_path, output_path]:
            if os.path.exists(path):
                os.unlink(path)
    
    @pytest.fixture
    def sample_metadata(self):
        """Sample metadata for testing."""
        return {
            'name': 'Test Show',
            'artist': 'Test Artist',
            'album': 'Test Album',
            'album_artist': 'Test Album Artist'
        }
    
    def test_init(self, processor):
        """Test AudioProcessor initialization."""
        assert processor.logger is not None
    
    @patch('src.services.audio_processor.subprocess.run')
    @patch('src.services.audio_processor.os.path.exists')
    def test_convert_to_mp3_success(self, mock_exists, mock_run, processor, temp_files):
        """Test successful MP3 conversion."""
        input_path, output_path = temp_files
        mock_exists.return_value = True
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        result = processor._convert_to_mp3(input_path, output_path)
        
        assert result is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert 'ffmpeg' in args[0]
        assert input_path in args
        assert output_path in args
    
    @patch('src.services.audio_processor.os.path.exists')
    def test_convert_to_mp3_input_not_exists(self, mock_exists, processor, temp_files):
        """Test MP3 conversion with non-existent input file."""
        input_path, output_path = temp_files
        mock_exists.return_value = False
        
        result = processor._convert_to_mp3(input_path, output_path)
        
        assert result is False
    
    @patch('src.services.audio_processor.shutil.copy2')
    @patch('src.services.audio_processor.os.path.exists')
    def test_convert_to_mp3_already_mp3(self, mock_exists, mock_copy, processor):
        """Test MP3 conversion when input is already MP3."""
        input_path = "/path/to/input.mp3"
        output_path = "/path/to/output.mp3"
        mock_exists.return_value = True
        
        result = processor._convert_to_mp3(input_path, output_path)
        
        assert result is True
        mock_copy.assert_called_once_with(input_path, output_path)
    
    @patch('src.services.audio_processor.subprocess.run')
    @patch('src.services.audio_processor.os.path.exists')
    def test_convert_to_mp3_ffmpeg_failure(self, mock_exists, mock_run, processor, temp_files):
        """Test MP3 conversion with FFmpeg failure."""
        input_path, output_path = temp_files
        mock_exists.return_value = True
        
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "FFmpeg error"
        mock_run.return_value = mock_result
        
        result = processor._convert_to_mp3(input_path, output_path)
        
        assert result is False
    
    @patch('src.services.audio_processor.subprocess.run')
    @patch('src.services.audio_processor.os.path.exists')
    def test_convert_to_mp3_timeout(self, mock_exists, mock_run, processor, temp_files):
        """Test MP3 conversion with timeout."""
        input_path, output_path = temp_files
        mock_exists.return_value = True
        
        mock_run.side_effect = subprocess.TimeoutExpired('ffmpeg', 300)
        
        result = processor._convert_to_mp3(input_path, output_path)
        
        assert result is False
    
    def test_generate_title(self, processor):
        """Test title generation."""
        recording_date = datetime(2023, 5, 15, 14, 30, 0)
        
        title = processor._generate_title(recording_date, "Morning Show")
        
        assert title == "2023-05-15 Morning Show"
    
    def test_generate_title_default_name(self, processor):
        """Test title generation with default show name."""
        recording_date = datetime(2023, 5, 15, 14, 30, 0)
        
        title = processor._generate_title(recording_date)
        
        assert title == "2023-05-15 Show"
    
    def test_calculate_track_number(self, processor):
        """Test track number calculation."""
        # Test date after base date (Jan 1, 2020)
        recording_date = datetime(2020, 1, 5, 12, 0, 0)  # 5 days after base
        
        track_number = processor._calculate_track_number(recording_date)
        
        assert track_number == 5  # 4 days difference + 1
    
    def test_calculate_track_number_base_date(self, processor):
        """Test track number calculation for base date."""
        recording_date = datetime(2020, 1, 1, 12, 0, 0)  # Base date
        
        track_number = processor._calculate_track_number(recording_date)
        
        assert track_number == 1  # Minimum track number
    
    def test_calculate_track_number_before_base(self, processor):
        """Test track number calculation for date before base."""
        recording_date = datetime(2019, 12, 30, 12, 0, 0)  # Before base date
        
        track_number = processor._calculate_track_number(recording_date)
        
        assert track_number == 1  # Minimum track number
    
    @patch('src.services.audio_processor.MP3')
    def test_embed_metadata_success(self, mock_mp3, processor, sample_metadata):
        """Test successful metadata embedding."""
        mp3_path = "/path/to/test.mp3"
        
        # Mock MP3 file
        mock_audio_file = Mock()
        mock_audio_file.tags = Mock()
        mock_mp3.return_value = mock_audio_file
        
        recording_date = datetime(2023, 5, 15, 14, 30, 0)
        
        result = processor._embed_metadata(mp3_path, sample_metadata, None, recording_date)
        
        assert result is True
        mock_audio_file.tags.add.assert_called()
        mock_audio_file.save.assert_called_once()
        
        # Check that all required tags were added
        add_calls = mock_audio_file.tags.add.call_args_list
        tag_types = [call[0][0].__class__.__name__ for call in add_calls]
        
        expected_tags = ['TIT2', 'TPE1', 'TALB', 'TPE2', 'TRCK', 'TDRC']
        for expected_tag in expected_tags:
            assert expected_tag in tag_types
    
    @patch('src.services.audio_processor.MP3')
    def test_embed_metadata_no_existing_tags(self, mock_mp3, processor, sample_metadata):
        """Test metadata embedding when no existing tags."""
        mp3_path = "/path/to/test.mp3"
        
        # Mock MP3 file with no tags
        mock_audio_file = Mock()
        mock_audio_file.tags = None
        mock_mp3.return_value = mock_audio_file
        
        result = processor._embed_metadata(mp3_path, sample_metadata)
        
        assert result is True
        mock_audio_file.add_tags.assert_called_once()
    
    @patch('src.services.audio_processor.MP3')
    def test_embed_metadata_with_artwork(self, mock_mp3, processor, sample_metadata):
        """Test metadata embedding with artwork."""
        mp3_path = "/path/to/test.mp3"
        artwork_path = "/path/to/artwork.jpg"
        
        # Mock MP3 file
        mock_audio_file = Mock()
        mock_audio_file.tags = Mock()
        mock_mp3.return_value = mock_audio_file
        
        with patch.object(processor, '_embed_artwork', return_value=True) as mock_embed_artwork:
            with patch('src.services.audio_processor.os.path.exists', return_value=True):
                result = processor._embed_metadata(mp3_path, sample_metadata, artwork_path)
                
                assert result is True
                mock_embed_artwork.assert_called_once_with(mock_audio_file, artwork_path)
    
    @patch('src.services.audio_processor.MP3')
    def test_embed_metadata_exception(self, mock_mp3, processor, sample_metadata):
        """Test metadata embedding with exception."""
        mp3_path = "/path/to/test.mp3"
        
        mock_mp3.side_effect = Exception("Mutagen error")
        
        result = processor._embed_metadata(mp3_path, sample_metadata)
        
        assert result is False
    
    @patch('builtins.open', new_callable=mock_open, read_data=b'fake_image_data')
    @patch('src.services.audio_processor.Path')
    def test_embed_artwork_success(self, mock_path, mock_file, processor):
        """Test successful artwork embedding."""
        artwork_path = "/path/to/artwork.jpg"
        
        # Mock Path suffix
        mock_path_instance = Mock()
        mock_path_instance.suffix.lower.return_value = '.jpg'
        mock_path.return_value = mock_path_instance
        
        # Mock audio file
        mock_audio_file = Mock()
        mock_audio_file.tags = Mock()
        
        with patch.object(processor, '_process_artwork_image', return_value=artwork_path):
            result = processor._embed_artwork(mock_audio_file, artwork_path)
            
            assert result is True
            mock_audio_file.tags.add.assert_called_once()
            
            # Check APIC tag was added
            apic_call = mock_audio_file.tags.add.call_args[0][0]
            assert apic_call.mime == 'image/jpeg'
            assert apic_call.type == 3  # Cover (front)
            assert apic_call.data == b'fake_image_data'
    
    def test_embed_artwork_unsupported_format(self, processor):
        """Test artwork embedding with unsupported format."""
        artwork_path = "/path/to/artwork.gif"
        mock_audio_file = Mock()
        
        with patch.object(processor, '_process_artwork_image', return_value=artwork_path):
            with patch('src.services.audio_processor.Path') as mock_path:
                mock_path_instance = Mock()
                mock_path_instance.suffix.lower.return_value = '.gif'
                mock_path.return_value = mock_path_instance
                
                result = processor._embed_artwork(mock_audio_file, artwork_path)
                
                assert result is False
    
    @patch('src.services.audio_processor.Image.open')
    @patch('src.services.audio_processor.os.path.getsize')
    def test_process_artwork_image_no_resize_needed(self, mock_getsize, mock_image_open, processor):
        """Test artwork processing when no resize is needed."""
        artwork_path = "/path/to/artwork.jpg"
        
        # Mock small file size (under limit)
        mock_getsize.return_value = 1024 * 1024  # 1MB
        
        # Mock image
        mock_image = Mock()
        mock_image.mode = 'RGB'
        mock_image_open.return_value.__enter__.return_value = mock_image
        
        with patch('src.config.config.MAX_ARTWORK_SIZE_MB', 10):
            result = processor._process_artwork_image(artwork_path)
            
            assert result == artwork_path  # No processing needed
    
    @patch('src.services.audio_processor.Image.open')
    @patch('src.services.audio_processor.os.path.getsize')
    def test_process_artwork_image_resize_needed(self, mock_getsize, mock_image_open, processor):
        """Test artwork processing when resize is needed."""
        artwork_path = "/path/to/artwork.jpg"
        
        # Mock large file size (over limit)
        mock_getsize.return_value = 15 * 1024 * 1024  # 15MB
        
        # Mock large image
        mock_image = Mock()
        mock_image.mode = 'RGB'
        mock_image.width = 2000
        mock_image.height = 2000
        mock_image_open.return_value.__enter__.return_value = mock_image
        
        with patch('src.config.config.MAX_ARTWORK_SIZE_MB', 10):
            result = processor._process_artwork_image(artwork_path)
            
            assert result == artwork_path + '.processed.jpg'
            mock_image.thumbnail.assert_called_once_with((800, 800), Image.Resampling.LANCZOS)
            mock_image.save.assert_called_once()
    
    @patch('src.services.audio_processor.Image.open')
    def test_process_artwork_image_exception(self, mock_image_open, processor):
        """Test artwork processing with exception."""
        artwork_path = "/path/to/artwork.jpg"
        
        mock_image_open.side_effect = Exception("PIL error")
        
        result = processor._process_artwork_image(artwork_path)
        
        assert result is None
    
    @patch('src.services.audio_processor.subprocess.run')
    @patch('src.services.audio_processor.os.path.exists')
    def test_get_audio_info_success(self, mock_exists, mock_run, processor):
        """Test successful audio info retrieval."""
        file_path = "/path/to/audio.mp3"
        mock_exists.return_value = True
        
        # Mock FFprobe output
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '''
        {
            "format": {
                "size": "1024000",
                "duration": "180.5",
                "format_name": "mp3",
                "bit_rate": "128000"
            },
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "mp3",
                    "sample_rate": "44100",
                    "channels": 2,
                    "channel_layout": "stereo"
                }
            ]
        }
        '''
        mock_run.return_value = mock_result
        
        info = processor.get_audio_info(file_path)
        
        assert info is not None
        assert info['file_path'] == file_path
        assert info['file_size_bytes'] == 1024000
        assert info['duration_seconds'] == 180.5
        assert info['format_name'] == 'mp3'
        assert info['codec_name'] == 'mp3'
        assert info['sample_rate'] == 44100
        assert info['channels'] == 2
    
    @patch('src.services.audio_processor.os.path.exists')
    def test_get_audio_info_file_not_exists(self, mock_exists, processor):
        """Test audio info retrieval for non-existent file."""
        file_path = "/path/to/nonexistent.mp3"
        mock_exists.return_value = False
        
        info = processor.get_audio_info(file_path)
        
        assert info is None
    
    @patch('src.services.audio_processor.subprocess.run')
    @patch('src.services.audio_processor.os.path.exists')
    def test_get_audio_info_ffprobe_failure(self, mock_exists, mock_run, processor):
        """Test audio info retrieval with FFprobe failure."""
        file_path = "/path/to/audio.mp3"
        mock_exists.return_value = True
        
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "FFprobe error"
        mock_run.return_value = mock_result
        
        info = processor.get_audio_info(file_path)
        
        assert info is None
    
    @patch('src.services.audio_processor.MP3')
    @patch('src.services.audio_processor.os.path.exists')
    def test_validate_mp3_file_success(self, mock_exists, mock_mp3, processor):
        """Test successful MP3 file validation."""
        file_path = "/path/to/valid.mp3"
        mock_exists.return_value = True
        
        # Mock MP3 file with all required tags
        mock_audio_file = Mock()
        mock_tags = {
            'TIT2': Mock(),
            'TPE1': Mock(),
            'TALB': Mock(),
            'TPE2': Mock(),
            'TRCK': Mock()
        }
        mock_audio_file.tags = mock_tags
        mock_mp3.return_value = mock_audio_file
        
        result = processor.validate_mp3_file(file_path)
        
        assert result is True
    
    @patch('src.services.audio_processor.os.path.exists')
    def test_validate_mp3_file_not_exists(self, mock_exists, processor):
        """Test MP3 file validation for non-existent file."""
        file_path = "/path/to/nonexistent.mp3"
        mock_exists.return_value = False
        
        result = processor.validate_mp3_file(file_path)
        
        assert result is False
    
    @patch('src.services.audio_processor.MP3')
    @patch('src.services.audio_processor.os.path.exists')
    def test_validate_mp3_file_no_tags(self, mock_exists, mock_mp3, processor):
        """Test MP3 file validation with no tags."""
        file_path = "/path/to/notags.mp3"
        mock_exists.return_value = True
        
        # Mock MP3 file with no tags
        mock_audio_file = Mock()
        mock_audio_file.tags = None
        mock_mp3.return_value = mock_audio_file
        
        result = processor.validate_mp3_file(file_path)
        
        assert result is False
    
    @patch('src.services.audio_processor.MP3')
    @patch('src.services.audio_processor.os.path.exists')
    def test_validate_mp3_file_missing_tags(self, mock_exists, mock_mp3, processor):
        """Test MP3 file validation with missing required tags."""
        file_path = "/path/to/incomplete.mp3"
        mock_exists.return_value = True
        
        # Mock MP3 file with only some tags
        mock_audio_file = Mock()
        mock_tags = {
            'TIT2': Mock(),
            'TPE1': Mock()
            # Missing TALB, TPE2, TRCK
        }
        mock_audio_file.tags = mock_tags
        mock_mp3.return_value = mock_audio_file
        
        result = processor.validate_mp3_file(file_path)
        
        assert result is False
    
    @patch('src.services.audio_processor.os.makedirs')
    def test_process_audio_file_success(self, mock_makedirs, processor, sample_metadata):
        """Test successful complete audio file processing."""
        input_path = "/path/to/input.wav"
        output_path = "/path/to/output.mp3"
        
        with patch.object(processor, '_convert_to_mp3', return_value=True) as mock_convert:
            with patch.object(processor, '_embed_metadata', return_value=True) as mock_embed:
                result = processor.process_audio_file(
                    input_path, output_path, sample_metadata
                )
                
                assert result is True
                mock_makedirs.assert_called_once()
                mock_convert.assert_called_once_with(input_path, output_path)
                mock_embed.assert_called_once()
    
    def test_process_audio_file_conversion_failure(self, processor, sample_metadata):
        """Test audio file processing with conversion failure."""
        input_path = "/path/to/input.wav"
        output_path = "/path/to/output.mp3"
        
        with patch.object(processor, '_convert_to_mp3', return_value=False):
            result = processor.process_audio_file(
                input_path, output_path, sample_metadata
            )
            
            assert result is False
    
    def test_process_audio_file_metadata_failure(self, processor, sample_metadata):
        """Test audio file processing with metadata embedding failure."""
        input_path = "/path/to/input.wav"
        output_path = "/path/to/output.mp3"
        
        with patch.object(processor, '_convert_to_mp3', return_value=True):
            with patch.object(processor, '_embed_metadata', return_value=False):
                result = processor.process_audio_file(
                    input_path, output_path, sample_metadata
                )
                
                assert result is False


class TestRecordingSessionManager:
    """Test RecordingSessionManager class with mocked dependencies."""
    
    @pytest.fixture
    def stream_config(self):
        """Create mock stream configuration."""
        config = Mock(spec=StreamConfiguration)
        config.name = "Test Stream"
        config.stream_url = "https://example.com/stream.mp3"
        config.artist = "Test Artist"
        config.album = "Test Album"
        config.album_artist = "Test Album Artist"
        config.artwork_path = "/path/to/artwork.jpg"
        config.output_filename_pattern = "{date}_{name}.mp3"
        config.scp_destination = "user@host:/path"
        return config
    
    @pytest.fixture
    def session_manager(self, stream_config):
        """Create RecordingSessionManager instance for testing."""
        with patch('src.services.recording_session_manager.os.makedirs'):
            return RecordingSessionManager(
                session_id=1,
                stream_config=stream_config,
                duration_minutes=30
            )
    
    def test_init(self, session_manager, stream_config):
        """Test RecordingSessionManager initialization."""
        assert session_manager.session_id == 1
        assert session_manager.stream_config == stream_config
        assert session_manager.duration_minutes == 30
        assert session_manager.current_stage == WorkflowStage.INITIALIZING
        assert session_manager.start_time is None
        assert session_manager.end_time is None
        assert session_manager.error_message is None
        assert session_manager.retry_count == 0
    
    def test_generate_file_paths(self, session_manager):
        """Test file path generation."""
        with patch('src.services.recording_session_manager.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2023, 5, 15, 14, 30, 0)
            mock_datetime.strftime = datetime.strftime
            
            session_manager._generate_file_paths()
            
            assert session_manager.raw_recording_path is not None
            assert "Test Stream" in session_manager.raw_recording_path
            assert "_raw.mp3" in session_manager.raw_recording_path
            
            assert session_manager.processed_mp3_path is not None
            assert "2023-05-15_Test Stream.mp3" in session_manager.processed_mp3_path
    
    def test_start_recording_success(self, session_manager):
        """Test successful recording workflow start."""
        result = session_manager.start_recording()
        
        assert result is True
        assert session_manager.workflow_thread is not None
        assert session_manager.workflow_thread.daemon is True
        
        # Wait briefly for thread to start
        time.sleep(0.1)
    
    def test_start_recording_invalid_stage(self, session_manager):
        """Test starting recording with invalid stage."""
        session_manager.current_stage = WorkflowStage.RECORDING
        
        result = session_manager.start_recording()
        
        assert result is False
        assert "Cannot start recording" in session_manager.error_message
    
    @patch('src.services.recording_session_manager.StreamRecorder')
    def test_execute_recording_stage_success(self, mock_stream_recorder_class, session_manager):
        """Test successful recording stage execution."""
        # Mock StreamRecorder
        mock_recorder = Mock()
        mock_recorder.start_recording.return_value = True
        mock_recorder.status = RecordingStatus.COMPLETED
        mock_recorder.error_message = None
        mock_stream_recorder_class.return_value = mock_recorder
        
        result = session_manager._execute_recording_stage()
        
        assert result is True
        mock_stream_recorder_class.assert_called_once()
        mock_recorder.start_recording.assert_called_once()
        mock_recorder.set_status_callback.assert_called_once()
    
    @patch('src.services.recording_session_manager.StreamRecorder')
    def test_execute_recording_stage_start_failure(self, mock_stream_recorder_class, session_manager):
        """Test recording stage with start failure."""
        # Mock StreamRecorder
        mock_recorder = Mock()
        mock_recorder.start_recording.return_value = False
        mock_recorder.error_message = "Stream validation failed"
        mock_stream_recorder_class.return_value = mock_recorder
        
        result = session_manager._execute_recording_stage()
        
        assert result is False
        assert session_manager.current_stage == WorkflowStage.FAILED
        assert "Failed to start recording" in session_manager.error_message
    
    @patch('src.services.recording_session_manager.StreamRecorder')
    def test_execute_recording_stage_recording_failure(self, mock_stream_recorder_class, session_manager):
        """Test recording stage with recording failure."""
        # Mock StreamRecorder
        mock_recorder = Mock()
        mock_recorder.start_recording.return_value = True
        mock_recorder.status = RecordingStatus.FAILED
        mock_recorder.error_message = "Recording failed"
        mock_stream_recorder_class.return_value = mock_recorder
        
        result = session_manager._execute_recording_stage()
        
        assert result is False
        assert session_manager.current_stage == WorkflowStage.FAILED
        assert "Recording failed" in session_manager.error_message
    
    def test_execute_processing_stage_success(self, session_manager):
        """Test successful processing stage execution."""
        session_manager.raw_recording_path = "/path/to/raw.mp3"
        session_manager.processed_mp3_path = "/path/to/processed.mp3"
        session_manager.start_time = datetime.now()
        
        with patch.object(session_manager.audio_processor, 'process_audio_file', return_value=True):
            result = session_manager._execute_processing_stage()
            
            assert result is True
            session_manager.audio_processor.process_audio_file.assert_called_once()
    
    def test_execute_processing_stage_failure(self, session_manager):
        """Test processing stage with failure."""
        session_manager.raw_recording_path = "/path/to/raw.mp3"
        session_manager.processed_mp3_path = "/path/to/processed.mp3"
        
        with patch.object(session_manager.audio_processor, 'process_audio_file', return_value=False):
            result = session_manager._execute_processing_stage()
            
            assert result is False
            assert session_manager.current_stage == WorkflowStage.FAILED
            assert session_manager.error_message == "Audio processing failed"
    
    def test_execute_transfer_stage_placeholder(self, session_manager):
        """Test transfer stage (placeholder implementation)."""
        session_manager.processed_mp3_path = "/path/to/processed.mp3"
        
        result = session_manager._execute_transfer_stage()
        
        assert result is True  # Placeholder always succeeds
    
    def test_stop_recording_success(self, session_manager):
        """Test successful recording stop."""
        session_manager.current_stage = WorkflowStage.RECORDING
        session_manager.stream_recorder = Mock()
        session_manager.workflow_thread = Mock()
        session_manager.workflow_thread.is_alive.return_value = False
        
        result = session_manager.stop_recording()
        
        assert result is True
        assert session_manager.stop_event.is_set()
        session_manager.stream_recorder.stop_recording.assert_called_once()
    
    def test_stop_recording_invalid_stage(self, session_manager):
        """Test stopping recording with invalid stage."""
        session_manager.current_stage = WorkflowStage.COMPLETED
        
        result = session_manager.stop_recording()
        
        assert result is False
    
    def test_retry_workflow_success(self, session_manager):
        """Test successful workflow retry."""
        session_manager.current_stage = WorkflowStage.FAILED
        session_manager.retry_count = 1
        session_manager.max_retries = 3
        
        with patch.object(session_manager, 'start_recording', return_value=True):
            with patch.object(session_manager, '_cleanup_failed_attempt'):
                result = session_manager.retry_workflow()
                
                assert result is True
                assert session_manager.retry_count == 2
                assert session_manager.current_stage == WorkflowStage.INITIALIZING
                assert session_manager.error_message is None
    
    def test_retry_workflow_max_retries_exceeded(self, session_manager):
        """Test workflow retry with max retries exceeded."""
        session_manager.current_stage = WorkflowStage.FAILED
        session_manager.retry_count = 3
        session_manager.max_retries = 3
        
        result = session_manager.retry_workflow()
        
        assert result is False
        assert "Maximum retries" in session_manager.error_message
    
    def test_retry_workflow_invalid_stage(self, session_manager):
        """Test workflow retry with invalid stage."""
        session_manager.current_stage = WorkflowStage.RECORDING
        
        result = session_manager.retry_workflow()
        
        assert result is False
        assert "Cannot retry" in session_manager.error_message
    
    @patch('src.services.recording_session_manager.os.path.exists')
    @patch('src.services.recording_session_manager.os.remove')
    def test_cleanup_failed_attempt(self, mock_remove, mock_exists, session_manager):
        """Test cleanup of failed attempt files."""
        session_manager.raw_recording_path = "/path/to/raw.mp3"
        session_manager.processed_mp3_path = "/path/to/processed.mp3"
        mock_exists.return_value = True
        
        session_manager._cleanup_failed_attempt()
        
        assert mock_remove.call_count == 2
        mock_remove.assert_any_call("/path/to/raw.mp3")
        mock_remove.assert_any_call("/path/to/processed.mp3")
    
    @patch('src.services.recording_session_manager.os.path.exists')
    @patch('src.services.recording_session_manager.os.remove')
    def test_cleanup_temporary_files(self, mock_remove, mock_exists, session_manager):
        """Test cleanup of temporary files."""
        session_manager.raw_recording_path = "/path/to/raw.mp3"
        session_manager.processed_mp3_path = "/path/to/processed.mp3"
        mock_exists.return_value = True
        
        session_manager._cleanup_temporary_files()
        
        # Should only remove raw file, not processed file
        mock_remove.assert_called_once_with("/path/to/raw.mp3")
    
    @patch('src.services.recording_session_manager.os.path.getsize')
    @patch('src.services.recording_session_manager.os.path.exists')
    def test_get_session_info(self, mock_exists, mock_getsize, session_manager):
        """Test getting session information."""
        session_manager.start_time = datetime(2023, 1, 1, 12, 0, 0)
        session_manager.end_time = datetime(2023, 1, 1, 12, 30, 0)
        session_manager.raw_recording_path = "/path/to/raw.mp3"
        session_manager.processed_mp3_path = "/path/to/processed.mp3"
        
        mock_exists.return_value = True
        mock_getsize.side_effect = [1024000, 2048000]  # Raw and processed file sizes
        
        info = session_manager.get_session_info()
        
        assert info['session_id'] == 1
        assert info['stage'] == WorkflowStage.INITIALIZING.value
        assert info['stream_name'] == "Test Stream"
        assert info['duration_minutes'] == 30
        assert info['duration_seconds'] == 1800  # 30 minutes
        assert info['raw_file_size_bytes'] == 1024000
        assert info['processed_file_size_bytes'] == 2048000
    
    def test_status_callback(self, session_manager):
        """Test status callback functionality."""
        callback_mock = Mock()
        session_manager.set_status_callback(callback_mock)
        
        session_manager._update_status(WorkflowStage.RECORDING, {'test': 'data'})
        
        callback_mock.assert_called_once()
        args = callback_mock.call_args
        assert args[0][0] == WorkflowStage.RECORDING
        assert 'test' in args[0][1]
        assert args[0][1]['test'] == 'data'
    
    def test_progress_callback(self, session_manager):
        """Test progress callback functionality."""
        callback_mock = Mock()
        session_manager.set_progress_callback(callback_mock)
        
        session_manager._update_progress("Test operation", 50.0)
        
        callback_mock.assert_called_once_with("Test operation", 50.0)
    
    def test_context_manager(self, stream_config):
        """Test context manager functionality."""
        with patch('src.services.recording_session_manager.os.makedirs'):
            with RecordingSessionManager(1, stream_config, 30) as manager:
                assert isinstance(manager, RecordingSessionManager)
            # Cleanup should be called automatically