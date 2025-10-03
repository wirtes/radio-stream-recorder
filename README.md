# Audio Stream Recorder

A containerized Python application for automated recording, processing, and distribution of audio streams. Features a web-based interface for configuration, cron-like scheduling, and automatic file transfer via SCP.

## Features

- **Web-based Configuration**: Intuitive interface for managing stream configurations and recording schedules
- **Automated Recording**: Cron-like scheduling for recurring recordings with configurable duration
- **Audio Processing**: Automatic conversion to MP3 with metadata embedding and artwork support
- **File Transfer**: Secure SCP transfer to remote destinations with retry logic
- **Monitoring & Logging**: Comprehensive system monitoring with real-time status updates
- **Configuration Backup**: Automatic and manual backup/restore of system configuration
- **Docker Containerized**: Easy deployment with persistent storage and health monitoring

## Quick Start

### Prerequisites

- Docker and Docker Compose
- SSH key for remote file transfers (optional)

### Basic Deployment

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd audio-stream-recorder
   ```

2. **Create configuration directories:**
   ```bash
   mkdir -p data recordings logs artwork config
   ```

3. **Copy example configuration:**
   ```bash
   cp docker-compose.yml.example docker-compose.yml
   cp .env.example .env
   ```

4. **Edit environment variables:**
   ```bash
   nano .env
   ```

5. **Start the application:**
   ```bash
   docker-compose up -d
   ```

6. **Access the web interface:**
   Open http://localhost:8666 in your browser

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_PORT` | `8666` | Web interface port |
| `WEB_HOST` | `0.0.0.0` | Web interface host |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `MAX_CONCURRENT_RECORDINGS` | `3` | Maximum simultaneous recordings |
| `CLEANUP_AFTER_TRANSFER` | `true` | Delete local files after successful SCP transfer |
| `MAX_ARTWORK_SIZE_MB` | `10` | Maximum artwork file size in MB |
| `DEFAULT_MAX_RETRIES` | `3` | Default retry count for failed operations |
| `RETRY_DELAY_SECONDS` | `60` | Delay between retry attempts |

### Volume Mounts

The application uses several volume mounts for persistent data:

- `/app/data` - Database and application data
- `/app/recordings` - Temporary storage for recorded files
- `/app/logs` - Application logs
- `/app/artwork` - Uploaded artwork files
- `/app/config` - SSH keys and configuration files

### SSH Configuration

For SCP file transfers, place your SSH private key in the `config` directory:

```bash
# Copy your SSH key
cp ~/.ssh/id_rsa ./config/ssh_key
chmod 600 ./config/ssh_key
```

Configure your stream's SCP destination as: `user@hostname:/path/to/destination/`

## Usage

### Stream Configuration

1. Navigate to **Streams** in the web interface
2. Click **Add New Stream**
3. Configure:
   - **Name**: Unique identifier for the stream
   - **Stream URL**: HTTP/HTTPS/RTMP stream URL
   - **Metadata**: Artist, Album, Album Artist information
   - **Artwork**: Optional cover art image
   - **SCP Destination**: Remote transfer location

### Recording Schedules

1. Navigate to **Schedules** in the web interface
2. Click **Add New Schedule**
3. Configure:
   - **Stream**: Select configured stream
   - **Cron Expression**: Schedule using cron syntax (e.g., `0 9 * * 1-5` for weekdays at 9 AM)
   - **Duration**: Recording length in hours and minutes
   - **Active**: Enable/disable the schedule

### Cron Expression Examples

| Expression | Description |
|------------|-------------|
| `0 9 * * 1-5` | Weekdays at 9:00 AM |
| `30 14 * * 0` | Sundays at 2:30 PM |
| `0 */2 * * *` | Every 2 hours |
| `15 8,20 * * *` | Daily at 8:15 AM and 8:15 PM |

### Monitoring

- **Dashboard**: Overview of system status and active recordings
- **Sessions**: View recording history and status
- **Logs**: Real-time system logs and error messages
- **System Status**: Resource usage and health monitoring

### Configuration Backup

