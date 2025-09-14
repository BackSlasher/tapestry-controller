// Digink Web UI JavaScript

// Global variables for screensaver monitoring
let screensaverCheckInterval = null;
let layoutRefreshInterval = null;

document.addEventListener('DOMContentLoaded', function() {
    // Load device information and screensaver status on page load
    loadDeviceInfo();
    loadScreensaverStatus();
    
    // Initialize canvas layout
    initializeCanvas();
    
    // Image preview functionality
    const imageInput = document.getElementById('image-input');
    const imagePreview = document.getElementById('image-preview');
    const previewCanvas = document.getElementById('preview-canvas');
    
    if (imageInput) {
        imageInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    drawPreviewCanvas(e.target.result);
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
    const restoreImageBtn = document.getElementById('restore-image');
    
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
    
    if (restoreImageBtn) {
        restoreImageBtn.addEventListener('click', function() {
            restoreLastImage();
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
                            Screen: ${device.screen_type} (${device.dimensions.width.toFixed(1)} × ${device.dimensions.height.toFixed(1)} mm)<br>
                            Position: (${device.coordinates.x}, ${device.coordinates.y})<br>
                            Rotation: ${device.rotation}°
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

function initializeCanvas() {
    // Initialize canvas and load layout data
    drawLayoutCanvas();
}

function refreshLayout() {
    // Refresh the canvas layout
    drawLayoutCanvas();
}

function drawLayoutCanvas() {
    const canvas = document.getElementById('layout-canvas');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    
    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Load layout data
    fetch('/layout-data')
        .then(response => response.json())
        .then(data => {
            // Update device count
            const deviceCountSpan = document.getElementById('device-count');
            if (deviceCountSpan) {
                deviceCountSpan.textContent = data.screens.length;
            }
            
            if (data.screens.length === 0) {
                // No screens, show placeholder
                canvas.width = 400;
                canvas.height = 300;
                ctx.fillStyle = '#f8f9fa';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = '#6c757d';
                ctx.font = '16px Arial';
                ctx.textAlign = 'center';
                ctx.fillText('No devices configured', canvas.width/2, canvas.height/2);
                return;
            }
            
            // Calculate canvas dimensions based on screen layout
            let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
            data.screens.forEach(screen => {
                minX = Math.min(minX, screen.x);
                minY = Math.min(minY, screen.y);
                maxX = Math.max(maxX, screen.x + screen.width);
                maxY = Math.max(maxY, screen.y + screen.height);
            });
            
            const layoutWidth = maxX - minX;
            const layoutHeight = maxY - minY;
            const padding = 40;
            
            // Scale to fit canvas nicely
            const maxCanvasWidth = 800;
            const maxCanvasHeight = 600;
            const scaleX = (maxCanvasWidth - padding * 2) / layoutWidth;
            const scaleY = (maxCanvasHeight - padding * 2) / layoutHeight;
            const scale = Math.min(scaleX, scaleY, 1); // Don't scale up
            
            canvas.width = layoutWidth * scale + padding * 2;
            canvas.height = layoutHeight * scale + padding * 2;
            
            // Draw background image if available
            if (data.current_image && data.image_size) {
                const img = new Image();
                img.onload = function() {
                    // Calculate image position and size to fit in layout
                    const imgScale = Math.min(
                        (layoutWidth * scale) / data.image_size.width,
                        (layoutHeight * scale) / data.image_size.height
                    );
                    const imgWidth = data.image_size.width * imgScale;
                    const imgHeight = data.image_size.height * imgScale;
                    const imgX = (canvas.width - imgWidth) / 2;
                    const imgY = (canvas.height - imgHeight) / 2;
                    
                    // Draw image with low opacity
                    ctx.globalAlpha = 0.3;
                    ctx.drawImage(img, imgX, imgY, imgWidth, imgHeight);
                    ctx.globalAlpha = 1.0;
                    
                    // Draw screens on top
                    drawScreens(ctx, data.screens, minX, minY, scale, padding);
                };
                img.src = data.current_image;
            } else {
                // No image, just draw screens
                drawScreens(ctx, data.screens, minX, minY, scale, padding);
            }
        })
        .catch(error => {
            console.error('Error loading layout data:', error);
            canvas.width = 400;
            canvas.height = 300;
            ctx.fillStyle = '#f8f9fa';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#dc3545';
            ctx.font = '16px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('Error loading layout', canvas.width/2, canvas.height/2);
        });
}

function drawScreens(ctx, screens, offsetX, offsetY, scale, padding) {
    screens.forEach(screen => {
        const x = (screen.x - offsetX) * scale + padding;
        const y = (screen.y - offsetY) * scale + padding;
        const width = screen.width * scale;
        const height = screen.height * scale;
        
        // Draw screen rectangle with blue fill and border
        ctx.fillStyle = 'rgba(13, 110, 253, 0.3)'; // Bootstrap primary with opacity
        ctx.fillRect(x, y, width, height);
        
        ctx.strokeStyle = '#0d6efd';
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, width, height);
        
        // Draw screen label
        ctx.fillStyle = '#000';
        ctx.font = `${Math.max(10, 12 * scale)}px Arial`;
        ctx.textAlign = 'center';
        
        const centerX = x + width / 2;
        const centerY = y + height / 2;
        
        // Draw hostname
        ctx.fillText(screen.hostname, centerX, centerY - 5);
        
        // Draw screen type and rotation
        ctx.font = `${Math.max(8, 10 * scale)}px Arial`;
        ctx.fillStyle = '#666';
        ctx.fillText(`${screen.screen_type}`, centerX, centerY + 8);
        
        if (screen.rotation !== 0) {
            ctx.fillText(`${screen.rotation}°`, centerX, centerY + 20);
        }
    });
}

function drawPreviewCanvas(imageSrc) {
    const canvas = document.getElementById('preview-canvas');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const img = new Image();
    
    img.onload = function() {
        // Set canvas size to maintain aspect ratio with max height of 200px
        const maxHeight = 200;
        const aspectRatio = img.width / img.height;
        
        let canvasWidth, canvasHeight;
        if (img.height > maxHeight) {
            canvasHeight = maxHeight;
            canvasWidth = maxHeight * aspectRatio;
        } else {
            canvasWidth = img.width;
            canvasHeight = img.height;
        }
        
        canvas.width = canvasWidth;
        canvas.height = canvasHeight;
        
        // Clear canvas
        ctx.clearRect(0, 0, canvasWidth, canvasHeight);
        
        // Draw the preview image
        ctx.drawImage(img, 0, 0, canvasWidth, canvasHeight);
        
        // Fetch layout data and draw screen overlays
        fetch('/layout-data')
            .then(response => response.json())
            .then(data => {
                if (data.screens && data.screens.length > 0) {
                    // Calculate scale and offsets to match the image
                    const screens = data.screens;
                    
                    // Find bounding box of all screens
                    const minX = Math.min(...screens.map(s => s.x));
                    const minY = Math.min(...screens.map(s => s.y));
                    const maxX = Math.max(...screens.map(s => s.x + s.width));
                    const maxY = Math.max(...screens.map(s => s.y + s.height));
                    
                    const layoutWidth = maxX - minX;
                    const layoutHeight = maxY - minY;
                    
                    // Calculate scale to fit preview canvas
                    const scaleX = canvasWidth / layoutWidth;
                    const scaleY = canvasHeight / layoutHeight;
                    const scale = Math.min(scaleX, scaleY);
                    
                    // Calculate offset to center the layout
                    const offsetX = (canvasWidth - layoutWidth * scale) / 2;
                    const offsetY = (canvasHeight - layoutHeight * scale) / 2;
                    
                    // Draw screen rectangles
                    screens.forEach(screen => {
                        const x = (screen.x - minX) * scale + offsetX;
                        const y = (screen.y - minY) * scale + offsetY;
                        const width = screen.width * scale;
                        const height = screen.height * scale;
                        
                        // Draw screen rectangle with blue border
                        ctx.strokeStyle = '#0d6efd';
                        ctx.lineWidth = 2;
                        ctx.strokeRect(x, y, width, height);
                        
                        // Draw screen rectangle with semi-transparent blue fill
                        ctx.fillStyle = 'rgba(13, 110, 253, 0.2)';
                        ctx.fillRect(x, y, width, height);
                    });
                }
            })
            .catch(error => {
                console.log('Could not load layout data for preview:', error);
                // Preview will just show the image without screen overlays
            });
    };
    
    img.src = imageSrc;
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

function restoreLastImage() {
    const restoreBtn = document.getElementById('restore-image');
    if (!restoreBtn) return;
    
    // Show loading state
    const originalText = restoreBtn.innerHTML;
    restoreBtn.disabled = true;
    restoreBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Restoring...';
    
    fetch('/restore-image', {
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
            
            // Refresh layout to show the restored image
            refreshLayout();
        } else {
            // Show error message
            showAlert(data.error || 'Failed to restore image', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showAlert('Failed to restore image: ' + error.message, 'danger');
    })
    .finally(() => {
        // Restore button state
        restoreBtn.disabled = false;
        restoreBtn.innerHTML = originalText;
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