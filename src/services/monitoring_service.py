"""
System monitoring and health check service for the audio stream recorder.

This module provides resource monitoring (disk space, memory usage),
system health endpoints, and performance metrics collection.
"""

import os
import psutil
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
from enum import Enum

from .logging_service import get_logging_service, OperationType, LogLevel


class HealthStatus(Enum):
    """System health status enumeration."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class SystemMetrics:
    """System resource metrics data class."""
    timestamp: str
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    disk_free_gb: float
    active_recordings: int
    uptime_seconds: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return asdict(self)


@dataclass
class HealthCheck:
    """Health check result data class."""
    component: str
    status: HealthStatus
    message: str
    timestamp: str
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert health check to dictionary."""
        result = asdict(self)
        result['status'] = self.status.value
        return result


class MonitoringService:
    """
    System monitoring and health check service.
    
    Features:
    - Resource monitoring (CPU, memory, disk space)
    - System health checks with configurable thresholds
    - Performance metrics collection and reporting
    - Health endpoints for container orchestration
    - Automatic alerting when resources are low
    """
    
    def __init__(self,
                 monitoring_interval: int = 60,  # seconds
                 disk_warning_threshold: float = 80.0,  # percent
                 disk_critical_threshold: float = 90.0,  # percent
                 memory_warning_threshold: float = 80.0,  # percent
                 memory_critical_threshold: float = 90.0,  # percent
                 cpu_warning_threshold: float = 80.0,  # percent
                 cpu_critical_threshold: float = 95.0,  # percent
                 metrics_retention_hours: int = 24):
        """
        Initialize the monitoring service.
        
        Args:
            monitoring_interval: Seconds between metric collections
            disk_warning_threshold: Disk usage warning threshold (%)
            disk_critical_threshold: Disk usage critical threshold (%)
            memory_warning_threshold: Memory usage warning threshold (%)
            memory_critical_threshold: Memory usage critical threshold (%)
            cpu_warning_threshold: CPU usage warning threshold (%)
            cpu_critical_threshold: CPU usage critical threshold (%)
            metrics_retention_hours: Hours to retain metrics history
        """
        self.monitoring_interval = monitoring_interval
        self.disk_warning_threshold = disk_warning_threshold
        self.disk_critical_threshold = disk_critical_threshold
        self.memory_warning_threshold = memory_warning_threshold
        self.memory_critical_threshold = memory_critical_threshold
        self.cpu_warning_threshold = cpu_warning_threshold
        self.cpu_critical_threshold = cpu_critical_threshold
        self.metrics_retention_hours = metrics_retention_hours
        
        self.logger = get_logging_service()
        self.start_time = time.time()
        self.is_monitoring = False
        self.monitoring_thread = None
        
        # Metrics storage (in-memory for now, could be extended to persistent storage)
        self.metrics_history: List[SystemMetrics] = []
        self.health_checks: Dict[str, HealthCheck] = {}
        
        # Lock for thread-safe access to metrics
        self._metrics_lock = threading.Lock()
        
        # Active recording counter (to be updated by recording service)
        self._active_recordings = 0
        
    def start_monitoring(self):
        """Start the monitoring service in a background thread."""
        if self.is_monitoring:
            return
            
        self.is_monitoring = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        self.logger.log_operation(
            OperationType.SYSTEM,
            "System monitoring service started",
            LogLevel.INFO,
            context={'monitoring_interval': self.monitoring_interval}
        )
        
    def stop_monitoring(self):
        """Stop the monitoring service."""
        self.is_monitoring = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
            
        self.logger.log_operation(
            OperationType.SYSTEM,
            "System monitoring service stopped",
            LogLevel.INFO
        )
    
    def is_running(self) -> bool:
        """
        Check if the monitoring service is running.
        
        Returns:
            True if monitoring is active, False otherwise
        """
        return self.is_monitoring
        
    def _monitoring_loop(self):
        """Main monitoring loop that runs in background thread."""
        while self.is_monitoring:
            try:
                # Collect system metrics
                metrics = self._collect_system_metrics()
                
                # Store metrics
                with self._metrics_lock:
                    self.metrics_history.append(metrics)
                    
                # Perform health checks
                self._perform_health_checks(metrics)
                
                # Clean up old metrics
                self._cleanup_old_metrics()
                
                # Log system status periodically (every 10 minutes)
                if len(self.metrics_history) % 10 == 0:
                    self.logger.log_operation(
                        OperationType.SYSTEM,
                        f"System status: CPU {metrics.cpu_percent:.1f}%, "
                        f"Memory {metrics.memory_percent:.1f}%, "
                        f"Disk {metrics.disk_percent:.1f}%, "
                        f"Active recordings: {metrics.active_recordings}",
                        LogLevel.INFO,
                        context=metrics.to_dict()
                    )
                    
            except Exception as e:
                self.logger.log_operation(
                    OperationType.SYSTEM,
                    f"Error in monitoring loop: {str(e)}",
                    LogLevel.ERROR,
                    exc_info=True
                )
                
            # Wait for next monitoring cycle
            time.sleep(self.monitoring_interval)
            
    def _collect_system_metrics(self) -> SystemMetrics:
        """Collect current system resource metrics."""
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_mb = memory.used / (1024 * 1024)
        memory_total_mb = memory.total / (1024 * 1024)
        
        # Disk usage for recordings directory
        recordings_path = Path("/app/recordings")
        if recordings_path.exists():
            disk_usage = psutil.disk_usage(str(recordings_path))
        else:
            # Fallback to root filesystem
            disk_usage = psutil.disk_usage("/")
            
        disk_percent = (disk_usage.used / disk_usage.total) * 100
        disk_used_gb = disk_usage.used / (1024 * 1024 * 1024)
        disk_total_gb = disk_usage.total / (1024 * 1024 * 1024)
        disk_free_gb = disk_usage.free / (1024 * 1024 * 1024)
        
        # System uptime
        uptime_seconds = time.time() - self.start_time
        
        return SystemMetrics(
            timestamp=datetime.now().isoformat(),
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_mb=memory_used_mb,
            memory_total_mb=memory_total_mb,
            disk_percent=disk_percent,
            disk_used_gb=disk_used_gb,
            disk_total_gb=disk_total_gb,
            disk_free_gb=disk_free_gb,
            active_recordings=self._active_recordings,
            uptime_seconds=uptime_seconds
        )
        
    def _perform_health_checks(self, metrics: SystemMetrics):
        """Perform health checks based on current metrics."""
        timestamp = datetime.now().isoformat()
        
        # Disk space health check
        if metrics.disk_percent >= self.disk_critical_threshold:
            status = HealthStatus.CRITICAL
            message = f"Disk usage critical: {metrics.disk_percent:.1f}%"
            self.logger.log_operation(
                OperationType.SYSTEM,
                message,
                LogLevel.CRITICAL,
                context={'disk_percent': metrics.disk_percent, 'threshold': self.disk_critical_threshold}
            )
        elif metrics.disk_percent >= self.disk_warning_threshold:
            status = HealthStatus.WARNING
            message = f"Disk usage high: {metrics.disk_percent:.1f}%"
            self.logger.log_operation(
                OperationType.SYSTEM,
                message,
                LogLevel.WARNING,
                context={'disk_percent': metrics.disk_percent, 'threshold': self.disk_warning_threshold}
            )
        else:
            status = HealthStatus.HEALTHY
            message = f"Disk usage normal: {metrics.disk_percent:.1f}%"
            
        self.health_checks['disk'] = HealthCheck(
            component='disk',
            status=status,
            message=message,
            timestamp=timestamp,
            details={
                'usage_percent': metrics.disk_percent,
                'free_gb': metrics.disk_free_gb,
                'total_gb': metrics.disk_total_gb
            }
        )
        
        # Memory health check
        if metrics.memory_percent >= self.memory_critical_threshold:
            status = HealthStatus.CRITICAL
            message = f"Memory usage critical: {metrics.memory_percent:.1f}%"
            self.logger.log_operation(
                OperationType.SYSTEM,
                message,
                LogLevel.CRITICAL,
                context={'memory_percent': metrics.memory_percent, 'threshold': self.memory_critical_threshold}
            )
        elif metrics.memory_percent >= self.memory_warning_threshold:
            status = HealthStatus.WARNING
            message = f"Memory usage high: {metrics.memory_percent:.1f}%"
            self.logger.log_operation(
                OperationType.SYSTEM,
                message,
                LogLevel.WARNING,
                context={'memory_percent': metrics.memory_percent, 'threshold': self.memory_warning_threshold}
            )
        else:
            status = HealthStatus.HEALTHY
            message = f"Memory usage normal: {metrics.memory_percent:.1f}%"
            
        self.health_checks['memory'] = HealthCheck(
            component='memory',
            status=status,
            message=message,
            timestamp=timestamp,
            details={
                'usage_percent': metrics.memory_percent,
                'used_mb': metrics.memory_used_mb,
                'total_mb': metrics.memory_total_mb
            }
        )
        
        # CPU health check
        if metrics.cpu_percent >= self.cpu_critical_threshold:
            status = HealthStatus.CRITICAL
            message = f"CPU usage critical: {metrics.cpu_percent:.1f}%"
            self.logger.log_operation(
                OperationType.SYSTEM,
                message,
                LogLevel.CRITICAL,
                context={'cpu_percent': metrics.cpu_percent, 'threshold': self.cpu_critical_threshold}
            )
        elif metrics.cpu_percent >= self.cpu_warning_threshold:
            status = HealthStatus.WARNING
            message = f"CPU usage high: {metrics.cpu_percent:.1f}%"
            self.logger.log_operation(
                OperationType.SYSTEM,
                message,
                LogLevel.WARNING,
                context={'cpu_percent': metrics.cpu_percent, 'threshold': self.cpu_warning_threshold}
            )
        else:
            status = HealthStatus.HEALTHY
            message = f"CPU usage normal: {metrics.cpu_percent:.1f}%"
            
        self.health_checks['cpu'] = HealthCheck(
            component='cpu',
            status=status,
            message=message,
            timestamp=timestamp,
            details={
                'usage_percent': metrics.cpu_percent
            }
        )
        
        # Overall system health check
        component_statuses = [check.status for check in self.health_checks.values()]
        if HealthStatus.CRITICAL in component_statuses:
            overall_status = HealthStatus.CRITICAL
            message = "System health critical - one or more components in critical state"
        elif HealthStatus.WARNING in component_statuses:
            overall_status = HealthStatus.WARNING
            message = "System health warning - one or more components need attention"
        else:
            overall_status = HealthStatus.HEALTHY
            message = "System health good - all components operating normally"
            
        self.health_checks['system'] = HealthCheck(
            component='system',
            status=overall_status,
            message=message,
            timestamp=timestamp,
            details={
                'active_recordings': metrics.active_recordings,
                'uptime_seconds': metrics.uptime_seconds
            }
        )
        
    def _cleanup_old_metrics(self):
        """Remove metrics older than retention period."""
        if not self.metrics_history:
            return
            
        cutoff_time = datetime.utcnow() - timedelta(hours=self.metrics_retention_hours)
        cutoff_timestamp = cutoff_time.isoformat() + 'Z'
        
        with self._metrics_lock:
            # Keep only metrics newer than cutoff time
            self.metrics_history = [
                m for m in self.metrics_history 
                if m.timestamp > cutoff_timestamp
            ]
            
    def get_current_metrics(self) -> SystemMetrics:
        """Get the most recent system metrics."""
        if not self.metrics_history:
            return self._collect_system_metrics()
            
        with self._metrics_lock:
            return self.metrics_history[-1]
            
    def get_metrics_history(self, hours: int = 1) -> List[SystemMetrics]:
        """
        Get metrics history for the specified number of hours.
        
        Args:
            hours: Number of hours of history to return
            
        Returns:
            List of SystemMetrics ordered by timestamp (oldest first)
        """
        if not self.metrics_history:
            return []
            
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        cutoff_timestamp = cutoff_time.isoformat() + 'Z'
        
        with self._metrics_lock:
            return [
                m for m in self.metrics_history 
                if m.timestamp > cutoff_timestamp
            ]
            
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get current system health status.
        
        Returns:
            Dictionary containing overall health and component details
        """
        if not self.health_checks:
            # Perform immediate health check if none exist
            metrics = self._collect_system_metrics()
            self._perform_health_checks(metrics)
            
        overall_check = self.health_checks.get('system')
        if not overall_check:
            return {
                'status': HealthStatus.UNKNOWN.value,
                'message': 'Health status not available',
                'timestamp': datetime.now().isoformat(),
                'components': {}
            }
            
        return {
            'status': overall_check.status.value,
            'message': overall_check.message,
            'timestamp': overall_check.timestamp,
            'components': {
                name: check.to_dict() 
                for name, check in self.health_checks.items()
                if name != 'system'
            }
        }
        
    def is_healthy(self) -> bool:
        """
        Check if the system is healthy (no critical issues).
        
        Returns:
            True if system is healthy or has only warnings, False if critical issues exist
        """
        health_status = self.get_health_status()
        return health_status['status'] in [HealthStatus.HEALTHY.value, HealthStatus.WARNING.value]
        
    def set_active_recordings(self, count: int):
        """Update the count of active recordings."""
        self._active_recordings = max(0, count)
        
    def increment_active_recordings(self):
        """Increment the active recordings counter."""
        self._active_recordings += 1
        
    def decrement_active_recordings(self):
        """Decrement the active recordings counter."""
        self._active_recordings = max(0, self._active_recordings - 1)
        
    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get a performance summary with key metrics and trends.
        
        Returns:
            Dictionary containing performance summary
        """
        current_metrics = self.get_current_metrics()
        history = self.get_metrics_history(hours=1)
        
        if len(history) < 2:
            return {
                'current': current_metrics.to_dict(),
                'trends': {},
                'averages': {}
            }
            
        # Calculate averages over the last hour
        avg_cpu = sum(m.cpu_percent for m in history) / len(history)
        avg_memory = sum(m.memory_percent for m in history) / len(history)
        avg_disk = sum(m.disk_percent for m in history) / len(history)
        
        # Calculate trends (comparing current to average)
        cpu_trend = current_metrics.cpu_percent - avg_cpu
        memory_trend = current_metrics.memory_percent - avg_memory
        disk_trend = current_metrics.disk_percent - avg_disk
        
        return {
            'current': current_metrics.to_dict(),
            'averages': {
                'cpu_percent': round(avg_cpu, 2),
                'memory_percent': round(avg_memory, 2),
                'disk_percent': round(avg_disk, 2)
            },
            'trends': {
                'cpu_trend': round(cpu_trend, 2),
                'memory_trend': round(memory_trend, 2),
                'disk_trend': round(disk_trend, 2)
            },
            'thresholds': {
                'disk_warning': self.disk_warning_threshold,
                'disk_critical': self.disk_critical_threshold,
                'memory_warning': self.memory_warning_threshold,
                'memory_critical': self.memory_critical_threshold,
                'cpu_warning': self.cpu_warning_threshold,
                'cpu_critical': self.cpu_critical_threshold
            }
        }


# Global monitoring service instance
_monitoring_service: Optional[MonitoringService] = None


def get_monitoring_service() -> MonitoringService:
    """Get the global monitoring service instance."""
    global _monitoring_service
    if _monitoring_service is None:
        _monitoring_service = MonitoringService()
    return _monitoring_service


def init_monitoring_service(**kwargs) -> MonitoringService:
    """Initialize the global monitoring service with custom parameters."""
    global _monitoring_service
    _monitoring_service = MonitoringService(**kwargs)
    return _monitoring_service