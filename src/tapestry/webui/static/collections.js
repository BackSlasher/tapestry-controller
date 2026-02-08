// Collections management JavaScript

let currentCollection = null;
let selectedCollection = null;
let createCollectionModal = null;
let renameCollectionModal = null;

document.addEventListener('DOMContentLoaded', function() {
    // Initialize modals
    createCollectionModal = new bootstrap.Modal(document.getElementById('createCollectionModal'));
    renameCollectionModal = new bootstrap.Modal(document.getElementById('renameCollectionModal'));
    
    // Check for collection in query string
    const urlParams = new URLSearchParams(window.location.search);
    const collectionParam = urlParams.get('collection');
    if (collectionParam) {
        currentCollection = collectionParam;
    }
    
    // Load collections on page load
    loadCollections();
    
    // Set up Enter key handlers for modals
    document.getElementById('new-collection-name').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            createCollection();
        }
    });
    
    document.getElementById('rename-collection-name').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            renameCollection();
        }
    });
});

async function loadCollections() {
    try {
        const response = await fetch('/api/collections');
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to load collections');
        }
        
        selectedCollection = data.selected_collection;
        displayCollections(data.collections);
        
        // If we had a current collection selected, keep it selected
        if (currentCollection && data.collections.find(c => c.name === currentCollection)) {
            document.getElementById('collection-select').value = currentCollection;
        }
    } catch (error) {
        console.error('Error loading collections:', error);
        showAlert(`Failed to load collections: ${error.message}`, 'danger');
    }
}

function displayCollections(collections) {
    const selectEl = document.getElementById('collection-select');
    const emptyState = document.getElementById('empty-state');
    const imagesSection = document.getElementById('images-section');
    
    if (collections.length === 0) {
        // Show empty state
        selectEl.innerHTML = '<option value="">No collections available</option>';
        selectEl.disabled = true;
        emptyState.style.display = 'block';
        imagesSection.style.display = 'none';
        document.getElementById('rename-btn').disabled = true;
        document.getElementById('delete-btn').disabled = true;
        return;
    }
    
    // Hide empty state
    emptyState.style.display = 'none';
    selectEl.disabled = false;
    
    // Populate dropdown
    let html = '<option value="">Select a collection...</option>';
    
    collections.forEach(collection => {
        html += `<option value="${escapeHtml(collection.name)}">${escapeHtml(collection.name)} (${collection.image_count} images)</option>`;
    });
    
    selectEl.innerHTML = html;
    
    // If we have a current collection, select it
    if (currentCollection) {
        selectEl.value = currentCollection;
        onCollectionChange();
    }
}

function onCollectionChange() {
    const selectEl = document.getElementById('collection-select');
    const selectedName = selectEl.value;
    
    if (!selectedName) {
        // No collection selected
        document.getElementById('images-section').style.display = 'none';
        document.getElementById('rename-btn').disabled = true;
        document.getElementById('delete-btn').disabled = true;
        currentCollection = null;
        
        // Clear query string
        updateQueryString(null);
        return;
    }
    
    // Collection selected
    currentCollection = selectedName;
    document.getElementById('rename-btn').disabled = false;
    document.getElementById('delete-btn').disabled = false;
    
    // Update URL with collection name
    updateQueryString(selectedName);
    
    // Load images for this collection
    loadCollectionImages(selectedName);
}

function updateQueryString(collectionName) {
    const url = new URL(window.location);
    
    if (collectionName) {
        url.searchParams.set('collection', collectionName);
    } else {
        url.searchParams.delete('collection');
    }
    
    // Update URL without reloading page
    window.history.pushState({}, '', url);
}

