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

    // Screensaver overlay buttons
    const disableScreensaverBtn = document.getElementById('disable-screensaver');
    if (disableScreensaverBtn) {
        disableScreensaverBtn.addEventListener('click', function() {
            stopScreensaverFromOverlay();
        });
    }

    const nextImageBtn = document.getElementById('next-image-home');
    if (nextImageBtn) {
        nextImageBtn.addEventListener('click', function() {
            nextScreensaverImageFromHome();
        });
    }

    // Handle window resize to redraw canvas with new dimensions
    let resizeTimeout;
    window.addEventListener('resize', function() {
        // Debounce resize events
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(function() {
            refreshLayout();
        }, 250);
    });
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

// Cache ETags to detect changes
let lastLayoutETag = null;
let lastImageETag = null;

function updateDeviceCount(layoutData) {
    const deviceCountSpan = document.getElementById('device-count');
    if (deviceCountSpan && layoutData.screens) {
        deviceCountSpan.textContent = layoutData.screens.length;
    }
}

async function refreshLayout() {
    const canvas = document.getElementById('layout-canvas');
    if (!canvas) return;

    try {
        // Fetch both endpoints in parallel
        const [layoutResponse, imageResponse] = await Promise.all([
            fetch('/layout-data'),
            fetch('/current-image')
        ]);

        if (!layoutResponse.ok) {
            console.error(`Layout fetch failed: ${layoutResponse.status} ${layoutResponse.statusText}`);
            return;
        }
        if (!imageResponse.ok) {
            console.warn(`Image fetch failed: ${imageResponse.status} ${imageResponse.statusText}`);
            return;
        }

        const currentLayoutETag = layoutResponse.headers.get('etag');
        const currentImageETag = imageResponse.headers.get('etag');

        if (currentLayoutETag && currentLayoutETag === lastLayoutETag &&
            currentImageETag && currentImageETag === lastImageETag) {
            return;
        }

        [lastLayoutETag, lastImageETag]  = [currentLayoutETag, currentImageETag];

        const layoutData =  layoutResponse.status === 204 ? null : await layoutResponse.json();
        const imageBlob = imageResponse.status === 204 ? null : await imageResponse.blob();
        updateDeviceCount(layoutData);
        await drawCanvas(layoutData, imageBlob);

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

    // Handle case with no devices/screens
    if (!layoutData || !layoutData.screens || layoutData.screens.length === 0) {
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

    // Get the actual available space in the container
    const canvasContainer = canvas.parentElement;
    const containerRect = canvasContainer.getBoundingClientRect();

    // Use container width minus padding, with reasonable height limits
    const maxDisplayWidth = Math.max(400, containerRect.width - 40); // Min 400px, minus padding
    const maxDisplayHeight = Math.min(600, window.innerHeight * 0.6); // Max 60% of viewport height

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
                // Set canvas to exact image dimensions (no scaling needed since /current-image now returns processed source)
                canvas.width = img.width;
                canvas.height = img.height;

                // Clear canvas and draw background
                ctx.clearRect(0, 0, canvas.width, canvas.height);

                // Draw the image at 1:1 scale (exact match with processed source)
                ctx.drawImage(img, 0, 0);

                // Create a mask for screen areas
                const screenMask = document.createElement('canvas');
                screenMask.width = canvas.width;
                screenMask.height = canvas.height;
                const maskCtx = screenMask.getContext('2d');

                // Fill mask with white (faded areas)
                maskCtx.fillStyle = 'rgba(255, 255, 255, 0.7)';
                maskCtx.fillRect(0, 0, screenMask.width, screenMask.height);

                // Cut out screen areas (keep original image visible)
                maskCtx.globalCompositeOperation = 'destination-out';
                layoutData.screens.forEach(screen => {
                    maskCtx.fillStyle = 'rgba(0, 0, 0, 1)';
                    maskCtx.fillRect(screen.x, screen.y, screen.width, screen.height);
                });

                // Apply the mask to the main canvas
                ctx.drawImage(screenMask, 0, 0);

                // Draw screen overlays on top using exact pixel coordinates
                drawScreens(ctx, layoutData.screens, 1); // Scale factor is 1 since we're using exact dimensions

                URL.revokeObjectURL(img.src);
            };
            img.src = URL.createObjectURL(imageBlob);
        } catch (error) {
            console.error('Error loading background image:', error);
            // Fallback to original sizing logic if image load fails
            drawScreens(ctx, layoutData.screens, displayScale);
        }
    } else {
        // No image or error - use original sizing logic for screen borders
        drawScreens(ctx, layoutData.screens, displayScale);
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
        const fontSize = Math.max(28, 32 * displayScale);
        ctx.font = `${fontSize}px Arial`;
        ctx.textAlign = 'center';
        const textWidth = ctx.measureText(screen.hostname).width;
        const textHeight = fontSize;

        // White background for text
        ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
        ctx.fillRect(centerX - textWidth/2 - 4, centerY - textHeight/2 - 2, textWidth + 8, textHeight + 4);

        // Draw hostname text
        ctx.fillStyle = '#000';
        ctx.textBaseline = 'middle';
        ctx.fillText(screen.hostname, centerX, centerY);

        // Draw direction arrow (pointing to rotation = 0 direction)
        ctx.save();
        ctx.translate(centerX, centerY - 40);
        ctx.rotate((screen.rotation || 0) * Math.PI / 180);

        // White circle background for arrow
        ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
        ctx.beginPath();
        const arrowRadius = Math.max(16, 20 * displayScale);
        ctx.arc(0, 0, arrowRadius, 0, 2 * Math.PI);
        ctx.fill();

        // Arrow
        ctx.font = `${fontSize}px Arial`;
        ctx.fillStyle = '#000';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('↑', 0, 0);

        ctx.restore();
    });
}