The system automatically creates daily configuration backups. Manual backups can be created from the **Backup** page:

1. Navigate to **Backup** in the web interface
2. Click **Create Backup**
3. Optionally specify a custom name
4. Choose whether to include artwork files

To restore a configuration:
1. Select a backup from the list
2. Click **Restore**
3. Choose whether to overwrite existing configurations

## Docker Compose Examples

### Basic Setup

```yaml
version: '3.8'

services:
  audio-recorder:
    build: .
    ports:
      - "8666:8666"
    volumes:
      - ./data:/app/data
      - ./recordings:/app/recordings
      - ./logs:/app/logs
      - ./artwork:/app/artwork
      - ./config:/app/config
    environment:
      - WEB_PORT=8666
      - LOG_LEVEL=INFO
      - MAX_CONCURRENT_RECORDINGS=3
    restart: unless-stopped
```

### Production Setup with Custom Network

```yaml
version: '3.8'

services:
  audio-recorder:
    build: .
    container_name: audio-stream-recorder
    ports:
      - "8666:8666"
    volumes:
      - /opt/audio-recorder/data:/app/data
      - /opt/audio-recorder/recordings:/app/recordings
      - /var/log/audio-recorder:/app/logs
      - /opt/audio-recorder/artwork:/app/artwork
      - /opt/audio-recorder/config:/app/config
    environment:
      - WEB_PORT=8666
      - LOG_LEVEL=INFO
      - MAX_CONCURRENT_RECORDINGS=5
      - CLEANUP_AFTER_TRANSFER=true
      - DEFAULT_MAX_RETRIES=5
    networks:
      - audio-recorder-net
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8666/health"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  audio-recorder-net:
    driver: bridge
```

### Development Setup

```yaml
version: '3.8'

services:
  audio-recorder:
    build: .
    ports:
      - "8666:8666"
    volumes:
      - ./data:/app/data
      - ./recordings:/app/recordings
      - ./logs:/app/logs
      - ./artwork:/app/artwork
      - ./config:/app/config
      - ./src:/app/src  # Mount source for development
    environment:
      - WEB_PORT=8666
      - LOG_LEVEL=DEBUG
      - MAX_CONCURRENT_RECORDINGS=2
      - FLASK_DEBUG=true
    restart: "no"
```

## API Documentation

The application provides a REST API for programmatic access:

### Health Check
```
GET /health
```

### Stream Management
```
GET /api/streams                    # List all streams
POST /api/streams                   # Create new stream
GET /api/streams/{id}               # Get specific stream
PUT /api/streams/{id}               # Update stream
DELETE /api/streams/{id}            # Delete stream
POST /api/streams/{id}/test         # Test stream connection
```

### Schedule Management
```
GET /api/schedules                  # List all schedules
POST /api/schedules                 # Create new schedule
GET /api/schedules/{id}             # Get specific schedule
PUT /api/schedules/{id}             # Update schedule
DELETE /api/schedules/{id}          # Delete schedule
POST /api/schedules/validate-cron   # Validate cron expression
```

### System Monitoring
```
GET /api/system/status              # System status and metrics
GET /api/logs                       # Recent system logs
GET /api/sessions                   # Recording sessions
```

### Configuration Backup
```
POST /api/backup/create             # Create backup
GET /api/backup/list                # List backups
POST /api/backup/restore            # Restore backup
POST /api/backup/validate           # Validate backup
DELETE /api/backup/delete           # Delete backup
```

## Troubleshooting

### Common Issues

#### Container Won't Start

**Problem**: Container exits immediately or fails to start

**Solutions**:
1. Check Docker logs: `docker-compose logs audio-recorder`
2. Verify volume permissions: `chmod -R 755 data recordings logs artwork config`
3. Ensure required directories exist: `mkdir -p data recordings logs artwork config`
4. Check port availability: `netstat -tulpn | grep 8666`

#### Recording Fails

**Problem**: Recordings start but fail during processing

