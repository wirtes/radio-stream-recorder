"""
TransferQueue for managing failed file transfers and retry attempts.
Provides queue system for retry attempts and transfer status tracking.
"""

import os
import json
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from queue import Queue, Empty
import sqlite3

from .scp_transfer_service import SCPTransferService, TransferResult, TransferStatus, SCPConfig
from ..config import config


@dataclass
class QueuedTransfer:
    """Represents a queued transfer operation."""
    id: str
    local_path: str
    scp_destination: str
    created_at: datetime
    scheduled_at: datetime
    retry_count: int = 0
    max_retries: int = 3
    last_error: Optional[str] = None
    priority: int = 0  # Higher number = higher priority
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        data['scheduled_at'] = self.scheduled_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueuedTransfer':
        """Create from dictionary."""
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['scheduled_at'] = datetime.fromisoformat(data['scheduled_at'])
        return cls(**data)


class TransferQueue:
    """
    Queue system for managing failed transfers and retry attempts.
    Provides persistent storage and automatic retry scheduling.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize TransferQueue.
        
        Args:
            db_path: Path to SQLite database file (defaults to data/transfer_queue.db)
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.db_path = db_path or os.path.join('data', 'transfer_queue.db')
        self.scp_service = SCPTransferService()
        
        # Thread-safe queue and locks
        self._queue: Queue[QueuedTransfer] = Queue()
        self._queue_lock = threading.Lock()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # Initialize database
        self._init_database()
        self._load_queue_from_db()
    
    def _init_database(self) -> None:
        """Initialize SQLite database for persistent queue storage."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS transfer_queue (
                    id TEXT PRIMARY KEY,
                    local_path TEXT NOT NULL,
                    scp_destination TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    last_error TEXT,
                    priority INTEGER DEFAULT 0,
                    metadata TEXT,
                    status TEXT DEFAULT 'queued'
                )
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_scheduled_at ON transfer_queue(scheduled_at)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_priority ON transfer_queue(priority DESC)
            ''')
            
            conn.commit()
    
    def _load_queue_from_db(self) -> None:
        """Load pending transfers from database into memory queue."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM transfer_queue 
                WHERE status = 'queued' AND scheduled_at <= ?
                ORDER BY priority DESC, scheduled_at ASC
            ''', (datetime.now().isoformat(),))
            
            for row in cursor:
                transfer_data = dict(row)
                # Parse metadata if present
                if transfer_data['metadata']:
                    transfer_data['metadata'] = json.loads(transfer_data['metadata'])
                else:
                    transfer_data['metadata'] = None
                
                # Remove status field as it's not part of QueuedTransfer
                del transfer_data['status']
                
                queued_transfer = QueuedTransfer.from_dict(transfer_data)
                self._queue.put(queued_transfer)
                
                self.logger.debug(f"Loaded queued transfer: {queued_transfer.id}")
    
    def _save_transfer_to_db(self, transfer: QueuedTransfer, status: str = 'queued') -> None:
        """Save transfer to database."""
        with sqlite3.connect(self.db_path) as conn:
            metadata_json = json.dumps(transfer.metadata) if transfer.metadata else None
            
            conn.execute('''
                INSERT OR REPLACE INTO transfer_queue 
                (id, local_path, scp_destination, created_at, scheduled_at, 
                 retry_count, max_retries, last_error, priority, metadata, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                transfer.id, transfer.local_path, transfer.scp_destination,
                transfer.created_at.isoformat(), transfer.scheduled_at.isoformat(),
                transfer.retry_count, transfer.max_retries, transfer.last_error,
                transfer.priority, metadata_json, status
            ))
            conn.commit()
    
    def _remove_transfer_from_db(self, transfer_id: str) -> None:
        """Remove transfer from database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM transfer_queue WHERE id = ?', (transfer_id,))
            conn.commit()
    
    def _update_transfer_status_in_db(self, transfer_id: str, status: str, last_error: Optional[str] = None) -> None:
        """Update transfer status in database."""
        with sqlite3.connect(self.db_path) as conn:
            if last_error:
                conn.execute('''
                    UPDATE transfer_queue 
                    SET status = ?, last_error = ? 
                    WHERE id = ?
                ''', (status, last_error, transfer_id))
            else:
                conn.execute('''
                    UPDATE transfer_queue 
                    SET status = ? 
                    WHERE id = ?
                ''', (status, transfer_id))
            conn.commit()
    
    def add_transfer(
        self,
        local_path: str,
        scp_destination: str,
        priority: int = 0,
        max_retries: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        delay_seconds: int = 0
    ) -> str:
        """
        Add a transfer to the queue.
        
        Args:
            local_path: Path to local file
            scp_destination: SCP destination string
            priority: Transfer priority (higher = more important)
            max_retries: Maximum retry attempts (defaults to config value)
            metadata: Optional metadata dictionary
            delay_seconds: Delay before first attempt
            
        Returns:
            Transfer ID
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local file not found: {local_path}")
        
        transfer_id = f"transfer_{int(time.time() * 1000)}_{os.path.basename(local_path)}"
        now = datetime.now()
        scheduled_at = now + timedelta(seconds=delay_seconds)
        
        queued_transfer = QueuedTransfer(
            id=transfer_id,
            local_path=local_path,
            scp_destination=scp_destination,
            created_at=now,
            scheduled_at=scheduled_at,
            retry_count=0,
            max_retries=max_retries or config.DEFAULT_MAX_RETRIES,
            priority=priority,
            metadata=metadata
        )
        
        # Save to database
        self._save_transfer_to_db(queued_transfer)
        
        # Add to memory queue if scheduled time has passed
        if scheduled_at <= now:
            with self._queue_lock:
                self._queue.put(queued_transfer)
        
        self.logger.info(f"Added transfer to queue: {transfer_id} (priority: {priority})")
        return transfer_id
    
    def retry_failed_transfer(self, transfer_id: str, delay_seconds: int = 0) -> bool:
        """
        Retry a failed transfer.
        
        Args:
            transfer_id: Transfer ID to retry
            delay_seconds: Delay before retry attempt
            
        Returns:
            True if transfer was queued for retry, False if not found or max retries exceeded
        """
        # Load transfer from database
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('SELECT * FROM transfer_queue WHERE id = ?', (transfer_id,))
            row = cursor.fetchone()
            
            if not row:
                self.logger.warning(f"Transfer not found for retry: {transfer_id}")
                return False
            
            transfer_data = dict(row)
            if transfer_data['metadata']:
                transfer_data['metadata'] = json.loads(transfer_data['metadata'])
            else:
                transfer_data['metadata'] = None
            
            del transfer_data['status']  # Remove status field
            queued_transfer = QueuedTransfer.from_dict(transfer_data)
        
        # Check if max retries exceeded
        if queued_transfer.retry_count >= queued_transfer.max_retries:
            self.logger.warning(f"Max retries exceeded for transfer: {transfer_id}")
            return False
        
        # Update retry count and schedule time
        queued_transfer.retry_count += 1
        queued_transfer.scheduled_at = datetime.now() + timedelta(seconds=delay_seconds)
        
        # Save updated transfer
        self._save_transfer_to_db(queued_transfer)
        
        # Add to memory queue
        with self._queue_lock:
            self._queue.put(queued_transfer)
        
        self.logger.info(f"Queued transfer for retry: {transfer_id} (attempt {queued_transfer.retry_count})")
        return True
    
    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get current queue status.
        
        Returns:
            Dictionary with queue statistics
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT status, COUNT(*) as count FROM transfer_queue GROUP BY status')
            status_counts = {row[0]: row[1] for row in cursor}
            
            cursor = conn.execute('SELECT COUNT(*) FROM transfer_queue WHERE scheduled_at <= ?', 
                                (datetime.now().isoformat(),))
            ready_count = cursor.fetchone()[0]
        
        with self._queue_lock:
            memory_queue_size = self._queue.qsize()
        
        return {
            'memory_queue_size': memory_queue_size,
            'ready_for_processing': ready_count,
            'status_counts': status_counts,
            'worker_running': self._running
        }
    
    def get_pending_transfers(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get list of pending transfers.
        
        Args:
            limit: Maximum number of transfers to return
            
        Returns:
            List of transfer dictionaries
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM transfer_queue 
                WHERE status IN ('queued', 'processing', 'failed')
                ORDER BY priority DESC, scheduled_at ASC
                LIMIT ?
            ''', (limit,))
            
            transfers = []
            for row in cursor:
                transfer_data = dict(row)
                if transfer_data['metadata']:
                    transfer_data['metadata'] = json.loads(transfer_data['metadata'])
                transfers.append(transfer_data)
            
            return transfers
    
    def remove_transfer(self, transfer_id: str) -> bool:
        """
        Remove a transfer from the queue.
        
        Args:
            transfer_id: Transfer ID to remove
            
        Returns:
            True if transfer was removed, False if not found
        """
        self._remove_transfer_from_db(transfer_id)
        self.logger.info(f"Removed transfer from queue: {transfer_id}")
        return True
    
    def start_worker(self) -> None:
        """Start the background worker thread for processing transfers."""
        if self._running:
            self.logger.warning("Worker thread is already running")
            return
        
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        self.logger.info("Started transfer queue worker thread")
    
    def stop_worker(self) -> None:
        """Stop the background worker thread."""
        if not self._running:
            return
        
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        self.logger.info("Stopped transfer queue worker thread")
    
    def _worker_loop(self) -> None:
        """Main worker loop for processing queued transfers."""
        self.logger.info("Transfer queue worker started")
        
        while self._running:
            try:
                # Get next transfer from queue (with timeout to allow checking _running)
                try:
                    transfer = self._queue.get(timeout=1.0)
                except Empty:
                    continue
                
                # Check if scheduled time has arrived
                if transfer.scheduled_at > datetime.now():
                    # Put back in queue and wait
                    with self._queue_lock:
                        self._queue.put(transfer)
                    time.sleep(1.0)
                    continue
                
                # Check if file still exists
                if not os.path.exists(transfer.local_path):
                    self.logger.warning(f"Local file no longer exists: {transfer.local_path}")
                    self._update_transfer_status_in_db(transfer.id, 'failed', 'Local file not found')
                    continue
                
                # Update status to processing
                self._update_transfer_status_in_db(transfer.id, 'processing')
                
                # Attempt transfer
                self.logger.info(f"Processing transfer: {transfer.id} (attempt {transfer.retry_count + 1})")
                
                result = self.scp_service.transfer_file(
                    local_path=transfer.local_path,
                    scp_destination=transfer.scp_destination
                )
                
                if result.success:
                    # Transfer successful
                    self.logger.info(f"Transfer completed successfully: {transfer.id}")
                    self._update_transfer_status_in_db(transfer.id, 'completed')
                    self._remove_transfer_from_db(transfer.id)
                else:
                    # Transfer failed
                    transfer.last_error = result.error_message
                    transfer.retry_count += 1
                    
                    if transfer.retry_count < transfer.max_retries:
                        # Schedule retry with exponential backoff
                        delay = config.RETRY_DELAY_SECONDS * (2 ** (transfer.retry_count - 1))
                        transfer.scheduled_at = datetime.now() + timedelta(seconds=delay)
                        
                        self.logger.warning(
                            f"Transfer failed, scheduling retry: {transfer.id} "
                            f"(attempt {transfer.retry_count}/{transfer.max_retries}) in {delay}s"
                        )
                        
                        self._save_transfer_to_db(transfer, 'queued')
                        with self._queue_lock:
                            self._queue.put(transfer)
                    else:
                        # Max retries exceeded
                        self.logger.error(f"Transfer failed permanently: {transfer.id} - {result.error_message}")
                        self._update_transfer_status_in_db(transfer.id, 'failed', result.error_message)
                
            except Exception as e:
                self.logger.error(f"Error in transfer worker loop: {str(e)}", exc_info=True)
                time.sleep(1.0)
        
        self.logger.info("Transfer queue worker stopped")
    
    def cleanup_completed_transfers(self, older_than_days: int = 7) -> int:
        """
        Clean up completed transfers older than specified days.
        
        Args:
            older_than_days: Remove completed transfers older than this many days
            
        Returns:
            Number of transfers removed
        """
        cutoff_date = datetime.now() - timedelta(days=older_than_days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                DELETE FROM transfer_queue 
                WHERE status = 'completed' AND created_at < ?
            ''', (cutoff_date.isoformat(),))
            
            removed_count = cursor.rowcount
            conn.commit()
        
        if removed_count > 0:
            self.logger.info(f"Cleaned up {removed_count} completed transfers older than {older_than_days} days")
        
        return removed_count