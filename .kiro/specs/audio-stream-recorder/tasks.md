# Implementation Plan

- [x] 1. Set up project structure and core dependencies
  - Create directory structure for models, services, web interface, and Docker configuration
  - Set up requirements.txt with all necessary Python dependencies (Flask/FastAPI, SQLAlchemy, APScheduler, Paramiko, Mutagen, etc.)
  - Create basic project configuration and environment variable handling
  - _Requirements: 7.1, 7.2_

- [ ] 2. Implement data models and database layer
  - [ ] 2.1 Create SQLAlchemy data models for stream configurations, schedules, and recording sessions
    - Implement StreamConfiguration model with validation
    - Implement RecordingSchedule model with cron expression validation
    - Implement RecordingSession model for tracking recording status
    - _Requirements: 2.2, 3.1, 3.2_

  - [ ] 2.2 Implement database repository layer with CRUD operations
    - Create ConfigurationRepository for stream management
    - Create ScheduleRepository for recording schedule management
    - Create SessionRepository for recording session tracking
    - _Requirements: 2.4, 2.5, 3.4, 3.5_

  - [ ]* 2.3 Write unit tests for data models and repositories
    - Test model validation and constraints
    - Test repository CRUD operations
    - Test database relationships and foreign keys
    - _Requirements: 2.4, 3.1_

- [ ] 3. Create audio recording and processing components
  - [ ] 3.1 Implement StreamRecorder class for audio capture
    - Create interface for FFmpeg-based stream recording
    - Implement support for multiple streaming protocols (HTTP, HTTPS, RTMP)
    - Add stream validation and connection testing functionality
    - Implement recording duration limits and automatic stop functionality
    - _Requirements: 1.1, 1.7, 6.1, 6.4, 6.5_

  - [ ] 3.2 Implement AudioProcessor class for format conversion and metadata
    - Create MP3 conversion functionality using FFmpeg
    - Implement metadata calculation (auto-generated title, track number from days since Jan 1 2020)
    - Add metadata embedding functionality using Mutagen
    - Implement artwork embedding for MP3 files
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 6.2_

  - [ ] 3.3 Create RecordingSession manager for workflow orchestration
    - Implement complete recording workflow (capture → process → transfer)
    - Add error handling and retry logic for failed recordings
    - Create real-time status tracking and progress reporting
    - _Requirements: 1.1, 1.2, 1.3, 3.3, 3.4, 5.4_

  - [ ]* 3.4 Write unit tests for audio components
    - Mock FFmpeg operations for testing
    - Test metadata calculation and embedding
    - Test error handling and retry logic
    - _Requirements: 1.4, 1.5, 6.3_

- [ ] 4. Implement file transfer system
  - [ ] 4.1 Create SCPTransferService for secure file transfers
    - Implement SSH key-based authentication using Paramiko
    - Add configurable retry logic with exponential backoff
    - Create transfer progress monitoring and logging
    - _Requirements: 4.1, 4.2, 4.4, 4.5_

  - [ ] 4.2 Implement TransferQueue for managing failed transfers
    - Create queue system for retry attempts
    - Add configurable cleanup of local files after successful transfer
    - Implement transfer status tracking and reporting
    - _Requirements: 4.3, 4.4_

  - [ ]* 4.3 Write unit tests for file transfer components
    - Mock SSH/SCP operations for testing
    - Test retry logic and error handling
    - Test transfer queue functionality
    - _Requirements: 4.4, 4.5_

- [ ] 5. Create scheduler system
  - [ ] 5.1 Implement SchedulerService using APScheduler
    - Create cron expression parsing and validation
    - Implement job scheduling and persistence across container restarts
    - Add support for concurrent recording sessions with limits
    - _Requirements: 3.1, 3.3, 3.6, 7.5_

  - [ ] 5.2 Create JobManager for schedule lifecycle management
    - Implement job creation, updating, and deletion
    - Add next execution time calculation and display
    - Create job status tracking and failure handling
    - _Requirements: 3.5, 3.6_

  - [ ]* 5.3 Write unit tests for scheduler components
    - Test cron expression parsing and validation
    - Test job scheduling and persistence
    - Test concurrent recording limits
    - _Requirements: 3.1, 3.6_

