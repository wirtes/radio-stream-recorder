"""
Configuration migration and validation tools for Audio Stream Recorder.
Handles version upgrades and configuration format changes.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from src.config import Config

logger = logging.getLogger(__name__)


class ConfigMigration:
    """Handles configuration migration between versions."""
    
    CURRENT_VERSION = "1.0.0"
    
    # Migration functions for each version upgrade
    MIGRATIONS = {
        "0.9.0": "migrate_from_0_9_0",
        "1.0.0": "migrate_from_1_0_0"
    }
    
    def __init__(self):
        self.migration_log = []
    
    def migrate_configuration(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate configuration data to current version.
        
        Args:
            config_data: Configuration data to migrate
            
        Returns:
            Migrated configuration data
        """
        try:
            # Get current version from metadata
            current_version = config_data.get('metadata', {}).get('version', '0.9.0')
            
            if current_version == self.CURRENT_VERSION:
                logger.info("Configuration is already at current version")
                return config_data
            
            logger.info(f"Migrating configuration from version {current_version} to {self.CURRENT_VERSION}")
            
            # Apply migrations in order
            migrated_data = config_data.copy()
            
            # Determine migration path
            migration_path = self._get_migration_path(current_version)
            
            for version in migration_path:
                if version in self.MIGRATIONS:
                    migration_func = getattr(self, self.MIGRATIONS[version])
                    migrated_data = migration_func(migrated_data)
                    self.migration_log.append(f"Applied migration for version {version}")
            
            # Update version in metadata
            if 'metadata' not in migrated_data:
                migrated_data['metadata'] = {}
            
            migrated_data['metadata']['version'] = self.CURRENT_VERSION
            migrated_data['metadata']['migrated_at'] = datetime.utcnow().isoformat()
            migrated_data['metadata']['migration_log'] = self.migration_log
            
            logger.info(f"Configuration migration completed: {len(self.migration_log)} migrations applied")
            return migrated_data
            
        except Exception as e:
            logger.error(f"Error during configuration migration: {e}")
            raise ValueError(f"Configuration migration failed: {e}")
    
    def _get_migration_path(self, from_version: str) -> List[str]:
        """
        Get the list of versions to migrate through.
        
        Args:
            from_version: Starting version
            
        Returns:
            List of versions to migrate through
        """
        # Simple version ordering for now
        version_order = ["0.9.0", "1.0.0"]
        
        try:
            start_index = version_order.index(from_version)
            return version_order[start_index + 1:]
        except ValueError:
            # Unknown version, migrate through all
            return version_order
    
    def migrate_from_0_9_0(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate from version 0.9.0 to 1.0.0.
        
        Args:
            config_data: Configuration data to migrate
            
        Returns:
            Migrated configuration data
        """
        migrated = config_data.copy()
        
        # Add new fields that were introduced in 1.0.0
        for stream in migrated.get('streams', []):
            # Add output_filename_pattern if missing
            if 'output_filename_pattern' not in stream:
                stream['output_filename_pattern'] = '{artist} - {album} - {date} - {title}.mp3'
            
            # Ensure artwork_path is present (can be None)
            if 'artwork_path' not in stream:
                stream['artwork_path'] = None
        
        for schedule in migrated.get('schedules', []):
            # Add max_retries if missing
            if 'max_retries' not in schedule:
                schedule['max_retries'] = Config.DEFAULT_MAX_RETRIES
        
        return migrated
    
    def migrate_from_1_0_0(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Placeholder for future migrations from 1.0.0.
        
        Args:
            config_data: Configuration data to migrate
            
        Returns:
            Migrated configuration data
        """
        # No changes needed for current version
        return config_data
    
    def validate_configuration(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate configuration data structure and content.
        
        Args:
            config_data: Configuration data to validate
            
        Returns:
            Validation results dictionary
        """
        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'info': []
        }
        
        try:
            # Check required top-level sections
            required_sections = ['metadata', 'streams']
            for section in required_sections:
                if section not in config_data:
                    validation_result['errors'].append(f"Missing required section: {section}")
                    validation_result['valid'] = False
            
            # Validate metadata
            if 'metadata' in config_data:
                metadata = config_data['metadata']
                
                if 'version' not in metadata:
                    validation_result['warnings'].append("Missing version in metadata")
                
                if 'created_at' not in metadata:
                    validation_result['warnings'].append("Missing created_at in metadata")
            
            # Validate streams
            if 'streams' in config_data:
                streams = config_data['streams']
                
                if not isinstance(streams, list):
                    validation_result['errors'].append("Streams section must be a list")
                    validation_result['valid'] = False
                else:
                    stream_names = set()
                    
                    for i, stream in enumerate(streams):
                        stream_errors = self._validate_stream(stream, i + 1)
                        validation_result['errors'].extend(stream_errors)
                        
                        if stream_errors:
                            validation_result['valid'] = False
                        
                        # Check for duplicate stream names
                        stream_name = stream.get('name')
                        if stream_name:
                            if stream_name in stream_names:
                                validation_result['errors'].append(f"Duplicate stream name: {stream_name}")
                                validation_result['valid'] = False
                            else:
                                stream_names.add(stream_name)
            
            # Validate schedules
            if 'schedules' in config_data:
                schedules = config_data['schedules']
                
                if not isinstance(schedules, list):
                    validation_result['errors'].append("Schedules section must be a list")
                    validation_result['valid'] = False
                else:
                    for i, schedule in enumerate(schedules):
                        schedule_errors = self._validate_schedule(schedule, i + 1)
                        validation_result['errors'].extend(schedule_errors)
                        
                        if schedule_errors:
                            validation_result['valid'] = False
            
            # Add summary info
            if 'streams' in config_data:
                validation_result['info'].append(f"Found {len(config_data['streams'])} stream configurations")
            
            if 'schedules' in config_data:
                validation_result['info'].append(f"Found {len(config_data['schedules'])} recording schedules")
            
        except Exception as e:
            validation_result['valid'] = False
            validation_result['errors'].append(f"Validation error: {str(e)}")
        
        return validation_result
    
    def _validate_stream(self, stream: Dict[str, Any], stream_number: int) -> List[str]:
        """
        Validate a single stream configuration.
        
        Args:
            stream: Stream configuration to validate
            stream_number: Stream number for error messages
            
        Returns:
            List of validation errors
        """
        errors = []
        
        # Required fields
        required_fields = ['name', 'stream_url', 'artist', 'album', 'album_artist', 'scp_destination']
        
        for field in required_fields:
            if field not in stream:
                errors.append(f"Stream {stream_number}: Missing required field '{field}'")
            elif not stream[field] or not isinstance(stream[field], str):
                errors.append(f"Stream {stream_number}: Field '{field}' must be a non-empty string")
        
        # Validate stream URL format
        if 'stream_url' in stream:
            stream_url = stream['stream_url']
            if not (stream_url.startswith('http://') or stream_url.startswith('https://') or 
                   stream_url.startswith('rtmp://') or stream_url.startswith('rtmps://')):
                errors.append(f"Stream {stream_number}: Invalid stream URL format")
        
        # Validate optional fields
        if 'output_filename_pattern' in stream:
            pattern = stream['output_filename_pattern']
            if not isinstance(pattern, str) or not pattern.strip():
                errors.append(f"Stream {stream_number}: output_filename_pattern must be a non-empty string")
        
        # Validate artwork path if present
        if 'artwork_path' in stream and stream['artwork_path'] is not None:
            if not isinstance(stream['artwork_path'], str):
                errors.append(f"Stream {stream_number}: artwork_path must be a string or null")
        
        return errors
    
    def _validate_schedule(self, schedule: Dict[str, Any], schedule_number: int) -> List[str]:
        """
        Validate a single schedule configuration.
        
        Args:
            schedule: Schedule configuration to validate
            schedule_number: Schedule number for error messages
            
        Returns:
            List of validation errors
        """
        errors = []
        
        # Required fields
        required_fields = ['stream_name', 'cron_expression', 'duration_minutes']
        
        for field in required_fields:
            if field not in schedule:
                errors.append(f"Schedule {schedule_number}: Missing required field '{field}'")
        
        # Validate cron expression
        if 'cron_expression' in schedule:
            try:
                from croniter import croniter
                if not croniter.is_valid(schedule['cron_expression']):
                    errors.append(f"Schedule {schedule_number}: Invalid cron expression")
            except ImportError:
                errors.append(f"Schedule {schedule_number}: Cannot validate cron expression (croniter not available)")
            except Exception:
                errors.append(f"Schedule {schedule_number}: Error validating cron expression")
        
        # Validate duration
        if 'duration_minutes' in schedule:
            duration = schedule['duration_minutes']
            if not isinstance(duration, int) or duration <= 0:
                errors.append(f"Schedule {schedule_number}: duration_minutes must be a positive integer")
        
        # Validate optional fields
        if 'max_retries' in schedule:
            max_retries = schedule['max_retries']
            if not isinstance(max_retries, int) or max_retries < 0:
                errors.append(f"Schedule {schedule_number}: max_retries must be a non-negative integer")
        
        if 'is_active' in schedule:
            if not isinstance(schedule['is_active'], bool):
                errors.append(f"Schedule {schedule_number}: is_active must be a boolean")
        
        return errors
    
    def create_configuration_template(self) -> Dict[str, Any]:
        """
        Create a template configuration structure.
        
        Returns:
            Template configuration dictionary
        """
        return {
            'metadata': {
                'version': self.CURRENT_VERSION,
                'created_at': datetime.utcnow().isoformat(),
                'backup_name': 'template',
                'include_artwork': True
            },
            'streams': [
                {
                    'name': 'Example Stream',
                    'stream_url': 'https://example.com/stream.m3u8',
                    'artist': 'Example Artist',
                    'album': 'Example Album',
                    'album_artist': 'Example Album Artist',
                    'artwork_path': None,
                    'output_filename_pattern': '{artist} - {album} - {date} - {title}.mp3',
                    'scp_destination': 'user@server:/path/to/destination/',
                    'created_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat()
                }
            ],
            'schedules': [
                {
                    'stream_name': 'Example Stream',
                    'cron_expression': '0 9 * * 1-5',
                    'duration_minutes': 60,
                    'is_active': False,
                    'max_retries': 3,
                    'created_at': datetime.utcnow().isoformat(),
                    'updated_at': datetime.utcnow().isoformat()
                }
            ]
        }