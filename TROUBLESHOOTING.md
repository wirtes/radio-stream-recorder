# Audio Stream Recorder - Troubleshooting Guide

This guide covers common issues and their solutions for the Audio Stream Recorder application.

## Table of Contents

1. [Container Issues](#container-issues)
2. [Recording Problems](#recording-problems)
3. [File Transfer Issues](#file-transfer-issues)
4. [Web Interface Problems](#web-interface-problems)
5. [Performance Issues](#performance-issues)
6. [Configuration Problems](#configuration-problems)
7. [Log Analysis](#log-analysis)
8. [Network Issues](#network-issues)
9. [Storage Issues](#storage-issues)
10. [Advanced Debugging](#advanced-debugging)

## Container Issues

### Container Won't Start

**Symptoms:**
- Container exits immediately after starting
- `docker compose up` shows error messages
- Container status shows "Exited (1)"

**Common Causes & Solutions:**

1. **Port Already in Use**
   ```bash
   # Check if port 8666 is already in use
   netstat -tulpn | grep 8666
   
   # Solution: Change WEB_PORT in .env or stop conflicting service
   ```

2. **Volume Permission Issues**
   ```bash
   # Fix directory permissions
   sudo chown -R $USER:$USER data recordings logs artwork config
   chmod -R 755 data recordings logs artwork config
   ```

3. **Missing Directories**
   ```bash
   # Create required directories
   mkdir -p data recordings logs artwork config
   ```

4. **Docker Permission Issues**
   ```bash
   # Add user to docker group
   sudo usermod -aG docker $USER
   newgrp docker
   
   # Test Docker access
   docker ps
   ```

5. **Invalid Environment Variables**
   ```bash
   # Check .env file syntax
   cat .env | grep -v '^#' | grep '='
   
   # Ensure no spaces around = signs
   # Correct: WEB_PORT=8666
   # Incorrect: WEB_PORT = 8666
   ```

**Debugging Steps:**
```bash
# View container logs
docker compose logs audio-recorder

# Check container status
docker compose ps

# Inspect container configuration
docker inspect audio-stream-recorder
```

### Container Starts But Exits Quickly

**Check the logs for specific error messages:**
```bash
docker compose logs --tail=50 audio-recorder
```

**Common Issues:**
- Database initialization failure
- Missing Python dependencies
- Configuration validation errors
- FFmpeg not found

## Recording Problems

### Recordings Fail to Start

**Symptoms:**
- Schedules are active but recordings don't begin
- "Recording failed" messages in logs
- Sessions show "FAILED" status

**Troubleshooting Steps:**

1. **Test Stream URL Manually**
   ```bash
   # Test with curl
   curl -I "https://your-stream-url.com/stream.m3u8"
   
   # Test with FFmpeg
   docker exec -it audio-stream-recorder ffmpeg -i "https://your-stream-url.com/stream.m3u8" -t 10 test.mp3
   ```

2. **Check Stream Configuration**
   - Verify stream URL is accessible
   - Ensure URL format is correct (http://, https://, rtmp://)
   - Test stream in media player (VLC, etc.)

3. **Verify Scheduler Status**
   ```bash
   # Check if scheduler is running
   docker exec -it audio-stream-recorder ps aux | grep python
   ```

4. **Check Concurrent Recording Limits**
   - Verify `MAX_CONCURRENT_RECORDINGS` setting
   - Check if other recordings are already active

### Recordings Start But Fail During Processing

**Common Causes:**

1. **Insufficient Disk Space**
   ```bash
   # Check disk usage
   df -h
   docker exec -it audio-stream-recorder df -h /app/recordings
   ```

2. **Stream Connection Lost**
   - Check network stability
   - Verify stream server reliability
   - Review retry settings

3. **FFmpeg Processing Errors**
   ```bash
   # Test FFmpeg functionality
   docker exec -it audio-stream-recorder ffmpeg -version
   
   # Test audio processing
   docker exec -it audio-stream-recorder ffmpeg -f lavfi -i "sine=frequency=1000:duration=5" test.mp3
   ```

### Audio Quality Issues

**Solutions:**
1. Check stream source quality
2. Verify FFmpeg encoding settings
3. Monitor network bandwidth during recording
4. Test with different stream URLs

## File Transfer Issues

### SCP Transfers Fail

**Symptoms:**
- Recordings complete but files don't transfer
- "SCP transfer failed" in logs
- Files remain in recordings directory

**Troubleshooting Steps:**

1. **Test SSH Connection**
   ```bash
   # Test SSH key
   docker exec -it audio-stream-recorder ssh -i /app/config/ssh_key user@hostname
   
   # Test SCP manually
   docker exec -it audio-stream-recorder scp -i /app/config/ssh_key test.txt user@hostname:/path/
   ```

2. **Check SSH Key Permissions**
   ```bash
   # SSH key should be readable only by owner
   ls -la config/ssh_key
   chmod 600 config/ssh_key
   ```

3. **Verify Destination Path**
   - Ensure destination directory exists on remote server
   - Check write permissions on remote directory
   - Verify SCP destination format: `user@hostname:/path/to/destination/`

4. **Check Network Connectivity**
   ```bash
   # Test network connectivity
   docker exec -it audio-stream-recorder ping hostname
   
   # Test SSH port
   docker exec -it audio-stream-recorder telnet hostname 22
   ```

### SSH Key Issues

**Common Problems:**
1. **Wrong key format**: Ensure you're using the private key, not public key
2. **Key not added to remote server**: Add public key to `~/.ssh/authorized_keys` on remote server
3. **Wrong permissions**: SSH key must be 600 permissions
4. **Passphrase-protected key**: Use keys without passphrase or configure SSH agent

## Web Interface Problems

### Cannot Access Web Interface

**Symptoms:**
- Browser shows "connection refused" or timeout
- Web interface doesn't load

**Solutions:**

1. **Check Container Status**
   ```bash
   docker compose ps
   docker compose logs audio-recorder
   ```

2. **Verify Port Mapping**
   ```bash
   docker port audio-stream-recorder 8666
   ```

3. **Test Local Access**
   ```bash
   # Test from host machine
   curl http://localhost:8666/health
   
   # Test from inside container
   docker exec -it audio-stream-recorder curl http://localhost:8666/health
   ```

4. **Check Firewall Settings**
   ```bash
   # Ubuntu/Debian
   sudo ufw status
   
   # CentOS/RHEL
   sudo firewall-cmd --list-ports
   ```

### Web Interface Loads But Features Don't Work

**Common Issues:**
1. **JavaScript Errors**: Check browser console for errors
2. **CSRF Token Issues**: Clear browser cache and cookies
3. **API Endpoint Failures**: Check network tab in browser developer tools

**Debugging:**
```bash
# Check API endpoints
curl http://localhost:8666/api/streams
curl http://localhost:8666/api/system/status
```

## Performance Issues

### High CPU Usage

**Causes & Solutions:**

1. **Too Many Concurrent Recordings**
   - Reduce `MAX_CONCURRENT_RECORDINGS`
   - Monitor system resources during recordings

2. **FFmpeg Processing Load**
   - Use hardware acceleration if available
   - Optimize encoding settings
   - Consider lower quality settings for high-volume recording

3. **Monitoring Overhead**
   - Increase `MONITORING_INTERVAL`
   - Reduce log verbosity

### High Memory Usage

**Solutions:**
1. **Enable Cleanup After Transfer**
   ```bash
   # In .env file
   CLEANUP_AFTER_TRANSFER=true
   ```

2. **Limit Recording Duration**
   - Set reasonable duration limits for recordings
   - Monitor memory usage during long recordings

3. **Container Resource Limits**
   ```yaml
   # In docker-compose.yml
   deploy:
     resources:
       limits:
         memory: 1G
   ```

### Slow Performance

**Optimization Steps:**
1. **Check Disk I/O**
   ```bash
   # Monitor disk usage
   iostat -x 1
   ```

2. **Network Performance**
   ```bash
   # Test network speed
   docker exec -it audio-stream-recorder wget -O /dev/null http://speedtest.example.com/file
   ```

3. **Container Resources**
   ```bash
   # Monitor container resources
   docker stats audio-stream-recorder
   ```

## Configuration Problems

### Invalid Cron Expressions

**Symptoms:**
- Schedules don't trigger at expected times
- "Invalid cron expression" errors

**Solutions:**
1. **Test Cron Expressions**
   - Use online cron validators
   - Test with simple expressions first
   - Verify timezone settings

2. **Common Cron Patterns**
   ```
   0 9 * * 1-5    # Weekdays at 9 AM
   30 14 * * 0    # Sundays at 2:30 PM
   0 */2 * * *    # Every 2 hours
   15 8,20 * * *  # Daily at 8:15 AM and 8:15 PM
   ```

### Environment Variable Issues

**Check Variable Loading:**
```bash
# View environment variables in container
docker exec -it audio-stream-recorder env | grep -E "(WEB_PORT|LOG_LEVEL|MAX_CONCURRENT)"
```

**Common Issues:**
1. **Spaces around equals signs**: Use `VAR=value`, not `VAR = value`
2. **Missing quotes for special characters**: Use quotes for values with spaces
3. **Case sensitivity**: Environment variables are case-sensitive

## Log Analysis

### Understanding Log Levels

- **DEBUG**: Detailed debugging information
- **INFO**: General operational messages
- **WARNING**: Warning messages and recoverable errors
- **ERROR**: Error messages requiring attention

### Important Log Files

```bash
# Application logs
docker exec -it audio-stream-recorder tail -f /app/logs/audio_recorder.log

# System logs
docker exec -it audio-stream-recorder tail -f /app/logs/system.log

# Error logs
docker exec -it audio-stream-recorder tail -f /app/logs/error.log
```

### Common Log Messages

| Message Pattern | Meaning | Action Required |
|----------------|---------|-----------------|
| `Recording session X started` | Recording began | Normal operation |
| `Stream connection failed` | Cannot connect to stream | Check stream URL and network |
| `SCP transfer failed` | File transfer error | Check SSH configuration |
| `Disk space warning` | Low disk space | Clean up old recordings |
| `FFmpeg error` | Audio processing failed | Check stream format |
| `Database error` | Database operation failed | Check database integrity |

### Log Analysis Commands

```bash
# Search for errors
docker exec -it audio-stream-recorder grep -i error /app/logs/*.log

# Count error occurrences
docker exec -it audio-stream-recorder grep -c "ERROR" /app/logs/audio_recorder.log

# View recent errors
docker exec -it audio-stream-recorder tail -n 100 /app/logs/error.log

# Search for specific session
docker exec -it audio-stream-recorder grep "session 123" /app/logs/*.log
```

## Network Issues

### Stream Connection Problems

**Diagnosis:**
```bash
# Test stream connectivity
docker exec -it audio-stream-recorder curl -I "https://stream-url.com/stream.m3u8"

# Check DNS resolution
docker exec -it audio-stream-recorder nslookup stream-hostname.com

# Test with different tools
docker exec -it audio-stream-recorder wget --spider "https://stream-url.com/stream.m3u8"
```

**Common Solutions:**
1. **Firewall blocking outbound connections**
2. **DNS resolution issues**
3. **Proxy configuration needed**
4. **Stream server geographical restrictions**

### SCP Connection Issues

**Network Troubleshooting:**
```bash
# Test SSH connectivity
docker exec -it audio-stream-recorder nc -zv hostname 22

# Check routing
docker exec -it audio-stream-recorder traceroute hostname

# Test with verbose SSH
docker exec -it audio-stream-recorder ssh -vvv -i /app/config/ssh_key user@hostname
```

## Storage Issues

### Disk Space Problems

**Monitoring:**
```bash
# Check overall disk usage
df -h

# Check container volumes
docker system df

# Check specific directories
du -sh data recordings logs artwork config
```

**Solutions:**
1. **Enable automatic cleanup**
   ```bash
   # In .env file
   CLEANUP_AFTER_TRANSFER=true
   ```

2. **Manual cleanup**
   ```bash
   # Remove old recordings (be careful!)
   find recordings -name "*.mp3" -mtime +7 -delete
   
   # Clean up old logs
   find logs -name "*.log.*" -mtime +30 -delete
   ```

3. **Log rotation**
   ```bash
   # Configure log rotation in docker-compose.yml
   logging:
     driver: "json-file"
     options:
       max-size: "100m"
       max-file: "5"
   ```

### Permission Issues

**Fix Permissions:**
```bash
# Fix ownership
sudo chown -R $USER:$USER data recordings logs artwork config

# Fix permissions
chmod -R 755 data recordings logs artwork config
chmod 600 config/ssh_key  # SSH key should be more restrictive
```

## Advanced Debugging

### Container Debugging

**Access Container Shell:**
```bash
# Get shell access
docker exec -it audio-stream-recorder /bin/bash

# Run commands inside container
docker exec -it audio-stream-recorder ps aux
docker exec -it audio-stream-recorder netstat -tulpn
```

**Inspect Container:**
```bash
# View container configuration
docker inspect audio-stream-recorder

# Check container resources
docker stats audio-stream-recorder

# View container processes
docker top audio-stream-recorder
```

### Database Debugging

**SQLite Database Access:**
```bash
# Access database directly
docker exec -it audio-stream-recorder sqlite3 /app/data/audio_recorder.db

# Common SQL queries
.tables
SELECT * FROM stream_configurations;
SELECT * FROM recording_schedules WHERE is_active = 1;
SELECT * FROM recording_sessions ORDER BY created_at DESC LIMIT 10;
```

### Application Debugging

**Python Debugging:**
```bash
# Check Python processes
docker exec -it audio-stream-recorder ps aux | grep python

# View Python modules
docker exec -it audio-stream-recorder python -c "import sys; print('\n'.join(sys.path))"

# Test imports
docker exec -it audio-stream-recorder python -c "from src.services.scheduler_service import SchedulerService"
```

### Network Debugging

**Container Networking:**
```bash
# Check container network
docker network ls
docker network inspect bridge

# Check container IP
docker inspect audio-stream-recorder | grep IPAddress

# Test internal connectivity
docker exec -it audio-stream-recorder ping 8.8.8.8
```

## Getting Help

If you're still experiencing issues after following this guide:

1. **Collect Information:**
   - Container logs: `docker compose logs audio-recorder > logs.txt`
   - System information: `docker version`, `docker compose version`
   - Configuration: `cat .env` (remove sensitive information)
   - Error messages and steps to reproduce

2. **Check Documentation:**
   - Review the main README.md
   - Check API documentation
   - Review configuration examples

3. **Search Existing Issues:**
   - Look for similar problems in the project repository
   - Check closed issues for solutions

4. **Create New Issue:**
   - Provide detailed description of the problem
   - Include relevant logs and configuration
   - Specify your environment (OS, Docker version, etc.)
   - List steps to reproduce the issue

## Preventive Measures

### Regular Maintenance

1. **Monitor Disk Space:**
   ```bash
   # Set up disk space monitoring
   df -h | grep -E "(recordings|data|logs)"
   ```

2. **Check Log Files:**
   ```bash
   # Regular log review
   grep -i error logs/*.log | tail -20
   ```

3. **Backup Configuration:**
   - Use the built-in backup feature regularly
   - Test restore procedures periodically

4. **Update Dependencies:**
   ```bash
   # Rebuild container with latest base image
   docker compose build --no-cache
   ```

### Monitoring Setup

**Health Checks:**
```bash
# Regular health check
curl -f http://localhost:8666/health || echo "Service unhealthy"

# System resource monitoring
docker stats --no-stream audio-stream-recorder
```

**Automated Monitoring:**
```bash
#!/bin/bash
# Simple monitoring script
if ! curl -f http://localhost:8666/health > /dev/null 2>&1; then
    echo "Audio Stream Recorder is unhealthy" | mail -s "Service Alert" admin@example.com
fi
```