**Solutions**:
1. Check stream URL accessibility: Test the URL in a media player
2. Verify FFmpeg installation in container: `docker exec -it <container> ffmpeg -version`
3. Check disk space: Monitor the `/app/recordings` volume
4. Review logs for specific error messages

#### SCP Transfer Fails

**Problem**: Files record successfully but transfer fails

**Solutions**:
1. Verify SSH key permissions: `chmod 600 config/ssh_key`
2. Test SSH connection manually: `ssh -i config/ssh_key user@hostname`
3. Check destination directory permissions on remote server
4. Verify SCP destination format: `user@hostname:/path/to/destination/`

#### Web Interface Not Accessible

**Problem**: Cannot access web interface

**Solutions**:
1. Check container status: `docker-compose ps`
2. Verify port mapping: `docker port <container> 8666`
3. Check firewall settings
4. Try accessing via container IP: `docker inspect <container> | grep IPAddress`

#### High Memory Usage

**Problem**: Container uses excessive memory

**Solutions**:
1. Reduce `MAX_CONCURRENT_RECORDINGS`
2. Enable `CLEANUP_AFTER_TRANSFER=true`
3. Monitor recording file sizes and durations
4. Check for memory leaks in logs

### Log Analysis

#### Important Log Locations

- Application logs: `logs/audio_recorder.log`
- System logs: `logs/system.log`
- Error logs: `logs/error.log`

#### Log Level Configuration

Set `LOG_LEVEL` environment variable:
- `DEBUG`: Detailed debugging information
- `INFO`: General operational messages
- `WARNING`: Warning messages and recoverable errors
- `ERROR`: Error messages only

#### Common Log Messages

| Message Pattern | Meaning | Action |
|----------------|---------|---------|
| `Recording session X started` | Recording began successfully | Normal operation |
| `Stream connection failed` | Cannot connect to stream URL | Check stream URL and network |
| `SCP transfer failed` | File transfer error | Check SSH configuration |
| `Disk space warning` | Low disk space | Clean up old recordings |
| `FFmpeg error` | Audio processing failed | Check stream format compatibility |

### Performance Tuning

#### Resource Optimization

1. **CPU Usage**:
   - Reduce concurrent recordings
   - Use hardware-accelerated encoding if available
   - Monitor FFmpeg process usage

2. **Memory Usage**:
   - Enable automatic cleanup after transfer
   - Limit recording duration for long streams
   - Monitor container memory limits

3. **Disk Usage**:
   - Enable `CLEANUP_AFTER_TRANSFER`
   - Implement log rotation
   - Monitor recording directory size

4. **Network Usage**:
   - Use appropriate stream quality settings
   - Monitor bandwidth during concurrent recordings
   - Consider local network capacity

## Development

### Building from Source

```bash
# Clone repository
git clone <repository-url>
cd audio-stream-recorder

# Build Docker image
docker build -t audio-stream-recorder .

# Run development container
docker-compose -f docker-compose.yml up
```

### Running Tests

```bash
# Install development dependencies
pip install -r requirements.txt

# Run unit tests
python -m pytest tests/

# Run integration tests
python tests/run_integration_tests.py
```

### Project Structure

```
audio-stream-recorder/
├── src/                    # Application source code
│   ├── models/            # Database models and repositories
│   ├── services/          # Business logic services
│   └── web/               # Web interface and API
├── templates/             # HTML templates
├── static/                # CSS, JavaScript, and static assets
├── tests/                 # Test suite
├── config/                # SSH keys and configuration files
├── data/                  # Database and application data
├── recordings/            # Temporary recording storage
├── logs/                  # Application logs
├── artwork/               # Uploaded artwork files
├── Dockerfile             # Container build configuration
├── docker-compose.yml     # Container orchestration
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and add tests
4. Run the test suite: `python -m pytest`
5. Commit your changes: `git commit -am 'Add feature'`
6. Push to the branch: `git push origin feature-name`
7. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:

1. Check the troubleshooting section above
2. Review the application logs
3. Search existing issues in the repository
4. Create a new issue with detailed information including:
   - Docker version and OS
   - Container logs
   - Configuration details
   - Steps to reproduce the problem
