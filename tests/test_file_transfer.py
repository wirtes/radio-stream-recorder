"""
Unit tests for file transfer components.
Tests SCPTransferService and TransferQueue with mocked SSH/SCP operations.
"""

import pytest
import tempfile
import os
import time
import json
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path

from src.services.scp_transfer_service import (
    SCPTransferService, 
    TransferResult, 
    TransferStatus, 
    SCPConfig
)
from src.services.transfer_queue import TransferQueue, QueuedTransfer


class TestSCPTransferService:
    """Test cases for SCPTransferService."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = SCPTransferService()
    
    def test_parse_scp_destination_basic(self):
        """Test parsing basic SCP destination string."""
        destination = "user@example.com:/remote/path"
        config, remote_path = self.service.parse_scp_destination(destination)
        
        assert config.hostname == "example.com"
        assert config.username == "user"
        assert config.port == 22
        assert remote_path == "/remote/path"
    
    def test_parse_scp_destination_with_port(self):
        """Test parsing SCP destination with custom port."""
        destination = "user@example.com:2222:/remote/path"
        config, remote_path = self.service.parse_scp_destination(destination)
        
        assert config.hostname == "example.com"
        assert config.username == "user"
        assert config.port == 2222
        assert remote_path == "/remote/path"
    
    def test_parse_scp_destination_invalid_format(self):
        """Test parsing invalid SCP destination format."""
        with pytest.raises(ValueError, match="Invalid SCP destination format"):
            self.service.parse_scp_destination("invalid-format")
        
        with pytest.raises(ValueError, match="Invalid SCP destination format"):
            self.service.parse_scp_destination("user@host")  # Missing path
    
    @patch('src.services.scp_transfer_service.os.path.exists')
    def test_get_default_private_key_path(self, mock_exists):
        """Test finding default SSH private key."""
        # Mock key file exists in SSH config directory
        mock_exists.side_effect = lambda path: 'config/id_rsa' in path
        
        key_path = self.service._get_default_private_key_path()
        assert key_path is not None
        assert 'id_rsa' in key_path
    
    @patch('src.services.scp_transfer_service.os.path.exists')
    def test_get_default_private_key_path_not_found(self, mock_exists):
        """Test when no SSH private key is found."""
        mock_exists.return_value = False
        
        key_path = self.service._get_default_private_key_path()
        assert key_path is None
    
    @patch('src.services.scp_transfer_service.paramiko.SSHClient')
    @patch('src.services.scp_transfer_service.paramiko.RSAKey')
    @patch('src.services.scp_transfer_service.os.path.exists')
    def test_create_ssh_client_with_key(self, mock_exists, mock_rsa_key, mock_ssh_client):
        """Test creating SSH client with private key authentication."""
        mock_exists.return_value = True
        mock_key = Mock()
        mock_rsa_key.from_private_key_file.return_value = mock_key
        mock_client = Mock()
        mock_ssh_client.return_value = mock_client
        
        config = SCPConfig(
            hostname="example.com",
            username="user",
            private_key_path="/path/to/key"
        )
        
        client = self.service._create_ssh_client(config)
        
        assert client == mock_client
        mock_client.connect.assert_called_once()
        connect_args = mock_client.connect.call_args[1]
        assert connect_args['hostname'] == "example.com"
        assert connect_args['username'] == "user"
        assert connect_args['pkey'] == mock_key
    
    @patch('src.services.scp_transfer_service.paramiko.SSHClient')
    def test_create_ssh_client_with_password(self, mock_ssh_client):
        """Test creating SSH client with password authentication."""
        mock_client = Mock()
        mock_ssh_client.return_value = mock_client
        
        config = SCPConfig(
            hostname="example.com",
            username="user",
            password="secret"
        )
        
        client = self.service._create_ssh_client(config)
        
        assert client == mock_client
        mock_client.connect.assert_called_once()
        connect_args = mock_client.connect.call_args[1]
        assert connect_args['password'] == "secret"
    
    def test_create_ssh_client_no_auth(self):
        """Test creating SSH client without authentication method."""
        config = SCPConfig(
            hostname="example.com",
            username="user"
        )
        
        with pytest.raises(Exception):  # Should raise AuthenticationException
            self.service._create_ssh_client(config)
    
    @patch('src.services.scp_transfer_service.os.path.getsize')
    @patch('src.services.scp_transfer_service.time.time')
    def test_transfer_file_with_progress_success(self, mock_time, mock_getsize):
        """Test successful file transfer with progress monitoring."""
        # Setup mocks
        mock_getsize.return_value = 1024
        mock_time.side_effect = [0.0, 2.0]  # Start and end times
        
        mock_client = Mock()
        mock_scp = Mock()
        mock_client.open_sftp.return_value = mock_scp
        
        with patch.object(self.service, '_create_ssh_client', return_value=mock_client):
            config = SCPConfig(hostname="example.com", username="user", password="secret")
            
            result = self.service._transfer_file_with_progress(
                "/local/file.mp3",
                "/remote/file.mp3",
                config
            )
        
        assert result.success is True
        assert result.status == TransferStatus.COMPLETED
        assert result.bytes_transferred == 1024
        assert result.transfer_time_seconds == 2.0
        
        mock_scp.put.assert_called_once()
        mock_scp.close.assert_called_once()
        mock_client.close.assert_called_once()
    
    @patch('src.services.scp_transfer_service.os.path.getsize')
    @patch('src.services.scp_transfer_service.time.time')
    def test_transfer_file_with_progress_ssh_error(self, mock_time, mock_getsize):
        """Test file transfer with SSH error."""
        mock_getsize.return_value = 1024
        mock_time.side_effect = [0.0, 1.0]
        
        with patch.object(self.service, '_create_ssh_client', side_effect=Exception("SSH Error")):
            config = SCPConfig(hostname="example.com", username="user", password="secret")
            
            result = self.service._transfer_file_with_progress(
                "/local/file.mp3",
                "/remote/file.mp3",
                config
            )
        
        assert result.success is False
        assert result.status == TransferStatus.FAILED
        assert "SSH Error" in result.error_message
    
    @patch('src.services.scp_transfer_service.os.path.exists')
    def test_transfer_file_local_file_not_found(self, mock_exists):
        """Test transfer when local file doesn't exist."""
        mock_exists.return_value = False
        
        result = self.service.transfer_file(
            "/nonexistent/file.mp3",
            "user@host:/remote/path"
        )
        
        assert result.success is False
        assert result.status == TransferStatus.FAILED
        assert "Local file not found" in result.error_message
    
    @patch('src.services.scp_transfer_service.os.path.exists')
    @patch('src.services.scp_transfer_service.os.remove')
    def test_transfer_file_with_cleanup(self, mock_remove, mock_exists):
        """Test file transfer with local file cleanup."""
        mock_exists.return_value = True
        
        # Mock successful transfer
        mock_result = TransferResult(
            success=True,
            status=TransferStatus.COMPLETED,
            bytes_transferred=1024,
            transfer_time_seconds=1.0
        )
        
        with patch.object(self.service, '_transfer_file_with_progress', return_value=mock_result):
            with patch.object(self.service, 'parse_scp_destination') as mock_parse:
                config = SCPConfig(
                    hostname="example.com",
                    username="user",
                    password="secret",
                    cleanup_after_transfer=True
                )
                mock_parse.return_value = (config, "/remote/path")
                
                result = self.service.transfer_file(
                    "/local/file.mp3",
                    "user@host:/remote/path"
                )
        
        assert result.success is True
        mock_remove.assert_called_once_with("/local/file.mp3")
    
    @patch('src.services.scp_transfer_service.os.path.exists')
    def test_transfer_file_with_retries(self, mock_exists):
        """Test file transfer with retry logic."""
        mock_exists.return_value = True
        
        # Mock first attempt fails, second succeeds
        failed_result = TransferResult(
            success=False,
            status=TransferStatus.FAILED,
            error_message="Connection failed"
        )
        success_result = TransferResult(
            success=True,
            status=TransferStatus.COMPLETED,
            bytes_transferred=1024
        )
        
        with patch.object(self.service, '_transfer_file_with_progress', side_effect=[failed_result, success_result]):
            with patch.object(self.service, 'parse_scp_destination') as mock_parse:
                config = SCPConfig(
                    hostname="example.com",
                    username="user",
                    password="secret",
                    max_retries=2,
                    retry_delay=0  # No delay for testing
                )
                mock_parse.return_value = (config, "/remote/path")
                
                with patch('src.services.scp_transfer_service.time.sleep'):  # Mock sleep
                    result = self.service.transfer_file(
                        "/local/file.mp3",
                        "user@host:/remote/path"
                    )
        
        assert result.success is True
        assert result.retry_count == 1
    
    def test_test_connection_success(self):
        """Test successful connection test."""
        mock_client = Mock()
        
        with patch.object(self.service, '_create_ssh_client', return_value=mock_client):
            with patch.object(self.service, 'parse_scp_destination') as mock_parse:
                config = SCPConfig(hostname="example.com", username="user", password="secret")
                mock_parse.return_value = (config, "/remote/path")
                
                result = self.service.test_connection("user@host:/remote/path")
        
        assert result is True
        mock_client.close.assert_called_once()
    
    def test_test_connection_failure(self):
        """Test failed connection test."""
        with patch.object(self.service, '_create_ssh_client', side_effect=Exception("Connection failed")):
            with patch.object(self.service, 'parse_scp_destination') as mock_parse:
                config = SCPConfig(hostname="example.com", username="user", password="secret")
                mock_parse.return_value = (config, "/remote/path")
                
                result = self.service.test_connection("user@host:/remote/path")
        
        assert result is False


