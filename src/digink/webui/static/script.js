// Digink Web UI JavaScript

// Global variables for screensaver monitoring
let screensaverCheckInterval = null;
let layoutRefreshInterval = null;

document.addEventListener('DOMContentLoaded', function() {
    // Load device information and screensaver status on page load
    loadDeviceInfo();
    loadScreensaverStatus();
    
    // Image preview functionality
    const imageInput = document.getElementById('image-input');
    const imagePreview = document.getElementById('image-preview');
    const previewImg = document.getElementById('preview-img');
    
    if (imageInput) {
        imageInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    previewImg.src = e.target.result;
                    imagePreview.style.display = 'block';
                };
                reader.readAsDataURL(file);
            } else {
                imagePreview.style.display = 'none';
            }
        });
    }
    
    // Upload form handling
    const uploadForm = document.getElementById('upload-form');
    const uploadBtn = document.getElementById('upload-btn');
    const uploadSpinner = document.getElementById('upload-spinner');
    
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            // Show loading state
            uploadBtn.disabled = true;
            uploadSpinner.style.display = 'inline-block';
            uploadBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Sending...';
        });
    }
    
    // Refresh buttons
    const refreshLayoutBtn = document.getElementById('refresh-layout');
    const refreshDevicesBtn = document.getElementById('refresh-devices');
    const clearScreensBtn = document.getElementById('clear-screens');
    
    if (refreshLayoutBtn) {
        refreshLayoutBtn.addEventListener('click', function() {
            refreshLayout();
        });
    }
    
    if (refreshDevicesBtn) {
        refreshDevicesBtn.addEventListener('click', function() {
            loadDeviceInfo();
        });
    }
    
    if (clearScreensBtn) {
        clearScreensBtn.addEventListener('click', function() {
            clearAllScreens();
        });
    }
    
    // Screensaver buttons
    const startScreensaverBtn = document.getElementById('start-screensaver');
    const stopScreensaverBtn = document.getElementById('stop-screensaver');
    
    if (startScreensaverBtn) {
        startScreensaverBtn.addEventListener('click', function() {
            startScreensaver();
        });
    }
    
    if (stopScreensaverBtn) {
        stopScreensaverBtn.addEventListener('click', function() {
            stopScreensaver();
        });
    }
    
    // Interval update button
    const updateIntervalBtn = document.getElementById('update-interval');
    if (updateIntervalBtn) {
        updateIntervalBtn.addEventListener('click', function() {
            updateScreensaverInterval();
        });
    }
});

function loadDeviceInfo() {
    const deviceInfo = document.getElementById('device-info');
    if (!deviceInfo) return;
    
    // Show loading state
    deviceInfo.innerHTML = `
        <div class="d-flex justify-content-center">
            <div class="spinner-border" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
        </div>
    `;
    
    fetch('/devices')
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                deviceInfo.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
                return;
            }
            
            let html = '';
            data.devices.forEach((device, index) => {
                html += `
                    <div class="device-card border rounded p-3 mb-2">
                        <div class="device-host">${device.host}</div>
                        <div class="device-details">
                            Screen: ${device.screen_type}<br>
                            Position: (${device.coordinates.x}, ${device.coordinates.y})<br>
                            Rotation: ${device.rotation}°<br>
                            Size: ${device.dimensions.width.toFixed(1)} × ${device.dimensions.height.toFixed(1)} mm
                        </div>
                    </div>
                `;
            });
            
            if (html === '') {
                html = '<div class="alert alert-warning">No devices configured</div>';
            }
            
            deviceInfo.innerHTML = html;
        })
        .catch(error => {
            console.error('Error loading device info:', error);
            deviceInfo.innerHTML = '<div class="alert alert-danger">Failed to load device information</div>';
        });
}

function refreshLayout() {
    const layoutImg = document.getElementById('layout-image');
    if (layoutImg) {
        // Add timestamp to force refresh
        const timestamp = new Date().getTime();
        layoutImg.src = `/layout?t=${timestamp}`;
    }
}

function clearAllScreens() {
    const clearBtn = document.getElementById('clear-screens');
    if (!clearBtn) return;
    
    // Show confirmation dialog
    if (!confirm('Are you sure you want to clear all screens?')) {
        return;
    }
    
    // Show loading state
    const originalText = clearBtn.innerHTML;
    clearBtn.disabled = true;
    clearBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Clearing...';
    
    fetch('/clear', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Show success message
            showAlert(data.message, 'success');
        } else {
            showAlert(data.error || 'Failed to clear screens', 'danger');
        }
    })
    .catch(error => {
        console.error('Error clearing screens:', error);
        showAlert('Failed to clear screens', 'danger');
    })
    .finally(() => {
        // Restore button state
        clearBtn.disabled = false;
        clearBtn.innerHTML = originalText;
    });
}

function showAlert(message, type = 'info') {
    // Create alert element
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // Insert at top of container
    const container = document.querySelector('.container');
    const firstChild = container.firstElementChild;
    container.insertBefore(alertDiv, firstChild);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        const bsAlert = new bootstrap.Alert(alertDiv);
        bsAlert.close();
    }, 5000);
}

