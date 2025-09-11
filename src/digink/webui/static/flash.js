// Flash Firmware JavaScript

let currentProcessId = null;
let outputStream = null;

document.addEventListener('DOMContentLoaded', function() {
    const screenTypeSelect = document.getElementById('screen-type-select');
    const flashBtn = document.getElementById('flash-btn');
    const stopBtn = document.getElementById('stop-btn');
    const clearOutputBtn = document.getElementById('clear-output');
    const copyOutputBtn = document.getElementById('copy-output');
    const outputTextarea = document.getElementById('output-textarea');
    const flashStatus = document.getElementById('flash-status');
    const statusText = document.getElementById('status-text');
    
    // Enable flash button when screen type is selected
    if (screenTypeSelect) {
        screenTypeSelect.addEventListener('change', function() {
            flashBtn.disabled = !this.value;
        });
    }
    
    // Flash button handler
    if (flashBtn) {
        flashBtn.addEventListener('click', function() {
            const screenType = screenTypeSelect.value;
            if (!screenType) {
                showAlert('Please select a screen type', 'warning');
                return;
            }
            startFlashProcess(screenType);
        });
    }
    
    // Stop button handler
    if (stopBtn) {
        stopBtn.addEventListener('click', function() {
            stopFlashProcess();
        });
    }
    
    // Clear output button
    if (clearOutputBtn) {
        clearOutputBtn.addEventListener('click', function() {
            outputTextarea.value = '';
        });
    }
    
    // Copy output button
    if (copyOutputBtn) {
        copyOutputBtn.addEventListener('click', function() {
            outputTextarea.select();
            document.execCommand('copy');
            showAlert('Output copied to clipboard', 'success');
        });
    }
});

function startFlashProcess(screenType) {
    const flashBtn = document.getElementById('flash-btn');
    const stopBtn = document.getElementById('stop-btn');
    const outputTextarea = document.getElementById('output-textarea');
    const flashStatus = document.getElementById('flash-status');
    const statusText = document.getElementById('status-text');
    const screenTypeSelect = document.getElementById('screen-type-select');
    
    // Update UI state
    flashBtn.style.display = 'none';
    stopBtn.style.display = 'inline-block';
    screenTypeSelect.disabled = true;
    flashStatus.style.display = 'block';
    statusText.textContent = `Starting flash process for ${screenType}...`;
    outputTextarea.value = '';
    
    // Start the flash process
    fetch('/flash/start', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            screen_type: screenType
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            currentProcessId = data.process_id;
            statusText.textContent = `Flashing ${screenType} firmware...`;
            appendOutput(data.message + '\n');
            startOutputStreaming();
        } else {
            showAlert(data.error || 'Failed to start flash process', 'danger');
            resetUI();
        }
    })
    .catch(error => {
        console.error('Error starting flash process:', error);
        showAlert('Failed to start flash process', 'danger');
        resetUI();
    });
}

function stopFlashProcess() {
    if (!currentProcessId) return;
    
    const statusText = document.getElementById('status-text');
    statusText.textContent = 'Stopping process...';
    
    fetch(`/flash/stop/${currentProcessId}`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            appendOutput('Process stopped by user\n');
            showAlert(data.message, 'info');
        } else {
            showAlert(data.error || 'Failed to stop process', 'danger');
        }
        resetUI();
    })
    .catch(error => {
        console.error('Error stopping flash process:', error);
        showAlert('Failed to stop process', 'danger');
        resetUI();
    });
}

function startOutputStreaming() {
    if (!currentProcessId) return;
    
    // Close existing stream
    if (outputStream) {
        outputStream.close();
    }
    
    // Start new EventSource stream
    outputStream = new EventSource(`/flash/output/${currentProcessId}`);
    
    outputStream.onmessage = function(event) {
        if (event.data.trim()) {
            appendOutput(event.data + '\n');
        }
    };
    
    outputStream.addEventListener('finished', function(event) {
        const returnCode = parseInt(event.data);
        const statusText = document.getElementById('status-text');
        
        if (returnCode === 0) {
            statusText.textContent = 'Flash completed successfully';
            showAlert('Firmware flashing completed successfully!', 'success');
        } else {
            statusText.textContent = `Flash failed with exit code ${returnCode}`;
            showAlert(`Firmware flashing failed with exit code ${returnCode}`, 'danger');
        }
        
        appendOutput(`\n=== Process finished with exit code: ${returnCode} ===\n`);
        resetUI();
    });
    
    outputStream.onerror = function(event) {
        console.error('Output stream error:', event);
        appendOutput('Error: Connection to output stream lost\n');
        resetUI();
    };
}

function resetUI() {
    const flashBtn = document.getElementById('flash-btn');
    const stopBtn = document.getElementById('stop-btn');
    const screenTypeSelect = document.getElementById('screen-type-select');
    
    flashBtn.style.display = 'inline-block';
    stopBtn.style.display = 'none';
    screenTypeSelect.disabled = false;
    
    // Close output stream
    if (outputStream) {
        outputStream.close();
        outputStream = null;
    }
    
    currentProcessId = null;
}

function appendOutput(text) {
    const outputTextarea = document.getElementById('output-textarea');
    outputTextarea.value += text;
    // Auto-scroll to bottom
    outputTextarea.scrollTop = outputTextarea.scrollHeight;
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
        if (alertDiv.parentNode) {
            const bsAlert = new bootstrap.Alert(alertDiv);
            bsAlert.close();
        }
    }, 5000);
}