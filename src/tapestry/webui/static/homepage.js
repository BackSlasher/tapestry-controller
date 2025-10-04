// Homepage-specific JavaScript for Tapestry Web UI

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

async function loadDeviceInfo() {
    try {
        const response = await fetch('/devices');

        const data = await response.json();
        const deviceInfoDiv = document.getElementById('device-info');
        const deviceCountSpan = document.getElementById('device-count');

        if (data.devices) {
            const screens = data.devices
            // Update device count
            if (deviceCountSpan) {
                deviceCountSpan.textContent = screens.length;
            }

            // Update device info section
            if (deviceInfoDiv) {
                if (screens.length === 0) {
                    deviceInfoDiv.innerHTML = '<p class="text-muted">No devices configured. Use QR Positioning to discover devices.</p>';
                } else {
                    let deviceHtml = '<div class="row">';
                    screens.forEach(screen => {
                        const hostname = screen.host || 'Unknown';
                        const screenType = screen.screen_type || 'Unknown';
                        const x = screen.coordinates.x ?? 'Unknown';
                        const y = screen.coordinates.y ?? 'Unknown';
                        const width = screen.dimensions.width ?? 'Unknown';
                        const height = screen.dimensions.height ?? 'Unknown';
                        const rotation = screen.rotation ?? 'Unknown';

                        deviceHtml += `
                            <div class="col-md-6 mb-3">
                                <div class="card">
                                    <div class="card-body">
                                        <h6 class="card-title">${hostname}</h6>
                                        <p class="card-text">
                                            <small class="text-muted">
                                                Type: ${screenType}<br>
                                                Position: (${x}, ${y})<br>
                                                Size: ${width}×${height}<br>
                                                Rotation: ${rotation}°
                                            </small>
                                        </p>
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                    deviceHtml += '</div>';
                    deviceInfoDiv.innerHTML = deviceHtml;
                }
            }
        } else {
            const deviceInfoDiv = document.getElementById('device-info');
            if (deviceInfoDiv) {
                deviceInfoDiv.innerHTML = '<p class="text-muted">No device data available.</p>';
            }
        }
    } catch (error) {
        console.error('Error loading device info:', error);
        const deviceInfoDiv = document.getElementById('device-info');
        if (deviceInfoDiv) {
            deviceInfoDiv.innerHTML = '<div class="alert alert-danger">Error loading device information</div>';
        }
    }
}

function initializeCanvas() {
    const canvas = document.getElementById('layout-canvas');
    if (!canvas) return;

    // Initial canvas load
    refreshLayout();
}

async function refreshLayout() {
    const canvas = document.getElementById('layout-canvas');
    if (!canvas) return;

    try {
        // Fetch layout data
        const layoutResponse = await fetch('/layout-data');

        if (layoutResponse.status === 204) {
            // No content
            const ctx = canvas.getContext('2d');
            canvas.width = 400;
            canvas.height = 300;
            ctx.fillStyle = '#f8f9fa';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#6c757d';
            ctx.font = '16px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('No devices configured', canvas.width / 2, canvas.height / 2);
            return;
        }

        const layoutData = await layoutResponse.json();
        const deviceCountSpan = document.getElementById('device-count');
        if (deviceCountSpan && layoutData.screens) {
            deviceCountSpan.textContent = layoutData.screens.length;
        }

        // Try to fetch current image
        const imageResponse = await fetch('/current-image');

        if (imageResponse.ok && imageResponse.status !== 204) {
            const imageBlob = await imageResponse.blob();
            await drawCanvas(layoutData, imageBlob);
        } else {
            await drawLayoutCanvas();
        }

    } catch (error) {
        console.error('Error refreshing layout:', error);
        const canvas = document.getElementById('layout-canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = 400;
        canvas.height = 300;
        ctx.fillStyle = '#f8f9fa';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#dc3545';
        ctx.font = '16px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Error loading layout', canvas.width / 2, canvas.height / 2);
    }
}

async function drawCanvas(layoutData, imageBlob) {
    const canvas = document.getElementById('layout-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Calculate canvas size based on layout data
    let canvasWidth, canvasHeight;
    if (layoutData.image_size) {
        canvasWidth = layoutData.image_size.width;
        canvasHeight = layoutData.image_size.height;
    } else {
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        layoutData.screens.forEach(screen => {
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

    // Handle image loading using the provided blob
    if (imageBlob) {
        try {
            const img = new Image();
            img.onload = function() {
                // Clear canvas and draw background
                ctx.clearRect(0, 0, canvas.width, canvas.height);

                // Calculate scaling to fit canvas while maintaining aspect ratio
                const scale = Math.min(canvas.width / img.width, canvas.height / img.height);
                const scaledWidth = img.width * scale;
                const scaledHeight = img.height * scale;

                // Center the image
                const x = (canvas.width - scaledWidth) / 2;
                const y = (canvas.height - scaledHeight) / 2;

                // Draw the image
                ctx.drawImage(img, x, y, scaledWidth, scaledHeight);

                // Draw screen overlays on top
                drawScreens(ctx, layoutData.screens, displayScale);

                URL.revokeObjectURL(img.src);
            };
            img.src = URL.createObjectURL(imageBlob);
        } catch (error) {
            console.error('Error loading background image:', error);
            drawScreens(ctx, layoutData.screens, displayScale);
        }
    } else {
        // No image or error - just draw screen borders
        drawScreens(ctx, layoutData.screens, displayScale);
    }
}

async function drawLayoutCanvas() {
    const canvas = document.getElementById('layout-canvas');
    if (!canvas) return;

    try {
        const response = await fetch('/layout-data');

        if (response.status === 204) {
            // No content
            const ctx = canvas.getContext('2d');
            canvas.width = 400;
            canvas.height = 300;
            ctx.fillStyle = '#f8f9fa';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#6c757d';
            ctx.font = '16px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('No devices configured', canvas.width / 2, canvas.height / 2);
            return;
        }

        const data = await response.json();

        if (!data.screens || data.screens.length === 0) {
            // No screens, show placeholder
            const ctx = canvas.getContext('2d');
            canvas.width = 400;
            canvas.height = 300;
            ctx.fillStyle = '#f8f9fa';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#6c757d';
            ctx.font = '16px Arial';
            ctx.textAlign = 'center';
            ctx.fillText('No devices configured', canvas.width / 2, canvas.height / 2);

            const deviceCountSpan = document.getElementById('device-count');
            if (deviceCountSpan) {
                deviceCountSpan.textContent = '0';
            }
            return;
        }

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

        // Update device count
        const deviceCountSpan = document.getElementById('device-count');
        if (deviceCountSpan) {
            deviceCountSpan.textContent = data.screens.length;
        }

        // Try to fetch background image with proper ETag handling
        try {
            const imageResponse = await fetch('/current-image');
            if (imageResponse.ok && imageResponse.status !== 204) {
                const blob = await imageResponse.blob();
                const img = new Image();
                img.onload = function() {
                    const ctx = canvas.getContext('2d');
                    // Clear canvas and set white background
                    ctx.fillStyle = '#ffffff';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);

                    // Calculate image scaling and positioning
                    const imageAspectRatio = img.width / img.height;
                    const canvasAspectRatio = canvas.width / canvas.height;

                    let scale, offsetX = 0, offsetY = 0;

                    if (imageAspectRatio > canvasAspectRatio) {
                        // Image is wider - fit to canvas width
                        scale = canvas.width / img.width;
                        offsetY = (canvas.height - img.height * scale) / 2;
                    } else {
                        // Image is taller - fit to canvas height
                        scale = canvas.height / img.height;
                        offsetX = (canvas.width - img.width * scale) / 2;
                    }

                    // Draw the background image
                    ctx.drawImage(img, offsetX, offsetY, img.width * scale, img.height * scale);

                    // Draw screen overlays with transparency
                    ctx.globalAlpha = 0.8;
                    data.screens.forEach(screen => {
                        const x = screen.x * displayScale;
                        const y = screen.y * displayScale;
                        const width = screen.width * displayScale;
                        const height = screen.height * displayScale;

                        // Create a clipping region for this screen
                        ctx.save();
                        ctx.rect(x, y, width, height);
                        ctx.clip();

                        // Fill with semi-transparent white to show screen bounds
                        ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
                        ctx.fillRect(x, y, width, height);

                        ctx.restore();
                    });

                    // Reset alpha and draw screen borders, labels and arrows on top
                    ctx.globalAlpha = 1.0;
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
        const ctx = canvas.getContext('2d');
        canvas.width = 400;
        canvas.height = 300;
        ctx.fillStyle = '#f8f9fa';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#dc3545';
        ctx.font = '16px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Error loading layout', canvas.width / 2, canvas.height / 2);
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
        ctx.fillText('Error loading layout image', canvas.width / 2, canvas.height / 2);
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
        ctx.strokeStyle = '#000000';
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, width, height);

        // Calculate center coordinates for text and arrow
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
        ctx.fillRect(centerX - textWidth/2 - 4, centerY - textHeight/2 - 2, textWidth + 8, textHeight + 4);

        // Draw hostname text
        ctx.fillStyle = '#000';
        ctx.fillText(screen.hostname, centerX, centerY + 3);

        // Draw direction arrow (pointing to rotation = 0 direction)
        ctx.save();
        ctx.translate(centerX, centerY - 20);
        ctx.rotate((screen.rotation || 0) * Math.PI / 180);

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
        ctx.fillText('↑', 0, arrowFontSize/3);

        ctx.restore();
    });
}

function drawPreviewCanvas(imageSrc) {
    const canvas = document.getElementById('preview-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const img = new Image();

    img.onload = function() {
        // Set canvas size
        const maxWidth = 400;
        const maxHeight = 300;

        let { width, height } = img;

        // Scale down if too large
        if (width > maxWidth || height > maxHeight) {
            const scale = Math.min(maxWidth / width, maxHeight / height);
            width *= scale;
            height *= scale;
        }

        canvas.width = width;
        canvas.height = height;

        // Draw image
        ctx.clearRect(0, 0, width, height);
        ctx.drawImage(img, 0, 0, width, height);

        // Fetch and overlay screen positions
        fetch('/layout-data')
            .then(response => {
                if (response.status === 204) return null;
                return response.json();
            })
            .then(data => {
                if (!data || !data.screens) return;

                // Calculate scale factor from original image to canvas
                const scaleX = width / img.naturalWidth;
                const scaleY = height / img.naturalHeight;

                // Draw screen overlays
                data.screens.forEach(screen => {
                    const x = screen.x * scaleX;
                    const y = screen.y * scaleY;
                    const w = screen.width * scaleX;
                    const h = screen.height * scaleY;

                    // Draw outline
                    ctx.strokeStyle = '#ff6b6b';
                    ctx.lineWidth = 2;
                    ctx.strokeRect(x, y, w, h);

                    // Draw label background
                    ctx.fillStyle = 'rgba(255, 107, 107, 0.8)';
                    ctx.fillRect(x, y - 20, w, 20);

                    // Draw label text
                    ctx.fillStyle = 'white';
                    ctx.font = '12px Arial';
                    ctx.textAlign = 'center';
                    ctx.fillText(screen.label, x + w/2, y - 6);
                });
            })
            .catch(error => {
                console.error('Error loading screen layout for preview:', error);
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

    fetch('/clear-all-screens', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('All screens cleared successfully', 'success');
            // Refresh layout after clearing
            setTimeout(refreshLayout, 1000);
        } else {
            showAlert('Error clearing screens: ' + (data.error || 'Unknown error'), 'danger');
        }
    })
    .catch(error => {
        console.error('Error clearing screens:', error);
        showAlert('Failed to clear screens: ' + error.message, 'danger');
    })
    .finally(() => {
        // Reset button state
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

    fetch('/restore-last-image', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Last image restored successfully', 'success');
            // Refresh layout after restoring
            setTimeout(refreshLayout, 1000);
        } else {
            showAlert('Error restoring image: ' + (data.error || 'Unknown error'), 'danger');
        }
    })
    .catch(error => {
        console.error('Error restoring image:', error);
        showAlert('Failed to restore image: ' + error.message, 'danger');
    })
    .finally(() => {
        // Reset button state
        restoreBtn.disabled = false;
        restoreBtn.innerHTML = originalText;
    });
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
            // On error, hide screensaver message and show upload form
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
    disableBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Stopping...';

    fetch('/screensaver/stop', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Screensaver stopped', 'success');
            checkScreensaverStatus(); // Update UI
        } else {
            showAlert('Error stopping screensaver: ' + (data.error || 'Unknown error'), 'danger');
        }
    })
    .catch(error => {
        console.error('Error stopping screensaver:', error);
        showAlert('Failed to stop screensaver: ' + error.message, 'danger');
    })
    .finally(() => {
        // Reset button state
        disableBtn.disabled = false;
        disableBtn.innerHTML = originalText;
    });
}

async function schedulePeriodicUpdates() {
    try {
        // Run both updates and wait for completion
        await Promise.all([
            checkScreensaverStatus(),
            refreshLayout()
        ]);
    } catch (error) {
        console.error('Error in periodic updates:', error);
    }

    // Schedule next update only after current one finishes
    setTimeout(schedulePeriodicUpdates, 5000);
}