async function loadCollectionImages(collectionName) {
    const gridEl = document.getElementById('images-grid');
    const countEl = document.getElementById('image-count');
    const imagesSection = document.getElementById('images-section');
    
    try {
        imagesSection.style.display = 'block';
        gridEl.innerHTML = '<div class="text-center py-4"><div class="spinner-border"></div></div>';
        
        const response = await fetch(`/api/collections/${encodeURIComponent(collectionName)}/images`);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to load images');
        }
        
        countEl.textContent = data.images.length;
        
        let html = '<div class="row g-3">';
        
        // Add existing images first
        data.images.forEach(image => {
            const sizeKB = Math.round(image.size_bytes / 1024);
            html += `
                <div class="col-6 col-sm-4 col-md-3 col-lg-2">
                    <div class="card h-100">
                        <img src="/api/collections/${encodeURIComponent(collectionName)}/images/${encodeURIComponent(image.filename)}" 
                             class="card-img-top" alt="${escapeHtml(image.filename)}"
                             style="height: 180px; object-fit: cover; cursor: pointer;"
                             onclick="showImagePreview('${escapeHtml(collectionName)}', '${escapeHtml(image.filename)}')">
                        <div class="card-body p-2">
                            <div class="text-truncate small" title="${escapeHtml(image.filename)}">
                                ${escapeHtml(image.filename)}
                            </div>
                            <div class="d-flex justify-content-between align-items-center mt-2">
                                <small class="text-muted">${sizeKB} KB</small>
                                <button class="btn btn-sm btn-outline-danger" 
                                        onclick="deleteImage('${escapeHtml(collectionName)}', '${escapeHtml(image.filename)}'); event.stopPropagation();"
                                        title="Delete image">
                                    <i class="bi bi-trash"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
        
        // Add upload card as last item
        html += `
            <div class="col-6 col-sm-4 col-md-3 col-lg-2">
                <div class="card h-100 upload-card" onclick="document.getElementById('image-upload').click()" style="cursor: pointer;">
                    <div class="card-body d-flex flex-column align-items-center justify-content-center" style="height: 180px; border: 2px dashed #6c757d; border-radius: 0.25rem;">
                        <i class="bi bi-plus-circle" style="font-size: 3rem; color: #6c757d;"></i>
                        <div class="mt-2 text-center text-muted small">
                            <strong>Upload Images</strong>
                        </div>
                    </div>
                    <div class="card-body p-2">
                        <div class="text-center small text-muted">
                            Click to browse
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        html += '</div>';
        gridEl.innerHTML = html;
    } catch (error) {
        console.error('Error loading images:', error);
        gridEl.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle"></i> ${error.message}
            </div>
        `;
    }
}

function showImagePreview(collectionName, filename) {
    // Open image in new tab
    window.open(`/api/collections/${encodeURIComponent(collectionName)}/images/${encodeURIComponent(filename)}`, '_blank');
}

function showCreateCollectionModal() {
    document.getElementById('new-collection-name').value = '';
    createCollectionModal.show();
}

async function createCollection() {
    const nameInput = document.getElementById('new-collection-name');
    const name = nameInput.value.trim();
    
    if (!name) {
        showAlert('Please enter a collection name', 'danger');
        return;
    }
    
    try {
        const response = await fetch('/api/collections', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ name }),
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to create collection');
        }
        
        showAlert(data.message, 'success');
        createCollectionModal.hide();
        
        // Reload collections and select the new one
        currentCollection = name;
        await loadCollections();
        document.getElementById('collection-select').value = name;
        
        // Update query string and load images
        updateQueryString(name);
        document.getElementById('rename-btn').disabled = false;
        document.getElementById('delete-btn').disabled = false;
        await loadCollectionImages(name);
    } catch (error) {
        console.error('Error creating collection:', error);
        showAlert(error.message, 'danger');
    }
}

async function deleteCollection() {
    if (!currentCollection) return;
    
    if (!confirm(`Are you sure you want to delete the collection "${currentCollection}" and all its images?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/collections/${encodeURIComponent(currentCollection)}`, {
            method: 'DELETE',
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to delete collection');
        }
        
        // Show success message and any warning
        showAlert(data.message, 'success');
        if (data.warning) {
            showAlert(data.warning, 'warning');
        }
        
        // Clear current collection and reload
        currentCollection = null;
        document.getElementById('collection-select').value = '';
        document.getElementById('images-section').style.display = 'none';
        
        // Clear query string
        updateQueryString(null);
        
        await loadCollections();
    } catch (error) {
        console.error('Error deleting collection:', error);
        showAlert(error.message, 'danger');
    }
}

function showRenameCollectionModal() {
    if (!currentCollection) return;
    
    document.getElementById('rename-collection-name').value = currentCollection;
    renameCollectionModal.show();
}

async function renameCollection() {
    const nameInput = document.getElementById('rename-collection-name');
    const newName = nameInput.value.trim();
    
    if (!newName) {
        showAlert('Please enter a new collection name', 'danger');
        return;
    }
    
    if (newName === currentCollection) {
        renameCollectionModal.hide();
        return;
    }
    
    try {
        const response = await fetch(`/api/collections/${encodeURIComponent(currentCollection)}/rename`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ new_name: newName }),
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to rename collection');
        }
        
        showAlert(data.message, 'success');
        renameCollectionModal.hide();
        
        // Update to new name
        currentCollection = newName;
        
        // Reload collections and select the renamed one
        await loadCollections();
        document.getElementById('collection-select').value = newName;
        
        // Update query string to new name and reload images
        updateQueryString(newName);
        await loadCollectionImages(newName);
    } catch (error) {
        console.error('Error renaming collection:', error);
        showAlert(error.message, 'danger');
    }
}

async function uploadImages() {
    const fileInput = document.getElementById('image-upload');
    const files = fileInput.files;
    
    if (!files || files.length === 0) return;
    if (!currentCollection) {
        showAlert('No collection selected', 'danger');
        return;
    }
    
    const progressSection = document.getElementById('upload-progress-section');
    const progressBar = document.getElementById('upload-progress-bar');
    const statusText = document.getElementById('upload-status');
    
    progressSection.style.display = 'block';
    
    let uploaded = 0;
    let failed = 0;
    
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const progress = Math.round(((i + 1) / files.length) * 100);
        
        progressBar.style.width = `${progress}%`;
        statusText.textContent = `Uploading ${file.name}... (${i + 1}/${files.length})`;
        
        try {
            const formData = new FormData();
            formData.append('image', file);
            
            const response = await fetch(`/api/collections/${encodeURIComponent(currentCollection)}/images`, {
                method: 'POST',
                body: formData,
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Upload failed');
            }
            
            uploaded++;
        } catch (error) {
            console.error(`Error uploading ${file.name}:`, error);
            failed++;
        }
    }
    
    progressSection.style.display = 'none';
    progressBar.style.width = '0%';
    fileInput.value = '';
    
    if (uploaded > 0) {
        showAlert(`Uploaded ${uploaded} image(s)${failed > 0 ? `, ${failed} failed` : ''}`, 'success');
        // Reload both the images and the collection list to update counts
        await loadCollectionImages(currentCollection);
        await loadCollections();
    } else {
        showAlert('All uploads failed', 'danger');
    }
}

async function deleteImage(collectionName, filename) {
    if (!confirm(`Delete "${filename}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(
            `/api/collections/${encodeURIComponent(collectionName)}/images/${encodeURIComponent(filename)}`,
            {
                method: 'DELETE',
            }
        );
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Failed to delete image');
        }
        
        showAlert(data.message, 'success');
        
        // Reload images and update collection list (to update count)
        await loadCollectionImages(collectionName);
        await loadCollections();
    } catch (error) {
        console.error('Error deleting image:', error);
        showAlert(error.message, 'danger');
    }
}

// Note: showAlert is defined in common.js and takes (message, type) parameters

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
