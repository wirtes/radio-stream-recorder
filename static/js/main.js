/**
 * Main JavaScript file for Audio Stream Recorder web interface
 */

// Global application object
window.AudioRecorder = {
    csrfToken: null,
    
    // Initialize the application
    init: function() {
        this.setupCSRF();
        this.setupEventListeners();
        this.setupAjaxDefaults();
    },
    
    // Setup CSRF token for AJAX requests
    setupCSRF: function() {
        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
        if (csrfMeta) {
            this.csrfToken = csrfMeta.getAttribute('content');
        }
    },
    
    // Setup global event listeners
    setupEventListeners: function() {
        // Handle form submissions with CSRF
        document.addEventListener('submit', this.handleFormSubmit.bind(this));
        
        // Handle AJAX form submissions
        document.addEventListener('click', this.handleAjaxActions.bind(this));
        
        // Handle file uploads
        document.addEventListener('change', this.handleFileUploads.bind(this));
    },
    
    // Setup default AJAX settings
    setupAjaxDefaults: function() {
        // Add CSRF token to all AJAX requests
        const originalFetch = window.fetch;
        window.fetch = function(url, options = {}) {
            if (AudioRecorder.csrfToken && ['POST', 'PUT', 'DELETE', 'PATCH'].includes((options.method || 'GET').toUpperCase())) {
                options.headers = options.headers || {};
                options.headers['X-CSRF-Token'] = AudioRecorder.csrfToken;
            }
            return originalFetch(url, options);
        };
    },
    
    // Handle form submissions
    handleFormSubmit: function(event) {
        const form = event.target;
        if (form.tagName !== 'FORM') return;
        
        // Add CSRF token to forms if not present
        if (this.csrfToken && !form.querySelector('input[name="csrf_token"]')) {
            const csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrf_token';
            csrfInput.value = this.csrfToken;
            form.appendChild(csrfInput);
        }
    },
    
    // Handle AJAX actions (buttons with data-action attribute)
    handleAjaxActions: function(event) {
        const button = event.target.closest('[data-action]');
        if (!button) return;
        
        event.preventDefault();
        
        const action = button.getAttribute('data-action');
        const url = button.getAttribute('data-url');
        const method = button.getAttribute('data-method') || 'GET';
        const confirm = button.getAttribute('data-confirm');
        
        if (confirm && !window.confirm(confirm)) {
            return;
        }
        
        this.performAjaxAction(url, method, null, button);
    },
    
    // Handle file upload previews
    handleFileUploads: function(event) {
        const input = event.target;
        if (input.type !== 'file') return;
        
        const previewContainer = document.querySelector(`#${input.id}-preview`);
        if (!previewContainer) return;
        
        const file = input.files[0];
        if (!file) {
            previewContainer.innerHTML = '';
            return;
        }
        
        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = function(e) {
                previewContainer.innerHTML = `<img src="${e.target.result}" alt="Preview" style="max-width: 200px; max-height: 200px;">`;
            };
            reader.readAsDataURL(file);
        } else {
            previewContainer.innerHTML = `<p>File selected: ${file.name} (${AudioRecorder.formatFileSize(file.size)})</p>`;
        }
    },
    
    // Perform AJAX action
    performAjaxAction: function(url, method = 'GET', data = null, button = null) {
        if (button) {
            button.disabled = true;
            const originalText = button.textContent;
            button.innerHTML = '<span class="spinner"></span> Loading...';
        }
        
        const options = {
            method: method.toUpperCase(),
            headers: {
                'Content-Type': 'application/json',
            }
        };
        
        if (data) {
            options.body = JSON.stringify(data);
        }
        
        return fetch(url, options)
            .then(response => {
                if (!response.ok) {
                    return response.json().then(err => Promise.reject(err));
                }
                return response.json();
            })
            .then(data => {
                this.showAlert('Operation completed successfully', 'success');
                return data;
            })
            .catch(error => {
                console.error('AJAX Error:', error);
                this.showAlert(error.message || 'An error occurred', 'danger');
                throw error;
            })
            .finally(() => {
                if (button) {
                    button.disabled = false;
                    button.innerHTML = button.getAttribute('data-original-text') || 'Action';
                }
            });
    },
    
    // Show alert message
    showAlert: function(message, type = 'info', duration = 5000) {
        const alertContainer = document.getElementById('alert-container') || this.createAlertContainer();
        
        const alert = document.createElement('div');
        alert.className = `alert alert-${type}`;
        alert.innerHTML = `
            ${message}
            <button type="button" class="btn-close" onclick="this.parentElement.remove()">×</button>
        `;
        
        alertContainer.appendChild(alert);
        
        if (duration > 0) {
            setTimeout(() => {
                if (alert.parentElement) {
                    alert.remove();
                }
            }, duration);
        }
    },
    
    // Create alert container if it doesn't exist
    createAlertContainer: function() {
        const container = document.createElement('div');
        container.id = 'alert-container';
        container.style.position = 'fixed';
        container.style.top = '20px';
        container.style.right = '20px';
        container.style.zIndex = '9999';
        container.style.maxWidth = '400px';
        document.body.appendChild(container);
        return container;
    },
    
    // Utility function to format file size
    formatFileSize: function(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },
    
    // Utility function to format duration
    formatDuration: function(seconds) {
        if (seconds < 60) {
            return `${seconds}s`;
        } else if (seconds < 3600) {
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = seconds % 60;
            return `${minutes}m ${remainingSeconds}s`;
        } else {
            const hours = Math.floor(seconds / 3600);
            const remainingMinutes = Math.floor((seconds % 3600) / 60);
            return `${hours}h ${remainingMinutes}m`;
        }
    },
    
    // Validate cron expression
    validateCronExpression: function(expression) {
        const parts = expression.trim().split(/\s+/);
        if (parts.length !== 5) {
            return 'Cron expression must have exactly 5 fields: minute hour day month weekday';
        }
        
        const patterns = [
            /^(\*|([0-5]?\d)(,([0-5]?\d))*|([0-5]?\d)-([0-5]?\d))$/, // minute
            /^(\*|(1?\d|2[0-3])(,(1?\d|2[0-3]))*|(1?\d|2[0-3])-(1?\d|2[0-3]))$/, // hour
            /^(\*|([1-2]?\d|3[01])(,([1-2]?\d|3[01]))*|([1-2]?\d|3[01])-([1-2]?\d|3[01]))$/, // day
            /^(\*|([1-9]|1[0-2])(,([1-9]|1[0-2]))*|([1-9]|1[0-2])-([1-9]|1[0-2]))$/, // month
            /^(\*|[0-6](,[0-6])*|[0-6]-[0-6])$/ // weekday
        ];
        
        for (let i = 0; i < parts.length; i++) {
            if (!patterns[i].test(parts[i])) {
                return `Invalid value in field ${i + 1}: ${parts[i]}`;
            }
        }
        
        return null; // Valid
    },
    
    // Real-time updates
    startRealTimeUpdates: function(endpoint, callback, interval = 5000) {
        const updateFunction = () => {
            fetch(endpoint)
                .then(response => response.json())
                .then(data => callback(data))
                .catch(error => console.error('Real-time update error:', error));
        };
        
        updateFunction(); // Initial call
        return setInterval(updateFunction, interval);
    },
    
    // Stop real-time updates
    stopRealTimeUpdates: function(intervalId) {
        if (intervalId) {
            clearInterval(intervalId);
        }
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    AudioRecorder.init();
});

// Export for use in other scripts
window.AudioRecorder = AudioRecorder;