class TestTransferQueue:
    """Test cases for TransferQueue."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create temporary database
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix='.db')
        os.close(self.temp_db_fd)
        
        self.queue = TransferQueue(db_path=self.temp_db_path)
    
    def teardown_method(self):
        """Clean up test fixtures."""
        if hasattr(self, 'queue'):
            self.queue.stop_worker()
        if os.path.exists(self.temp_db_path):
            os.unlink(self.temp_db_path)
    
    def test_init_database(self):
        """Test database initialization."""
        # Check that tables were created
        with sqlite3.connect(self.temp_db_path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor]
            assert 'transfer_queue' in tables
    
    def test_queued_transfer_serialization(self):
        """Test QueuedTransfer serialization and deserialization."""
        now = datetime.now()
        transfer = QueuedTransfer(
            id="test_id",
            local_path="/local/file.mp3",
            scp_destination="user@host:/remote/path",
            created_at=now,
            scheduled_at=now,
            retry_count=1,
            metadata={"key": "value"}
        )
        
        # Test to_dict
        data = transfer.to_dict()
        assert data['id'] == "test_id"
        assert data['retry_count'] == 1
        assert data['metadata'] == {"key": "value"}
        assert isinstance(data['created_at'], str)
        
        # Test from_dict
        restored = QueuedTransfer.from_dict(data)
        assert restored.id == transfer.id
        assert restored.retry_count == transfer.retry_count
        assert restored.metadata == transfer.metadata
        assert isinstance(restored.created_at, datetime)
    
    @patch('src.services.transfer_queue.os.path.exists')
    def test_add_transfer(self, mock_exists):
        """Test adding transfer to queue."""
        mock_exists.return_value = True
        
        transfer_id = self.queue.add_transfer(
            local_path="/local/file.mp3",
            scp_destination="user@host:/remote/path",
            priority=5,
            metadata={"test": "data"}
        )
        
        assert transfer_id.startswith("transfer_")
        
        # Check database
        with sqlite3.connect(self.temp_db_path) as conn:
            cursor = conn.execute("SELECT * FROM transfer_queue WHERE id = ?", (transfer_id,))
            row = cursor.fetchone()
            assert row is not None
            assert row[1] == "/local/file.mp3"  # local_path
            assert row[8] == 5  # priority
    
    def test_add_transfer_file_not_found(self):
        """Test adding transfer when local file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            self.queue.add_transfer(
                local_path="/nonexistent/file.mp3",
                scp_destination="user@host:/remote/path"
            )
    
    @patch('src.services.transfer_queue.os.path.exists')
    def test_retry_failed_transfer(self, mock_exists):
        """Test retrying a failed transfer."""
        mock_exists.return_value = True
        
        # Add initial transfer
        transfer_id = self.queue.add_transfer(
            local_path="/local/file.mp3",
            scp_destination="user@host:/remote/path",
            max_retries=3
        )
        
        # Simulate failure by updating retry count
        with sqlite3.connect(self.temp_db_path) as conn:
            conn.execute(
                "UPDATE transfer_queue SET retry_count = 1, status = 'failed' WHERE id = ?",
                (transfer_id,)
            )
            conn.commit()
        
        # Retry transfer
        result = self.queue.retry_failed_transfer(transfer_id)
        assert result is True
        
        # Check that retry count was incremented
        with sqlite3.connect(self.temp_db_path) as conn:
            cursor = conn.execute("SELECT retry_count FROM transfer_queue WHERE id = ?", (transfer_id,))
            row = cursor.fetchone()
            assert row[0] == 2
    
    @patch('src.services.transfer_queue.os.path.exists')
    def test_retry_failed_transfer_max_retries_exceeded(self, mock_exists):
        """Test retrying transfer when max retries exceeded."""
        mock_exists.return_value = True
        
        # Add transfer with max retries already reached
        transfer_id = self.queue.add_transfer(
            local_path="/local/file.mp3",
            scp_destination="user@host:/remote/path",
            max_retries=2
        )
        
        # Set retry count to max
        with sqlite3.connect(self.temp_db_path) as conn:
            conn.execute(
                "UPDATE transfer_queue SET retry_count = 2, status = 'failed' WHERE id = ?",
                (transfer_id,)
            )
            conn.commit()
        
        # Attempt retry
        result = self.queue.retry_failed_transfer(transfer_id)
        assert result is False
    
    def test_get_queue_status(self):
        """Test getting queue status."""
        status = self.queue.get_queue_status()
        
        assert 'memory_queue_size' in status
        assert 'ready_for_processing' in status
        assert 'status_counts' in status
        assert 'worker_running' in status
        assert isinstance(status['memory_queue_size'], int)
    
    @patch('src.services.transfer_queue.os.path.exists')
    def test_get_pending_transfers(self, mock_exists):
        """Test getting list of pending transfers."""
        mock_exists.return_value = True
        
        # Add some transfers
        transfer_id1 = self.queue.add_transfer(
            local_path="/local/file1.mp3",
            scp_destination="user@host:/remote/path1",
            priority=1
        )
        transfer_id2 = self.queue.add_transfer(
            local_path="/local/file2.mp3",
            scp_destination="user@host:/remote/path2",
            priority=2
        )
        
        pending = self.queue.get_pending_transfers()
        
        assert len(pending) == 2
        # Should be ordered by priority (higher first)
        assert pending[0]['priority'] == 2
        assert pending[1]['priority'] == 1
    
    @patch('src.services.transfer_queue.os.path.exists')
    def test_remove_transfer(self, mock_exists):
        """Test removing transfer from queue."""
        mock_exists.return_value = True
        
        transfer_id = self.queue.add_transfer(
            local_path="/local/file.mp3",
            scp_destination="user@host:/remote/path"
        )
        
        result = self.queue.remove_transfer(transfer_id)
        assert result is True
        
        # Check that transfer was removed from database
        with sqlite3.connect(self.temp_db_path) as conn:
            cursor = conn.execute("SELECT * FROM transfer_queue WHERE id = ?", (transfer_id,))
            row = cursor.fetchone()
            assert row is None
    
    @patch('src.services.transfer_queue.os.path.exists')
    def test_cleanup_completed_transfers(self, mock_exists):
        """Test cleaning up old completed transfers."""
        mock_exists.return_value = True
        
        # Add transfer and mark as completed with old date
        transfer_id = self.queue.add_transfer(
            local_path="/local/file.mp3",
            scp_destination="user@host:/remote/path"
        )
        
        old_date = datetime.now() - timedelta(days=10)
        with sqlite3.connect(self.temp_db_path) as conn:
            conn.execute(
                "UPDATE transfer_queue SET status = 'completed', created_at = ? WHERE id = ?",
                (old_date.isoformat(), transfer_id)
            )
            conn.commit()
        
        # Cleanup transfers older than 7 days
        removed_count = self.queue.cleanup_completed_transfers(older_than_days=7)
        assert removed_count == 1
        
        # Check that transfer was removed
        with sqlite3.connect(self.temp_db_path) as conn:
            cursor = conn.execute("SELECT * FROM transfer_queue WHERE id = ?", (transfer_id,))
            row = cursor.fetchone()
            assert row is None
    
    @patch('src.services.transfer_queue.os.path.exists')
    @patch('src.services.transfer_queue.time.sleep')
    def test_worker_loop_successful_transfer(self, mock_sleep, mock_exists):
        """Test worker loop processing successful transfer."""
        mock_exists.return_value = True
        mock_sleep.return_value = None  # Speed up test
        
        # Mock successful transfer
        mock_result = TransferResult(
            success=True,
            status=TransferStatus.COMPLETED,
            bytes_transferred=1024
        )
        
        with patch.object(self.queue.scp_service, 'transfer_file', return_value=mock_result):
            # Add transfer
            transfer_id = self.queue.add_transfer(
                local_path="/local/file.mp3",
                scp_destination="user@host:/remote/path"
            )
            
            # Start worker briefly
            self.queue.start_worker()
            time.sleep(0.1)  # Let worker process
            self.queue.stop_worker()
            
            # Check that transfer was completed and removed
            with sqlite3.connect(self.temp_db_path) as conn:
                cursor = conn.execute("SELECT * FROM transfer_queue WHERE id = ?", (transfer_id,))
                row = cursor.fetchone()
                assert row is None  # Should be removed after completion
    
    @patch('src.services.transfer_queue.os.path.exists')
    @patch('src.services.transfer_queue.time.sleep')
    def test_worker_loop_failed_transfer_with_retry(self, mock_sleep, mock_exists):
        """Test worker loop processing failed transfer with retry."""
        mock_exists.return_value = True
        mock_sleep.return_value = None
        
        # Mock failed transfer
        mock_result = TransferResult(
            success=False,
            status=TransferStatus.FAILED,
            error_message="Connection failed"
        )
        
        with patch.object(self.queue.scp_service, 'transfer_file', return_value=mock_result):
            # Add transfer with retries
            transfer_id = self.queue.add_transfer(
                local_path="/local/file.mp3",
                scp_destination="user@host:/remote/path",
                max_retries=2
            )
            
            # Start worker briefly
            self.queue.start_worker()
            time.sleep(0.1)
            self.queue.stop_worker()
            
            # Check that transfer was updated with retry info
            with sqlite3.connect(self.temp_db_path) as conn:
                cursor = conn.execute("SELECT retry_count, status FROM transfer_queue WHERE id = ?", (transfer_id,))
                row = cursor.fetchone()
                assert row is not None
                assert row[0] > 0  # retry_count should be incremented
    
    def test_start_stop_worker(self):
        """Test starting and stopping worker thread."""
        assert not self.queue._running
        
        self.queue.start_worker()
        assert self.queue._running
        assert self.queue._worker_thread is not None
        
        self.queue.stop_worker()
        assert not self.queue._running