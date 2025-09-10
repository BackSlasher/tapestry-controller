// Digink Web UI JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Load device information on page load
    loadDeviceInfo();
    
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