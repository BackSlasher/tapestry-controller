// Tapestry Web UI JavaScript

// Global variables
let layoutRefreshInterval = null;

document.addEventListener('DOMContentLoaded', function() {
    // Load device information on page load
    loadDeviceInfo();

    // Initialize canvas layout
    initializeCanvas();

    // Check screensaver status and update overlay
    checkScreensaverStatus();

    // Set up periodic screensaver status check and layout refresh
    schedulePeriodicUpdates();

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
    
    // Action buttons
    const clearScreensBtn = document.getElementById('clear-screens');
    const restoreImageBtn = document.getElementById('restore-image');
    
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

    // Screensaver overlay stop button
    const disableScreensaverBtn = document.getElementById('disable-screensaver');
    if (disableScreensaverBtn) {
        disableScreensaverBtn.addEventListener('click', function() {
            stopScreensaverFromOverlay();
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

async function refreshLayout() {
    // Check for changes using ETags and only redraw if necessary
    try {
        // Fetch layout data and image in parallel
        const [layoutResponse, imageResponse] = await Promise.all([
            fetch('/layout-data'),
            fetch('/current-image')
        ]);

        // Check if either response indicates changes (not 304)
        const layoutChanged = layoutResponse.status !== 304;
        const imageChanged = imageResponse.status !== 304;

        if (layoutChanged || imageChanged) {
            console.log('Canvas update needed:', { layoutChanged, imageChanged });

            // Get layout data (either from response if changed, or from cache)
            let layoutData;
            if (layoutChanged) {
                layoutData = await layoutResponse.json();
                // Cache the layout data for future use
                window.cachedLayoutData = layoutData;
            } else if (window.cachedLayoutData) {
                // Use cached layout data since it hasn't changed
                layoutData = window.cachedLayoutData;
            } else {
                // No cache available, need to fetch (this should rarely happen)
                const freshLayoutResponse = await fetch('/layout-data');
                layoutData = await freshLayoutResponse.json();
                window.cachedLayoutData = layoutData;
            }

            // Redraw the canvas with the layout data and image response
            await drawCanvas(layoutData, imageResponse);
        } else {
            console.log('No changes detected (both 304), skipping canvas redraw');
        }

    } catch (error) {
        console.error('Error checking for canvas updates:', error);
        // On error, force a redraw
        await drawLayoutCanvas();
    }
}

async function drawCanvas(layoutData, imageResponse) {
    const canvas = document.getElementById('layout-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Use the provided layout data instead of fetching
    const data = layoutData;

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

    // Check if we should use server-side rendering
    if (data.use_server_rendering) {
        drawServerSideLayout(canvas, ctx);
        return;
    }

    // Calculate canvas size and scaling (same logic as before)
    let canvasWidth, canvasHeight;
    if (data.image_size) {
        canvasWidth = data.image_size.width;
        canvasHeight = data.image_size.height;
    } else {
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        data.screens.forEach(screen => {
            minX = Math.min(minX, screen.x);
            minY = Math.min(minY, screen.y);
            maxX = Math.max(maxX, screen.x + screen.width);
            maxY = Math.max(maxY, screen.y + screen.height);
        });
        canvasWidth = maxX - minX;
        canvasHeight = maxY - minY;
    }

    const maxDisplayWidth = 800;
    const maxDisplayHeight = 600;
    const displayScale = Math.min(
        maxDisplayWidth / canvasWidth,
        maxDisplayHeight / canvasHeight,
        1
    );

    canvas.width = canvasWidth * displayScale;
    canvas.height = canvasHeight * displayScale;

    // Handle image loading using the provided response
    if (imageResponse.ok) {
        try {
            const blob = await imageResponse.blob();
            const img = new Image();

            img.onload = function() {
                const imgWidth = canvas.width;
                const imgHeight = canvas.height;

                ctx.globalAlpha = 0.5;
                ctx.drawImage(img, 0, 0, imgWidth, imgHeight);

                ctx.globalAlpha = 1.0;
                data.screens.forEach(screen => {
                    const x = screen.x * displayScale;
                    const y = screen.y * displayScale;
                    const width = screen.width * displayScale;
                    const height = screen.height * displayScale;

                    ctx.save();
                    ctx.rect(x, y, width, height);
                    ctx.clip();
                    ctx.drawImage(img, 0, 0, imgWidth, imgHeight);
                    ctx.restore();
                });

                drawScreens(ctx, data.screens, displayScale);
                URL.revokeObjectURL(img.src);
            };

            img.src = URL.createObjectURL(blob);
        } catch (error) {
            console.error('Error loading background image:', error);
            drawScreens(ctx, data.screens, displayScale);
        }
    } else {
        // No image or error - just draw screen borders
        drawScreens(ctx, data.screens, displayScale);
    }
}

async function drawLayoutCanvas() {
    const canvas = document.getElementById('layout-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Load layout data
    try {
        const response = await fetch('/layout-data');
        const data = await response.json();
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
            
            // Check if we should use server-side rendering
            if (data.use_server_rendering) {
                drawServerSideLayout(canvas, ctx);
                return;
            }
            
            // With the new coordinate system, coordinates are already in pixels
            // relative to the scaled image, so we can work directly with them
            
            // Determine canvas size based on image size if available, otherwise screen bounds
            let canvasWidth, canvasHeight;
            if (data.image_size) {
                // Use the scaled image dimensions directly
                canvasWidth = data.image_size.width;
                canvasHeight = data.image_size.height;
            } else {
                // Fallback: calculate from screen bounds
                let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
                data.screens.forEach(screen => {
                    minX = Math.min(minX, screen.x);
                    minY = Math.min(minY, screen.y);
                    maxX = Math.max(maxX, screen.x + screen.width);
                    maxY = Math.max(maxY, screen.y + screen.height);
                });
                canvasWidth = maxX - minX;
                canvasHeight = maxY - minY;
            }
            
            // Scale canvas to fit nicely in the UI while maintaining aspect ratio
            const maxDisplayWidth = 800;
            const maxDisplayHeight = 600;
            const displayScale = Math.min(
                maxDisplayWidth / canvasWidth,
                maxDisplayHeight / canvasHeight,
                1 // Don't scale up
            );
            
            canvas.width = canvasWidth * displayScale;
            canvas.height = canvasHeight * displayScale;
            
            // Try to fetch background image with proper ETag handling
            try {
                const response = await fetch('/current-image');

                if (response.ok) {
                    // Image available - convert to blob and display
                    const blob = await response.blob();
                    const img = new Image();

                    img.onload = function() {
                        // The scaled image fills the entire canvas
                        const imgWidth = canvas.width;
                        const imgHeight = canvas.height;

                        // Draw image at half opacity everywhere
                        ctx.globalAlpha = 0.5;
                        ctx.drawImage(img, 0, 0, imgWidth, imgHeight);

                        // Draw image at full opacity only in screen areas
                        ctx.globalAlpha = 1.0;
                        data.screens.forEach(screen => {
                            // Scale screen coordinates to match canvas display size
                            const x = screen.x * displayScale;
                            const y = screen.y * displayScale;
                            const width = screen.width * displayScale;
                            const height = screen.height * displayScale;

                            // Create a clipping region for this screen
                            ctx.save();
                            ctx.rect(x, y, width, height);
                            ctx.clip();

                            // Draw the full-opacity image within the clipped region
                            ctx.drawImage(img, 0, 0, imgWidth, imgHeight);

                            ctx.restore();
                        });

                        // Draw screen borders, labels and arrows on top
                        drawScreens(ctx, data.screens, displayScale);

                        // Clean up blob URL
                        URL.revokeObjectURL(img.src);
                    };

                    img.src = URL.createObjectURL(blob);
                } else if (response.status === 204) {
                    // No image available - just draw screen borders
                    drawScreens(ctx, data.screens, displayScale);
                } else {
                    // Error - just draw screen borders
                    drawScreens(ctx, data.screens, displayScale);
                }
            } catch (error) {
                console.error('Error loading background image:', error);
                // Error - just draw screen borders
                drawScreens(ctx, data.screens, displayScale);
            }
    } catch (error) {
        console.error('Error loading layout data:', error);
        canvas.width = 400;
        canvas.height = 300;
        ctx.fillStyle = '#f8f9fa';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#dc3545';
        ctx.font = '16px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Error loading layout', canvas.width/2, canvas.height/2);
    }
}

function drawServerSideLayout(canvas, ctx) {
    // Load server-side rendered image and display it
    const img = new Image();
    img.onload = function() {
        canvas.width = img.width;
        canvas.height = img.height;
        ctx.drawImage(img, 0, 0);
    };
    img.onerror = function() {
        // Fallback to error message
        canvas.width = 400;
        canvas.height = 300;
        ctx.fillStyle = '#f8f9fa';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#dc3545';
        ctx.font = '16px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Error loading server-side layout', canvas.width/2, canvas.height/2);
    };
    img.src = '/layout-image';
}

function drawScreens(ctx, screens, displayScale) {
    screens.forEach(screen => {
        // Scale screen coordinates to match canvas display size
        const x = screen.x * displayScale;
        const y = screen.y * displayScale;
        const width = screen.width * displayScale;
        const height = screen.height * displayScale;
        
        // Always draw black border around screen area
        ctx.globalAlpha = 1.0;
        ctx.strokeStyle = '#000';
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, width, height);
        
        const centerX = x + width / 2;
        const centerY = y + height / 2;
        
        // Draw hostname (IP address) with white background for visibility
        const fontSize = Math.max(10, 12 * displayScale);
        ctx.font = `${fontSize}px Arial`;
        ctx.textAlign = 'center';
        const textWidth = ctx.measureText(screen.hostname).width;
        const textHeight = fontSize;
        
        // White background for text
        ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
        ctx.fillRect(centerX - textWidth/2 - 4, centerY + 8 - textHeight, textWidth + 8, textHeight + 4);
        
        // Black text
        ctx.fillStyle = '#000';
        ctx.fillText(screen.hostname, centerX, centerY + 8);
        
        // Draw rotation arrow pointing to top of screen
        ctx.save();
        ctx.translate(centerX, centerY - 15);
        ctx.rotate((screen.rotation * Math.PI) / 180);
        
        // White circle background for arrow
        ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
        ctx.beginPath();
        const arrowRadius = Math.max(8, 10 * displayScale);
        ctx.arc(0, 0, arrowRadius, 0, 2 * Math.PI);
        ctx.fill();
        
        // Arrow
        const arrowFontSize = Math.max(12, 14 * displayScale);
        ctx.font = `${arrowFontSize}px Arial`;
        ctx.fillStyle = '#000';
        ctx.textAlign = 'center';
        ctx.fillText('🔼', 0, 4); // Slight offset to center vertically
        ctx.restore();
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
                if (data.screens && data.screens.length > 0 && data.image_size) {
                    const screens = data.screens;
                    
                    // Calculate scale to match the preview canvas size to the actual image layout
                    const imageAspectRatio = data.image_size.width / data.image_size.height;
                    const canvasAspectRatio = canvasWidth / canvasHeight;
                    
                    let scale, offsetX = 0, offsetY = 0;
                    
                    if (imageAspectRatio > canvasAspectRatio) {
                        // Image is wider - fit to canvas width
                        scale = canvasWidth / data.image_size.width;
                        offsetY = (canvasHeight - data.image_size.height * scale) / 2;
                    } else {
                        // Image is taller - fit to canvas height
                        scale = canvasHeight / data.image_size.height;
                        offsetX = (canvasWidth - data.image_size.width * scale) / 2;
                    }
                    
                    // Draw screen rectangles using direct pixel coordinates
                    screens.forEach(screen => {
                        const x = screen.x * scale + offsetX;
                        const y = screen.y * scale + offsetY;
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

async function schedulePeriodicUpdates() {
    try {
        // Run both updates and wait for completion
        await Promise.all([
            checkScreensaverStatus(),
            refreshLayout()
        ]);
    } catch (error) {
        console.error('Error during periodic update:', error);
    }

    // Schedule next update only after current one finishes
    setTimeout(schedulePeriodicUpdates, 5000);
}






function checkScreensaverStatus() {
    const screensaverMessage = document.getElementById('screensaver-message');
    const uploadForm = document.getElementById('upload-form');
    if (!screensaverMessage || !uploadForm) return; // Not on main page

    fetch('/screensaver/status')
        .then(response => response.json())
        .then(data => {
            if (data.active) {
                screensaverMessage.classList.remove('d-none');
                uploadForm.classList.add('d-none');
            } else {
                screensaverMessage.classList.add('d-none');
                uploadForm.classList.remove('d-none');
            }
        })
        .catch(error => {
            console.error('Error checking screensaver status:', error);
            // Show upload form on error
            screensaverMessage.classList.add('d-none');
            uploadForm.classList.remove('d-none');
        });
}

function stopScreensaverFromOverlay() {
    const disableBtn = document.getElementById('disable-screensaver');
    if (!disableBtn) return;

    // Show loading state
    const originalText = disableBtn.innerHTML;
    disableBtn.disabled = true;
    disableBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Stopping...';

    fetch('/screensaver/stop', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Screensaver stopped successfully', 'success');
            // Update UI to show upload form
            checkScreensaverStatus();
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
        disableBtn.disabled = false;
        disableBtn.innerHTML = originalText;
    });
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