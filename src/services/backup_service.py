"""
Configuration backup and restore service for Audio Stream Recorder.
Handles automatic and manual backup/restore of system configuration.
"""

import os
import json
import shutil
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import zipfile
import tempfile

from src.config import Config
from src.models.database import DatabaseManager
from src.models.repositories import ConfigurationRepository, ScheduleRepository
from .config_migration import ConfigMigration

logger = logging.getLogger(__name__)


class BackupService:
    """Service for configuration backup and restore operations."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.config_repo = ConfigurationRepository(db_manager)
        self.schedule_repo = ScheduleRepository(db_manager)
        self.backup_dir = os.path.join(Config.DATA_DIR, 'backups')
        self.migration_tool = ConfigMigration()
        self.ensure_backup_directory()
    
    def ensure_backup_directory(self) -> None:
        """Ensure backup directory exists."""
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def create_backup(self, backup_name: Optional[str] = None, include_artwork: bool = True) -> Dict[str, Any]:
        """
        Create a complete configuration backup.
        
        Args:
            backup_name: Optional custom name for the backup
            include_artwork: Whether to include artwork files in backup
            
        Returns:
            Dictionary with backup information
        """
        try:
            from ..utils.timezone_utils import get_local_now
            timestamp = get_local_now()
            if not backup_name:
                backup_name = f"backup_{timestamp.strftime('%Y%m%d_%H%M%S')}"
            
            backup_filename = f"{backup_name}.zip"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # Create temporary directory for backup preparation
            with tempfile.TemporaryDirectory() as temp_dir:
                backup_data = {
                    'metadata': {
                        'backup_name': backup_name,
                        'created_at': timestamp.isoformat(),
                        'version': '1.0.0',
                        'include_artwork': include_artwork
                    },
                    'streams': [],
                    'schedules': []
                }
                
                # Export stream configurations
                streams = self.config_repo.get_all()
                for stream in streams:
                    stream_data = {
                        'name': stream.name,
                        'stream_url': stream.stream_url,
                        'artist': stream.artist,
                        'album': stream.album,
                        'album_artist': stream.album_artist,
                        'artwork_path': stream.artwork_path,
                        'output_filename_pattern': stream.output_filename_pattern,
                        'scp_destination': stream.scp_destination,
                        'created_at': stream.created_at.isoformat() if stream.created_at else None,
                        'updated_at': stream.updated_at.isoformat() if stream.updated_at else None
                    }
                    backup_data['streams'].append(stream_data)
                
                # Export recording schedules
                schedules = self.schedule_repo.get_all()
                for schedule in schedules:
                    schedule_data = {
                        'stream_name': None,  # Will be resolved during restore
                        'cron_expression': schedule.cron_expression,
                        'duration_minutes': schedule.duration_minutes,
                        'is_active': schedule.is_active,
                        'max_retries': schedule.max_retries,
                        'created_at': schedule.created_at.isoformat() if schedule.created_at else None,
                        'updated_at': schedule.updated_at.isoformat() if schedule.updated_at else None
                    }
                    
                    # Find associated stream name
                    stream = self.config_repo.get_by_id(schedule.stream_config_id)
                    if stream:
                        schedule_data['stream_name'] = stream.name
                    
                    backup_data['schedules'].append(schedule_data)
                
                # Save configuration data to JSON
                config_file = os.path.join(temp_dir, 'configuration.json')
                with open(config_file, 'w') as f:
                    json.dump(backup_data, f, indent=2)
                
                # Create ZIP archive
                with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    # Add configuration file
                    zipf.write(config_file, 'configuration.json')
                    
                    # Add artwork files if requested
                    if include_artwork and os.path.exists(Config.ARTWORK_DIR):
                        for root, dirs, files in os.walk(Config.ARTWORK_DIR):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.join('artwork', os.path.relpath(file_path, Config.ARTWORK_DIR))
                                zipf.write(file_path, arcname)
                
                backup_info = {
                    'backup_name': backup_name,
                    'backup_path': backup_path,
                    'backup_filename': backup_filename,
                    'created_at': timestamp.isoformat(),
                    'file_size_bytes': os.path.getsize(backup_path),
                    'streams_count': len(backup_data['streams']),
                    'schedules_count': len(backup_data['schedules']),
                    'include_artwork': include_artwork,
                    'success': True
                }
                
                logger.info(f"Configuration backup created: {backup_filename}")
                return backup_info
                
        except Exception as e:
            logger.error(f"Error creating backup: {str(e)}")
            return {
                'backup_name': backup_name or 'unknown',
                'success': False,
                'error': str(e)
            }
    
    def restore_backup(self, backup_filename: str, overwrite_existing: bool = False) -> Dict[str, Any]:
        """
        Restore configuration from a backup file.
        
        Args:
            backup_filename: Name of the backup file to restore
            overwrite_existing: Whether to overwrite existing configurations
            
        Returns:
            Dictionary with restore information
        """
        try:
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            if not os.path.exists(backup_path):
                return {
                    'success': False,
                    'error': f"Backup file not found: {backup_filename}"
                }
            
            from ..utils.timezone_utils import get_local_now
            restore_info = {
                'backup_filename': backup_filename,
                'restored_at': get_local_now().isoformat(),
                'streams_restored': 0,
                'schedules_restored': 0,
                'streams_skipped': 0,
                'schedules_skipped': 0,
                'errors': [],
                'success': True
            }
            
            # Create temporary directory for extraction
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract backup archive
                with zipfile.ZipFile(backup_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                
                # Load configuration data
                config_file = os.path.join(temp_dir, 'configuration.json')
                if not os.path.exists(config_file):
                    return {
                        'success': False,
                        'error': "Invalid backup file: configuration.json not found"
                    }
                
                with open(config_file, 'r') as f:
                    backup_data = json.load(f)
                
                # Validate backup format
                if 'metadata' not in backup_data or 'streams' not in backup_data:
                    return {
                        'success': False,
                        'error': "Invalid backup format"
                    }
                
                # Restore artwork files first
                artwork_dir = os.path.join(temp_dir, 'artwork')
                if os.path.exists(artwork_dir):
                    os.makedirs(Config.ARTWORK_DIR, exist_ok=True)
                    for root, dirs, files in os.walk(artwork_dir):
                        for file in files:
                            src_path = os.path.join(root, file)
                            dst_path = os.path.join(Config.ARTWORK_DIR, file)
                            
                            if overwrite_existing or not os.path.exists(dst_path):
                                shutil.copy2(src_path, dst_path)
                
                # Restore stream configurations
                stream_name_to_id = {}
                for stream_data in backup_data['streams']:
                    try:
                        # Check if stream already exists
                        existing_stream = self.config_repo.get_by_name(stream_data['name'])
                        
                        if existing_stream and not overwrite_existing:
                            restore_info['streams_skipped'] += 1
                            stream_name_to_id[stream_data['name']] = existing_stream.id
                            continue
                        
                        from src.models.stream_configuration import StreamConfigurationCreate
                        
                        # Create or update stream configuration
                        create_data = StreamConfigurationCreate(
                            name=stream_data['name'],
                            stream_url=stream_data['stream_url'],
                            artist=stream_data['artist'],
                            album=stream_data['album'],
                            album_artist=stream_data['album_artist'],
                            artwork_path=stream_data.get('artwork_path'),
                            output_filename_pattern=stream_data.get('output_filename_pattern', '{artist} - {album} - {date} - {title}.mp3'),
                            scp_destination=stream_data['scp_destination']
                        )
                        
                        if existing_stream and overwrite_existing:
                            # Update existing stream
                            from src.models.stream_configuration import StreamConfigurationUpdate
                            update_data = StreamConfigurationUpdate(**create_data.dict())
                            updated_stream = self.config_repo.update(existing_stream.id, update_data)
                            stream_name_to_id[stream_data['name']] = updated_stream.id
                        else:
                            # Create new stream
                            new_stream = self.config_repo.create(create_data)
                            stream_name_to_id[stream_data['name']] = new_stream.id
                        
                        restore_info['streams_restored'] += 1
                        
                    except Exception as e:
                        error_msg = f"Error restoring stream '{stream_data['name']}': {str(e)}"
                        restore_info['errors'].append(error_msg)
                        logger.error(error_msg)
                
                # Restore recording schedules
                for schedule_data in backup_data.get('schedules', []):
                    try:
                        stream_name = schedule_data.get('stream_name')
                        if not stream_name or stream_name not in stream_name_to_id:
                            error_msg = f"Cannot restore schedule: associated stream '{stream_name}' not found"
                            restore_info['errors'].append(error_msg)
                            continue
                        
                        stream_config_id = stream_name_to_id[stream_name]
                        
                        # Check if similar schedule already exists
                        existing_schedules = self.schedule_repo.get_by_stream_config(stream_config_id)
                        schedule_exists = any(
                            s.cron_expression == schedule_data['cron_expression'] and
                            s.duration_minutes == schedule_data['duration_minutes']
                            for s in existing_schedules
                        )
                        
                        if schedule_exists and not overwrite_existing:
                            restore_info['schedules_skipped'] += 1
                            continue
                        
                        from src.models.recording_schedule import RecordingScheduleCreate
                        
                        create_data = RecordingScheduleCreate(
                            stream_config_id=stream_config_id,
                            cron_expression=schedule_data['cron_expression'],
                            duration_minutes=schedule_data['duration_minutes'],
                            is_active=schedule_data.get('is_active', False),
                            max_retries=schedule_data.get('max_retries', Config.DEFAULT_MAX_RETRIES)
                        )
                        
                        new_schedule = self.schedule_repo.create(create_data)
                        restore_info['schedules_restored'] += 1
                        
                    except Exception as e:
                        error_msg = f"Error restoring schedule for stream '{stream_name}': {str(e)}"
                        restore_info['errors'].append(error_msg)
                        logger.error(error_msg)
                
                logger.info(f"Configuration restored from backup: {backup_filename}")
                return restore_info
                
        except Exception as e:
            logger.error(f"Error restoring backup: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """
        List all available backup files.
        
        Returns:
            List of backup information dictionaries
        """
        try:
            backups = []
            
            if not os.path.exists(self.backup_dir):
                return backups
            
            for filename in os.listdir(self.backup_dir):
                if filename.endswith('.zip'):
                    backup_path = os.path.join(self.backup_dir, filename)
                    
                    try:
                        # Get basic file information
                        stat = os.stat(backup_path)
                        backup_info = {
                            'filename': filename,
                            'file_size_bytes': stat.st_size,
                            'created_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            'valid': False,
                            'metadata': {}
                        }
                        
                        # Try to read backup metadata
                        try:
                            with zipfile.ZipFile(backup_path, 'r') as zipf:
                                if 'configuration.json' in zipf.namelist():
                                    with zipf.open('configuration.json') as f:
                                        config_data = json.load(f)
                                        if 'metadata' in config_data:
                                            backup_info['metadata'] = config_data['metadata']
                                            backup_info['streams_count'] = len(config_data.get('streams', []))
                                            backup_info['schedules_count'] = len(config_data.get('schedules', []))
                                            backup_info['valid'] = True
                        except Exception:
                            # If we can't read the backup, mark it as invalid but still list it
                            pass
                        
                        backups.append(backup_info)
                        
                    except Exception as e:
                        logger.warning(f"Error reading backup file {filename}: {str(e)}")
            
            # Sort by creation date, newest first
            backups.sort(key=lambda x: x['created_at'], reverse=True)
            return backups
            
        except Exception as e:
            logger.error(f"Error listing backups: {str(e)}")
            return []
    
    def delete_backup(self, backup_filename: str) -> Dict[str, Any]:
        """
        Delete a backup file.
        
        Args:
            backup_filename: Name of the backup file to delete
            
        Returns:
            Dictionary with deletion result
        """
        try:
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            if not os.path.exists(backup_path):
                return {
                    'success': False,
                    'error': f"Backup file not found: {backup_filename}"
                }
            
            os.remove(backup_path)
            
            logger.info(f"Backup deleted: {backup_filename}")
            from ..utils.timezone_utils import get_local_now
            return {
                'success': True,
                'backup_filename': backup_filename,
                'deleted_at': get_local_now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error deleting backup {backup_filename}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def validate_backup(self, backup_filename: str) -> Dict[str, Any]:
        """
        Validate a backup file without restoring it.
        
        Args:
            backup_filename: Name of the backup file to validate
            
        Returns:
            Dictionary with validation results
        """
        try:
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            if not os.path.exists(backup_path):
                return {
                    'valid': False,
                    'error': f"Backup file not found: {backup_filename}"
                }
            
            validation_result = {
                'valid': False,
                'backup_filename': backup_filename,
                'errors': [],
                'warnings': [],
                'metadata': {},
                'streams_count': 0,
                'schedules_count': 0
            }
            
            # Check if it's a valid ZIP file
            try:
                with zipfile.ZipFile(backup_path, 'r') as zipf:
                    # Check for required files
                    if 'configuration.json' not in zipf.namelist():
                        validation_result['errors'].append("Missing configuration.json file")
                        return validation_result
                    
                    # Load and validate configuration data
                    with zipf.open('configuration.json') as f:
                        config_data = json.load(f)
                    
                    # Use migration tool for comprehensive validation
                    migration_validation = self.migration_tool.validate_configuration(config_data)
                    validation_result['errors'].extend(migration_validation['errors'])
                    validation_result['warnings'].extend(migration_validation['warnings'])
                    
                    # Validate structure
                    if 'metadata' not in config_data:
                        validation_result['errors'].append("Missing metadata section")
                    else:
                        validation_result['metadata'] = config_data['metadata']
                    
                    if 'streams' not in config_data:
                        validation_result['errors'].append("Missing streams section")
                    else:
                        validation_result['streams_count'] = len(config_data['streams'])
                        
                        # Validate stream configurations
                        for i, stream in enumerate(config_data['streams']):
                            required_fields = ['name', 'stream_url', 'artist', 'album', 'album_artist', 'scp_destination']
                            for field in required_fields:
                                if field not in stream:
                                    validation_result['errors'].append(f"Stream {i+1}: Missing required field '{field}'")
                    
                    if 'schedules' in config_data:
                        validation_result['schedules_count'] = len(config_data['schedules'])
                        
                        # Validate schedules
                        for i, schedule in enumerate(config_data['schedules']):
                            required_fields = ['stream_name', 'cron_expression', 'duration_minutes']
                            for field in required_fields:
                                if field not in schedule:
                                    validation_result['errors'].append(f"Schedule {i+1}: Missing required field '{field}'")
                            
                            # Validate cron expression
                            if 'cron_expression' in schedule:
                                from croniter import croniter
                                if not croniter.is_valid(schedule['cron_expression']):
                                    validation_result['errors'].append(f"Schedule {i+1}: Invalid cron expression")
                    
                    # Check artwork files
                    artwork_files = [f for f in zipf.namelist() if f.startswith('artwork/')]
                    if artwork_files:
                        validation_result['artwork_files_count'] = len(artwork_files)
                    
                    validation_result['valid'] = len(validation_result['errors']) == 0
                    
            except zipfile.BadZipFile:
                validation_result['errors'].append("Invalid ZIP file format")
            except json.JSONDecodeError:
                validation_result['errors'].append("Invalid JSON in configuration file")
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error validating backup {backup_filename}: {str(e)}")
            return {
                'valid': False,
                'error': str(e)
            }
    
    def create_automatic_backup(self) -> Optional[Dict[str, Any]]:
        """
        Create an automatic backup with timestamp-based naming.
        
        Returns:
            Backup information dictionary or None if failed
        """
        try:
            # Clean up old automatic backups first
            self.cleanup_old_backups()
            
            # Create new automatic backup
            from ..utils.timezone_utils import get_local_timestamp_string
            backup_name = f"auto_backup_{get_local_timestamp_string()}"
            return self.create_backup(backup_name, include_artwork=True)
            
        except Exception as e:
            logger.error(f"Error creating automatic backup: {str(e)}")
            return None
    
    def cleanup_old_backups(self, keep_count: int = 10) -> int:
        """
        Clean up old automatic backups, keeping only the most recent ones.
        
        Args:
            keep_count: Number of automatic backups to keep
            
        Returns:
            Number of backups deleted
        """
        try:
            backups = self.list_backups()
            
            # Filter automatic backups
            auto_backups = [b for b in backups if b['filename'].startswith('auto_backup_')]
            
            if len(auto_backups) <= keep_count:
                return 0
            
            # Sort by creation date and delete oldest
            auto_backups.sort(key=lambda x: x['created_at'])
            backups_to_delete = auto_backups[:-keep_count]
            
            deleted_count = 0
            for backup in backups_to_delete:
                result = self.delete_backup(backup['filename'])
                if result['success']:
                    deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old automatic backups")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old backups: {str(e)}")
            return 0