async function clearAllScreens() {
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

    try {
        const response = await fetch('/clear', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (data.success) {
            showAlert('All screens cleared successfully', 'success');
            // Refresh layout after clearing
            setTimeout(refreshLayout, 1000);
        } else {
            showAlert('Error clearing screens: ' + (data.error || 'Unknown error'), 'danger');
        }
    } catch (error) {
        console.error('Error clearing screens:', error);
        showAlert('Failed to clear screens: ' + error.message, 'danger');
    } finally {
        // Reset button state
        clearBtn.disabled = false;
        clearBtn.innerHTML = originalText;
    }
}

async function restoreLastImage() {
    const restoreBtn = document.getElementById('restore-image');
    if (!restoreBtn) return;

    // Show loading state
    const originalText = restoreBtn.innerHTML;
    restoreBtn.disabled = true;
    restoreBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Restoring...';

    try {
        const response = await fetch('/restore-image', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (data.success) {
            showAlert('Last image restored successfully', 'success');
            // Refresh layout after restoring
            setTimeout(refreshLayout, 1000);
        } else {
            showAlert('Error restoring image: ' + (data.error || 'Unknown error'), 'danger');
        }
    } catch (error) {
        console.error('Error restoring image:', error);
        showAlert('Failed to restore image: ' + error.message, 'danger');
    } finally {
        // Reset button state
        restoreBtn.disabled = false;
        restoreBtn.innerHTML = originalText;
    }
}

async function checkScreensaverStatus() {
    const screensaverMessage = document.getElementById('screensaver-message');
    const uploadForm = document.getElementById('upload-form');
    if (!screensaverMessage || !uploadForm) return; // Not on main page

    try {
        const response = await fetch('/screensaver/status');

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (data.active) {
            screensaverMessage.classList.remove('d-none');
            uploadForm.classList.add('d-none');
        } else {
            screensaverMessage.classList.add('d-none');
            uploadForm.classList.remove('d-none');
        }
    } catch (error) {
        console.error('Error checking screensaver status:', error);
        // On error, hide screensaver message and show upload form
        screensaverMessage.classList.add('d-none');
        uploadForm.classList.remove('d-none');
    }
}

async function stopScreensaverFromOverlay() {
    const disableBtn = document.getElementById('disable-screensaver');
    if (!disableBtn) return;

    // Show loading state
    const originalText = disableBtn.innerHTML;
    disableBtn.disabled = true;
    disableBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Stopping...';

    try {
        const response = await fetch('/screensaver/stop', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (data.success) {
            showAlert('Screensaver stopped', 'success');
            checkScreensaverStatus(); // Update UI
        } else {
            showAlert('Error stopping screensaver: ' + (data.error || 'Unknown error'), 'danger');
        }
    } catch (error) {
        console.error('Error stopping screensaver:', error);
        showAlert('Failed to stop screensaver: ' + error.message, 'danger');
    } finally {
        // Reset button state
        disableBtn.disabled = false;
        disableBtn.innerHTML = originalText;
    }
}

async function nextScreensaverImageFromHome() {
    const nextBtn = document.getElementById('next-image-home');
    if (!nextBtn) return;

    // Show loading state
    const originalText = nextBtn.innerHTML;
    nextBtn.disabled = true;
    nextBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Loading...';

    try {
        const response = await fetch('/screensaver/next', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (data.success) {
            showAlert('Next image displayed successfully', 'success');
        } else {
            showAlert('Error displaying next image: ' + (data.error || 'Unknown error'), 'danger');
        }
    } catch (error) {
        console.error('Error displaying next image:', error);
        showAlert('Failed to display next image: ' + error.message, 'danger');
    } finally {
        // Reset button state
        nextBtn.disabled = false;
        nextBtn.innerHTML = originalText;
    }
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
