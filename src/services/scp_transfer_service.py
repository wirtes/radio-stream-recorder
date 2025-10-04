"""
SCPTransferService for secure file transfers using SSH/SCP.
Handles SSH key-based authentication, retry logic, and transfer monitoring.
"""

import os
import time
import logging
import threading
from datetime import datetime
from typing import Optional, Dict, Any, Callable
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

import paramiko
from paramiko import SSHClient, AutoAddPolicy
from paramiko.ssh_exception import SSHException, AuthenticationException, NoValidConnectionsError

from ..config import config


class TransferStatus(Enum):
    """Transfer status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class TransferResult:
    """Result of a file transfer operation."""
    success: bool
    status: TransferStatus
    error_message: Optional[str] = None
    bytes_transferred: int = 0
    transfer_time_seconds: float = 0.0
    retry_count: int = 0


@dataclass
class SCPConfig:
    """SCP connection configuration."""
    hostname: str
    username: str
    port: int = 22
    private_key_path: Optional[str] = None
    password: Optional[str] = None
    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 60
    cleanup_after_transfer: bool = True


class SCPTransferService:
    """
    Service for secure file transfers using SSH/SCP with retry logic and monitoring.
    """
    
    def __init__(self):
        """Initialize SCPTransferService."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._active_transfers: Dict[str, TransferResult] = {}
        self._transfer_lock = threading.Lock()
    
    def parse_scp_destination(self, scp_destination: str) -> tuple[SCPConfig, str]:
        """
        Parse SCP destination string into config and remote path.
        
        Format: username@hostname:/remote/path or username@hostname:port:/remote/path
        
        Args:
            scp_destination: SCP destination string
            
        Returns:
            Tuple of (SCPConfig, remote_path)
            
        Raises:
            ValueError: If destination format is invalid
        """
        if '@' not in scp_destination or ':' not in scp_destination:
            raise ValueError(f"Invalid SCP destination format: {scp_destination}")
        
        # Split username@hostname:path
        user_host, path_part = scp_destination.rsplit(':', 1)
        username, hostname_port = user_host.split('@', 1)
        
        # Check if port is specified
        if ':' in hostname_port:
            hostname, port_str = hostname_port.rsplit(':', 1)
            try:
                port = int(port_str)
            except ValueError:
                # Port is not a number, treat as part of hostname
                hostname = hostname_port
                port = 22
        else:
            hostname = hostname_port
            port = 22
        
        # Create config with defaults from application config
        scp_config = SCPConfig(
            hostname=hostname,
            username=username,
            port=port,
            private_key_path=self._get_default_private_key_path(),
            max_retries=config.DEFAULT_MAX_RETRIES,
            retry_delay=config.RETRY_DELAY_SECONDS,
            cleanup_after_transfer=config.CLEANUP_AFTER_TRANSFER
        )
        
        return scp_config, path_part
    
    def _get_default_private_key_path(self) -> Optional[str]:
        """Get default SSH private key path."""
        # Use the specific id_ed25519 key from config directory
        key_path = os.path.join(config.SSH_CONFIG_DIR, 'id_ed25519')
        if os.path.exists(key_path):
            return key_path
        
        # Fallback to other keys in config directory
        key_files = ['ssh_key', 'id_rsa', 'id_ecdsa']
        for key_file in key_files:
            key_path = os.path.join(config.SSH_CONFIG_DIR, key_file)
            if os.path.exists(key_path):
                return key_path
        
        return None
    
    def _create_ssh_client(self, scp_config: SCPConfig) -> SSHClient:
        """
        Create and configure SSH client.
        
        Args:
            scp_config: SCP configuration
            
        Returns:
            Configured SSH client
            
        Raises:
            AuthenticationException: If authentication fails
            SSHException: If connection fails
        """
        client = SSHClient()
        client.set_missing_host_key_policy(AutoAddPolicy())
        
        # Prepare authentication parameters
        auth_kwargs = {
            'hostname': scp_config.hostname,
            'port': scp_config.port,
            'username': scp_config.username,
            'timeout': scp_config.timeout
        }
        
        # Use private key if available, otherwise password
        if scp_config.private_key_path and os.path.exists(scp_config.private_key_path):
            try:
                # Try to load key with different key types
                private_key = None
                key_types = [
                    paramiko.Ed25519Key,
                    paramiko.RSAKey,
                    paramiko.ECDSAKey,
                    paramiko.DSSKey
                ]
                
                for key_type in key_types:
                    try:
                        private_key = key_type.from_private_key_file(scp_config.private_key_path)
                        self.logger.debug(f"Successfully loaded {key_type.__name__} from: {scp_config.private_key_path}")
                        break
                    except Exception:
                        continue
                
                if private_key:
                    auth_kwargs['pkey'] = private_key
                else:
                    raise Exception("Unable to load private key with any supported key type")
                    
            except Exception as e:
                self.logger.warning(f"Failed to load private key {scp_config.private_key_path}: {e}")
                if scp_config.password:
                    auth_kwargs['password'] = scp_config.password
        elif scp_config.password:
            auth_kwargs['password'] = scp_config.password
        else:
            raise AuthenticationException("No valid authentication method available")
        
        client.connect(**auth_kwargs)
        return client
    
    def _transfer_file_with_progress(
        self,
        local_path: str,
        remote_path: str,
        scp_config: SCPConfig,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> TransferResult:
        """
        Transfer file with progress monitoring.
        
        Args:
            local_path: Local file path
            remote_path: Remote file path
            scp_config: SCP configuration
            progress_callback: Optional progress callback function
            
        Returns:
            TransferResult with operation details
        """
        start_time = time.time()
        file_size = os.path.getsize(local_path)
        bytes_transferred = 0  # Initialize to avoid UnboundLocalError in exception handlers
        
        try:
            client = self._create_ssh_client(scp_config)
            
            try:
                # Create SCP client
                scp = client.open_sftp()
                
                # Ensure remote directory exists
                remote_dir = os.path.dirname(remote_path)
                if remote_dir and remote_dir != '/':
                    try:
                        # Try to create directory structure recursively
                        dirs_to_create = []
                        current_dir = remote_dir
                        while current_dir and current_dir != '/':
                            try:
                                scp.stat(current_dir)
                                break  # Directory exists
                            except FileNotFoundError:
                                dirs_to_create.append(current_dir)
                                current_dir = os.path.dirname(current_dir)
                        
                        # Create directories from parent to child
                        for dir_path in reversed(dirs_to_create):
                            try:
                                scp.mkdir(dir_path)
                            except Exception:
                                # Directory might already exist or permission denied
                                pass
                    except Exception as e:
                        self.logger.debug(f"Could not ensure remote directory exists: {e}")
                        # Continue anyway, the put operation might still work
                
                # Transfer file with progress monitoring
                bytes_transferred = 0
                
                def progress_wrapper(transferred, total):
                    nonlocal bytes_transferred
                    bytes_transferred = transferred
                    if progress_callback:
                        progress_callback(transferred, total)
                
                # If remote path ends with '/', append the local filename
                if remote_path.endswith('/'):
                    local_filename = os.path.basename(local_path)
                    full_remote_path = remote_path + local_filename
                else:
                    full_remote_path = remote_path
                
                self.logger.debug(f"Starting SFTP transfer: {local_path} -> {full_remote_path}")
                scp.put(local_path, full_remote_path, callback=progress_wrapper)
                self.logger.debug(f"SFTP transfer completed successfully")
                scp.close()
                
                transfer_time = time.time() - start_time
                
                self.logger.info(
                    f"Successfully transferred {local_path} to {scp_config.username}@{scp_config.hostname}:{full_remote_path} "
                    f"({file_size} bytes in {transfer_time:.2f}s)"
                )
                
                return TransferResult(
                    success=True,
                    status=TransferStatus.COMPLETED,
                    bytes_transferred=file_size,
                    transfer_time_seconds=transfer_time
                )
                
            finally:
                client.close()
                
        except (AuthenticationException, NoValidConnectionsError) as e:
            error_msg = f"Authentication/Connection failed: {str(e)}"
            self.logger.error(error_msg)
            return TransferResult(
                success=False,
                status=TransferStatus.FAILED,
                error_message=error_msg,
                bytes_transferred=bytes_transferred,
                transfer_time_seconds=time.time() - start_time
            )
            
        except SSHException as e:
            error_msg = f"SSH error during transfer: {str(e)}"
            self.logger.error(error_msg)
            return TransferResult(
                success=False,
                status=TransferStatus.FAILED,
                error_message=error_msg,
                bytes_transferred=bytes_transferred,
                transfer_time_seconds=time.time() - start_time
            )
            
        except Exception as e:
            error_msg = f"Unexpected error during transfer: {str(e)}"
            self.logger.error(f"{error_msg} (Type: {type(e).__name__})")
            self.logger.error(f"Local path: {local_path}")
            self.logger.error(f"Remote path: {remote_path}")
            self.logger.error(f"File size: {file_size} bytes")
            import traceback
            self.logger.error(f"Full traceback: {traceback.format_exc()}")
            return TransferResult(
                success=False,
                status=TransferStatus.FAILED,
                error_message=error_msg,
                bytes_transferred=bytes_transferred,
                transfer_time_seconds=time.time() - start_time
            )
    
    def transfer_file(
        self,
        local_path: str,
        scp_destination: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        custom_config: Optional[SCPConfig] = None
    ) -> TransferResult:
        """
        Transfer a file to remote destination with retry logic.
        
        Args:
            local_path: Path to local file
            scp_destination: SCP destination string (user@host:/path)
            progress_callback: Optional progress callback function
            custom_config: Optional custom SCP configuration
            
        Returns:
            TransferResult with operation details
        """
        if not os.path.exists(local_path):
            return TransferResult(
                success=False,
                status=TransferStatus.FAILED,
                error_message=f"Local file not found: {local_path}"
            )
        
        # Parse destination or use custom config
        if custom_config:
            scp_config = custom_config
            remote_path = scp_destination  # Assume it's just the path when using custom config
        else:
            try:
                scp_config, remote_path = self.parse_scp_destination(scp_destination)
                self.logger.debug(f"Parsed SCP destination: {scp_config.username}@{scp_config.hostname}:{remote_path}")
            except ValueError as e:
                return TransferResult(
                    success=False,
                    status=TransferStatus.FAILED,
                    error_message=str(e)
                )
        
        # Track transfer
        transfer_id = f"{local_path}_{datetime.now().isoformat()}"
        
        with self._transfer_lock:
            self._active_transfers[transfer_id] = TransferResult(
                success=False,
                status=TransferStatus.PENDING
            )
        
        # Attempt transfer with retry logic
        last_result = None
        
        for attempt in range(scp_config.max_retries + 1):
            if attempt > 0:
                self.logger.info(f"Retrying transfer attempt {attempt + 1}/{scp_config.max_retries + 1}")
                
                with self._transfer_lock:
                    self._active_transfers[transfer_id].status = TransferStatus.RETRYING
                    self._active_transfers[transfer_id].retry_count = attempt
                
                time.sleep(scp_config.retry_delay * (2 ** (attempt - 1)))  # Exponential backoff
            
            # Update status to in progress
            with self._transfer_lock:
                self._active_transfers[transfer_id].status = TransferStatus.IN_PROGRESS
            
            # Attempt transfer
            result = self._transfer_file_with_progress(
                local_path, remote_path, scp_config, progress_callback
            )
            result.retry_count = attempt
            last_result = result
            
            if result.success:
                # Cleanup local file if configured
                if scp_config.cleanup_after_transfer:
                    try:
                        os.remove(local_path)
                        self.logger.info(f"Cleaned up local file: {local_path}")
                    except Exception as e:
                        self.logger.warning(f"Failed to cleanup local file {local_path}: {e}")
                
                break
            else:
                self.logger.warning(f"Transfer attempt {attempt + 1} failed: {result.error_message}")
        
        # Update final status
        with self._transfer_lock:
            self._active_transfers[transfer_id] = last_result
        
        return last_result
    
    def get_transfer_status(self, transfer_id: str) -> Optional[TransferResult]:
        """
        Get status of a transfer operation.
        
        Args:
            transfer_id: Transfer identifier
            
        Returns:
            TransferResult if found, None otherwise
        """
        with self._transfer_lock:
            return self._active_transfers.get(transfer_id)
    
    def get_active_transfers(self) -> Dict[str, TransferResult]:
        """
        Get all active transfers.
        
        Returns:
            Dictionary of transfer_id -> TransferResult
        """
        with self._transfer_lock:
            return self._active_transfers.copy()
    
    def test_connection(self, scp_destination: str, custom_config: Optional[SCPConfig] = None) -> bool:
        """
        Test SSH connection to remote host.
        
        Args:
            scp_destination: SCP destination string
            custom_config: Optional custom SCP configuration
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            if custom_config:
                scp_config = custom_config
            else:
                scp_config, _ = self.parse_scp_destination(scp_destination)
            
            client = self._create_ssh_client(scp_config)
            client.close()
            
            self.logger.info(f"Connection test successful to {scp_config.username}@{scp_config.hostname}")
            return True
            
        except Exception as e:
            self.logger.error(f"Connection test failed: {str(e)}")
            return False