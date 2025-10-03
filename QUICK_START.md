# Audio Stream Recorder - Quick Start Guide

Get up and running with Audio Stream Recorder in minutes!

## Prerequisites

- Docker and Docker Compose installed
- At least 1GB free disk space
- Network access for stream recording

## 5-Minute Setup

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd audio-stream-recorder

# Run the installation setup
./deploy.sh install
```

### 2. Configure Environment

```bash
# Edit the environment file
nano .env

# Minimum required changes:
# - Change SECRET_KEY to a random string
# - Set your timezone (TZ=America/New_York)
```

### 3. Start the Application

```bash
# Start with development configuration
./deploy.sh start

# OR start with production configuration
./deploy.sh start prod
```

### 4. Access Web Interface

Open your browser and go to: **http://localhost:8666**

### 5. Configure Your First Stream

1. Click **"Streams"** in the navigation
2. Click **"Add New Stream"**
3. Fill in the form:
   - **Name**: My Radio Show
   - **Stream URL**: https://example.com/stream.m3u8
   - **Artist**: Radio Station
   - **Album**: Daily Shows
   - **Album Artist**: Radio Station
   - **SCP Destination**: user@server:/path/to/recordings/

4. Click **"Save Stream"**

### 6. Create a Recording Schedule

1. Click **"Schedules"** in the navigation
2. Click **"Add New Schedule"**
3. Configure:
   - **Stream**: Select "My Radio Show"
   - **Cron Expression**: `0 9 * * 1-5` (weekdays at 9 AM)
   - **Duration**: 1 hour 0 minutes
   - **Active**: ✅ Enabled

4. Click **"Save Schedule"**

## SSH Setup for File Transfers

If you want automatic file transfers via SCP:

```bash
# Copy your SSH private key
cp ~/.ssh/id_rsa config/ssh_key
chmod 600 config/ssh_key

# Test SSH connection
ssh -i config/ssh_key user@your-server.com
```

## Common Cron Expressions

| Expression | Description |
|------------|-------------|
| `0 9 * * 1-5` | Weekdays at 9:00 AM |
| `30 14 * * 0` | Sundays at 2:30 PM |
| `0 */2 * * *` | Every 2 hours |
| `15 8,20 * * *` | Daily at 8:15 AM and 8:15 PM |

## Useful Commands

```bash
# Check status
./deploy.sh status

# View logs
./deploy.sh logs

# Detailed system status
./deploy.sh detailed-status

# Stop the application
./deploy.sh stop

# Restart the application
./deploy.sh restart

# Create configuration backup
./deploy.sh backup

# Update to latest version
./deploy.sh update
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs for errors
./deploy.sh logs

# Verify Docker is running
docker --version
docker-compose --version

# Check port availability
netstat -tulpn | grep 8666
```

### Can't Access Web Interface

1. Check if container is running: `./deploy.sh status`
2. Verify port in .env file: `grep WEB_PORT .env`
3. Test health endpoint: `curl http://localhost:8666/health`

### Recording Fails

1. Test stream URL in a media player (VLC)
2. Check stream configuration in web interface
3. Review logs: `./deploy.sh logs`

### SCP Transfer Fails

1. Verify SSH key: `ssh -i config/ssh_key user@server`
2. Check destination path exists on remote server
3. Verify SCP destination format: `user@server:/path/`

## Next Steps

- **Monitor**: Use the Dashboard to monitor active recordings
- **Backup**: Set up regular configuration backups
- **Customize**: Adjust settings in .env for your needs
- **Scale**: Use production configuration for high-volume recording

## Getting Help

- 📖 Read the full [README.md](README.md)
- 🔧 Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- 🐛 Report issues on the project repository

## Production Deployment

For production use:

```bash
# Use production configuration
./deploy.sh start prod

# Set production environment variables in .env:
LOG_LEVEL=INFO
MAX_CONCURRENT_RECORDINGS=5
CLEANUP_AFTER_TRANSFER=true
```

That's it! You now have a fully functional audio stream recorder running in Docker. 🎉