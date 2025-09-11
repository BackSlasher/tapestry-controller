// QR Positioning functionality

document.addEventListener('DOMContentLoaded', function() {
    const startQRBtn = document.getElementById('start-qr-mode');
    const qrStatus = document.getElementById('qr-status');
    const photoInput = document.getElementById('photo-input');
    const analyzeBtn = document.getElementById('analyze-btn');
    const resultsSection = document.getElementById('results-section');
    const detectionResults = document.getElementById('detection-results');
    const configPreview = document.getElementById('config-preview');
    const configYaml = document.getElementById('config-yaml');
    const applyConfigBtn = document.getElementById('apply-config');
    const downloadConfigBtn = document.getElementById('download-config');

    let detectedConfig = null;

    // Start QR mode
    startQRBtn.addEventListener('click', function() {
        startQRBtn.disabled = true;
        startQRBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Displaying QR codes...';

        fetch('/positioning/qr-mode', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                qrStatus.style.display = 'block';
                startQRBtn.innerHTML = '<i class="bi bi-qr-code"></i> QR Codes Displayed';
                startQRBtn.classList.remove('btn-primary');
                startQRBtn.classList.add('btn-success');
            } else {
                throw new Error(data.error || 'Failed to display QR codes');
            }
        })
        .catch(error => {
            alert('Error displaying QR codes: ' + error.message);
            startQRBtn.disabled = false;
            startQRBtn.innerHTML = '<i class="bi bi-qr-code"></i> Show QR Codes on Screens';
        });
    });

    // Enable analyze button when photo is selected
    photoInput.addEventListener('change', function() {
        analyzeBtn.disabled = !this.files.length;
    });

    // Analyze photo
    analyzeBtn.addEventListener('click', function() {
        const file = photoInput.files[0];
        if (!file) {
            alert('Please select a photo first');
            return;
        }

        analyzeBtn.disabled = true;
        analyzeBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Analyzing...';

        const formData = new FormData();
        formData.append('photo', file);

        fetch('/positioning/analyze', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                displayResults(data.results, data.config);
                resultsSection.style.display = 'block';
            } else {
                throw new Error(data.error || 'Failed to analyze photo');
            }
        })
        .catch(error => {
            alert('Error analyzing photo: ' + error.message);
        })
        .finally(() => {
            analyzeBtn.disabled = false;
            analyzeBtn.innerHTML = '<i class="bi bi-search"></i> Analyze Positions';
        });
    });

    function displayResults(results, config) {
        detectionResults.innerHTML = '';

        if (Object.keys(results).length === 0) {
            detectionResults.innerHTML = `
                <div class="alert alert-warning">
                    <i class="bi bi-exclamation-triangle"></i>
                    <strong>No screens detected!</strong> 
                    Please ensure QR codes are visible and try again.
                </div>
            `;
            return;
        }

        // Display detected screens table
        let tableHtml = `
            <div class="alert alert-success">
                <i class="bi bi-check-circle"></i>
                <strong>Found ${Object.keys(results).length} screens!</strong>
            </div>
            <div class="table-responsive">
                <table class="table table-striped">
                    <thead>
                        <tr>
                            <th>Hostname</th>
                            <th>Position (mm)</th>
                            <th>Rotation</th>
                            <th>Scale Factor</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        for (const [hostname, data] of Object.entries(results)) {
            tableHtml += `
                <tr>
                    <td><code>${hostname}</code></td>
                    <td>(${data.x}, ${data.y})</td>
                    <td>${Math.round(data.rotation)}°</td>
                    <td>${data.scale_factor.toFixed(3)}</td>
                </tr>
            `;
        }

        tableHtml += `
                    </tbody>
                </table>
            </div>
        `;

        detectionResults.innerHTML = tableHtml;

        // Show config preview
        detectedConfig = config;
        configYaml.textContent = formatYaml(config);
        configPreview.style.display = 'block';
    }

    function formatYaml(obj, indent = 0) {
        let yaml = '';
        const indentStr = '  '.repeat(indent);
        
        for (const [key, value] of Object.entries(obj)) {
            yaml += indentStr + key + ':\n';
            if (Array.isArray(value)) {
                for (const item of value) {
                    yaml += indentStr + '  - ';
                    if (typeof item === 'object') {
                        yaml += '\n' + formatYaml(item, indent + 2);
                    } else {
                        yaml += item + '\n';
                    }
                }
            } else if (typeof value === 'object') {
                yaml += formatYaml(value, indent + 1);
            } else {
                yaml += indentStr + '  ' + value + '\n';
            }
        }
        return yaml;
    }

    // Apply configuration
    applyConfigBtn.addEventListener('click', function() {
        if (!detectedConfig) {
            alert('No configuration to apply');
            return;
        }

        if (!confirm('This will update your device configuration. Continue?')) {
            return;
        }

        applyConfigBtn.disabled = true;
        applyConfigBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Applying...';

        fetch('/positioning/apply', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(detectedConfig)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Configuration applied successfully!');
                // Optionally redirect to home page
                window.location.href = '/';
            } else {
                throw new Error(data.error || 'Failed to apply configuration');
            }
        })
        .catch(error => {
            alert('Error applying configuration: ' + error.message);
        })
        .finally(() => {
            applyConfigBtn.disabled = false;
            applyConfigBtn.innerHTML = '<i class="bi bi-check2-all"></i> Apply Configuration';
        });
    });

    // Download configuration
    downloadConfigBtn.addEventListener('click', function() {
        if (!detectedConfig) {
            alert('No configuration to download');
            return;
        }

        const yamlContent = formatYaml(detectedConfig);
        const blob = new Blob([yamlContent], { type: 'text/yaml' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'devices_positioned.yaml';
        a.click();
        URL.revokeObjectURL(url);
    });
});