- [ ] 6. Build web interface and API
  - [ ] 6.1 Create Flask/FastAPI application structure
    - Set up web framework with proper routing
    - Implement request/response models using Pydantic
    - Add CSRF protection and input validation
    - Configure static file serving for CSS/JS
    - _Requirements: 2.1, 7.3_

  - [ ] 6.2 Implement stream configuration API endpoints
    - Create CRUD endpoints for stream configurations
    - Add stream URL validation and testing functionality
    - Implement artwork file upload and management
    - Add configuration export/import functionality
    - _Requirements: 2.2, 2.3, 2.4, 2.5_

  - [ ] 6.3 Implement schedule management API endpoints
    - Create endpoints for recording schedule CRUD operations
    - Add cron expression validation and next-run calculation
    - Implement schedule activation/deactivation functionality
    - _Requirements: 3.1, 3.2, 3.5_

  - [ ] 6.4 Create system monitoring and logging API endpoints
    - Implement real-time system status API
    - Add log viewing and filtering functionality
    - Create recording session status and progress endpoints
    - Add system health monitoring (disk space, memory usage)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ] 6.5 Build HTML templates and user interface
    - Create responsive dashboard showing streams and schedules
    - Build stream configuration forms with validation
    - Implement schedule management interface with cron input
    - Add real-time status updates and log viewing
    - Create artwork upload and preview functionality
    - _Requirements: 2.1, 2.2, 3.1, 5.3, 5.4_

  - [ ]* 6.6 Write integration tests for web interface
    - Test API endpoints with various input scenarios
    - Test form validation and error handling
    - Test file upload functionality
    - _Requirements: 2.4, 6.3_

- [ ] 7. Implement logging and monitoring system
  - [ ] 7.1 Create comprehensive logging infrastructure
    - Set up structured logging with timestamps and operation types
    - Implement log rotation and retention policies
    - Add different log levels for various system operations
    - Create log persistence to host-mounted volumes
    - _Requirements: 5.1, 5.2_

  - [ ] 7.2 Add system monitoring and health checks
    - Implement resource monitoring (disk space, memory usage)
    - Create system health endpoints for container orchestration
    - Add performance metrics collection and reporting
    - _Requirements: 5.5_

- [ ] 8. Create Docker containerization
  - [ ] 8.1 Build Dockerfile with all system dependencies
    - Create multi-stage build for optimized container size
    - Install FFmpeg, SSH client, and Python dependencies
    - Configure proper user permissions and security settings
    - _Requirements: 7.1, 7.2_

  - [ ] 8.2 Implement container initialization and service startup
    - Create startup script for initializing database and services
    - Add proper signal handling for graceful shutdown
    - Implement health check endpoints for container monitoring
    - Configure volume mounts for persistent data storage
    - _Requirements: 7.3, 7.4, 7.5, 7.6_

  - [ ] 8.3 Create docker-compose configuration for easy deployment
    - Define volume mounts for data, recordings, config, logs, and artwork
    - Configure network settings and port mapping (default 8666)
    - Add environment variable configuration
    - Create example configuration files
    - _Requirements: 7.3, 7.4_

- [ ] 9. Integrate all components and create main application
  - [ ] 9.1 Create main application entry point
    - Initialize all services (web, scheduler, logging)
    - Set up proper dependency injection and service coordination
    - Implement graceful startup and shutdown procedures
    - _Requirements: 7.5_

  - [ ] 9.2 Wire together the complete recording workflow
    - Connect scheduler to recording components
    - Link audio processing to file transfer system
    - Integrate web interface with all backend services
    - Add end-to-end error handling and recovery
    - _Requirements: 1.1, 1.2, 1.3, 4.1, 3.3_

  - [ ]* 9.3 Create end-to-end integration tests
    - Test complete recording workflow from schedule to transfer
    - Test web interface integration with backend services
    - Test container deployment and volume persistence
    - _Requirements: 7.6_

- [ ] 10. Add configuration management and deployment utilities
  - [ ] 10.1 Create configuration backup and restore functionality
    - Implement automatic configuration backups
    - Add manual backup/restore through web interface
    - Create configuration validation and migration tools
    - _Requirements: 7.6_

  - [ ] 10.2 Build deployment documentation and example configurations
    - Create comprehensive README with setup instructions
    - Add example docker-compose.yml with volume configurations
    - Document environment variables and configuration options
    - Create troubleshooting guide for common issues
    - _Requirements: 7.1, 7.3, 7.4_