function loadScreensaverStatus() {
    const statusDiv = document.getElementById('screensaver-status');
    const startBtn = document.getElementById('start-screensaver');
    const stopBtn = document.getElementById('stop-screensaver');
    const intervalInput = document.getElementById('interval-input');
    
    if (!statusDiv) return;
    
    fetch('/screensaver/status')
        .then(response => response.json())
        .then(data => {
            let statusHtml = '';
            
            if (data.active) {
                statusHtml = `
                    <div class="alert alert-success mb-0">
                        <i class="bi bi-play-circle-fill"></i> 
                        <strong>Active</strong><br>
                        <small>Cycling through ${data.image_count} wallpapers every ${data.interval}s</small>
                    </div>
                `;
                startBtn.style.display = 'none';
                stopBtn.style.display = 'block';
                
                // Start monitoring screensaver and refreshing layout
                startScreensaverMonitoring(data.interval);
            } else {
                if (data.has_images) {
                    statusHtml = `
                        <div class="alert alert-secondary mb-0">
                            <i class="bi bi-pause-circle-fill"></i> 
                            <strong>Inactive</strong><br>
                            <small>${data.image_count} wallpapers available in ${data.wallpapers_dir}/</small>
                        </div>
                    `;
                    startBtn.style.display = 'block';
                } else {
                    statusHtml = `
                        <div class="alert alert-warning mb-0">
                            <i class="bi bi-exclamation-triangle-fill"></i> 
                            <strong>No wallpapers found</strong><br>
                            <small>Add images to ${data.wallpapers_dir}/ directory</small>
                        </div>
                    `;
                    startBtn.style.display = 'none';
                }
                stopBtn.style.display = 'none';
                
                // Stop monitoring when screensaver is not active
                stopScreensaverMonitoring();
            }
            
            statusDiv.innerHTML = statusHtml;
            
            // Update interval input with current value
            if (intervalInput) {
                intervalInput.value = data.interval;
            }
        })
        .catch(error => {
            console.error('Error loading screensaver status:', error);
            statusDiv.innerHTML = '<div class="alert alert-danger mb-0">Failed to load screensaver status</div>';
        });
}

function startScreensaver() {
    const startBtn = document.getElementById('start-screensaver');
    if (!startBtn) return;
    
    // Show loading state
    const originalText = startBtn.innerHTML;
    startBtn.disabled = true;
    startBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Starting...';
    
    fetch('/screensaver/start', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert(data.message, 'success');
            loadScreensaverStatus(); // Refresh status
        } else {
            showAlert(data.error || 'Failed to start screensaver', 'danger');
        }
    })
    .catch(error => {
        console.error('Error starting screensaver:', error);
        showAlert('Failed to start screensaver', 'danger');
    })
    .finally(() => {
        // Restore button state
        startBtn.disabled = false;
        startBtn.innerHTML = originalText;
    });
}

function stopScreensaver() {
    const stopBtn = document.getElementById('stop-screensaver');
    if (!stopBtn) return;
    
    // Show loading state
    const originalText = stopBtn.innerHTML;
    stopBtn.disabled = true;
    stopBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Stopping...';
    
    fetch('/screensaver/stop', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert(data.message, 'success');
            loadScreensaverStatus(); // Refresh status
        } else {
            showAlert(data.error || 'Failed to stop screensaver', 'danger');
        }
    })
    .catch(error => {
        console.error('Error stopping screensaver:', error);
        showAlert('Failed to stop screensaver', 'danger');
    })
    .finally(() => {
        // Restore button state
        stopBtn.disabled = false;
        stopBtn.innerHTML = originalText;
    });
}

function updateScreensaverInterval() {
    const intervalInput = document.getElementById('interval-input');
    const updateBtn = document.getElementById('update-interval');
    
    if (!intervalInput || !updateBtn) return;
    
    const newInterval = parseInt(intervalInput.value);
    if (isNaN(newInterval) || newInterval < 5 || newInterval > 3600) {
        showAlert('Interval must be between 5 and 3600 seconds', 'danger');
        return;
    }
    
    // Show loading state
    const originalText = updateBtn.innerHTML;
    updateBtn.disabled = true;
    updateBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>';
    
    fetch('/screensaver/config', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            interval: newInterval
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert(data.message, 'success');
            if (data.restarted) {
                showAlert('Screensaver was restarted with new interval', 'info');
            }
            loadScreensaverStatus(); // Refresh status
        } else {
            showAlert(data.error || 'Failed to update interval', 'danger');
        }
    })
    .catch(error => {
        console.error('Error updating interval:', error);
        showAlert('Failed to update interval', 'danger');
    })
    .finally(() => {
        // Restore button state
        updateBtn.disabled = false;
        updateBtn.innerHTML = originalText;
    });
}

function startScreensaverMonitoring(interval) {
    // Stop any existing monitoring
    stopScreensaverMonitoring();
    
    // Refresh layout immediately
    refreshLayout();
    
    // Set up interval to refresh layout every 10 seconds
    // This polls more frequently than the screensaver changes (30s)
    layoutRefreshInterval = setInterval(function() {
        refreshLayout();
    }, 10000);
    
    // Also check screensaver status every 10 seconds to detect if it stops
    screensaverCheckInterval = setInterval(function() {
        loadScreensaverStatus();
    }, 10000);
    
    console.log(`Started screensaver monitoring - refreshing layout every 10 seconds`);
}

function stopScreensaverMonitoring() {
    if (layoutRefreshInterval) {
        clearInterval(layoutRefreshInterval);
        layoutRefreshInterval = null;
    }
    
    if (screensaverCheckInterval) {
        clearInterval(screensaverCheckInterval);
        screensaverCheckInterval = null;
    }
    
    console.log('Stopped screensaver monitoring');
}

// Auto-dismiss alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert-dismissible');
        alerts.forEach(alert => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
});