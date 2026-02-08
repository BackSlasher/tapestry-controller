# Image Collections Feature

## Overview

This feature adds a comprehensive image collections management system to Tapestry, allowing users to organize images into named collections and manage them through the web interface.

## What's New

### 1. **Collections System**
- Organize images into named collections (e.g., "Nature", "Abstract", "Family Photos")
- Each collection is a directory under `~/.tapestry/collections/`
- Collections can be selected as the active gallery for the screensaver

### 2. **Web Interface**
- New "Collections" page accessible from the navigation menu
- Full CRUD operations:
  - **Create** new collections
  - **Read** and browse collections and their images
  - **Update** (rename) collections
  - **Delete** collections and images
- Drag-and-drop image upload (multiple files supported)
- Visual preview of images with thumbnails
- Delete individual images from collections

### 3. **Backward Compatibility**
- Automatic migration of legacy `wallpapers/` directory to collections
- Legacy `wallpapers_dir` setting still supported as fallback
- Default "wallpapers" collection created automatically

## File Structure

```
~/.tapestry/
├── collections/           # Root collections directory
│   ├── wallpapers/       # Default collection (migrated from legacy)
│   │   ├── image1.jpg
│   │   └── image2.png
│   ├── nature/           # User-created collection
│   │   ├── forest.jpg
│   │   └── ocean.png
│   └── abstract/         # Another collection
│       └── geometric.jpg
└── last_image.png        # Cached last displayed image
```

## New Files Added

### Backend
1. **`src/tapestry/webui/collections_manager.py`** - Core collections management logic
   - Collection CRUD operations
   - Image upload/delete functionality
   - Validation and security checks

2. **`src/tapestry/webui/collections_migration.py`** - Migration utilities
   - Automatic migration from legacy wallpapers
   - Default collection setup

### Frontend
3. **`src/tapestry/webui/templates/collections.html`** - Collections UI page
4. **`src/tapestry/webui/static/collections.js`** - Client-side JavaScript

## Modified Files

### Backend Changes
1. **`src/tapestry/settings.py`**
   - Added `collections_dir` setting (default: `~/.tapestry/collections`)
   - Added `selected_collection` setting (default: `wallpapers`)
   - Updated `GallerySettings` model

2. **`src/tapestry/webui/screensaver.py`**
   - Updated to use collections instead of single directory
   - Fallback to legacy `wallpapers_dir` for compatibility

3. **`src/tapestry/webui/app.py`**
   - Added 13 new API routes for collections management
   - Added migration check on app startup
   - Updated screensaver config to include collections settings

### Frontend Changes
4. **`src/tapestry/webui/templates/base.html`**
   - Added "Collections" navigation link

## API Endpoints

### Collections Management
- `GET /collections` - Collections management page
- `GET /api/collections` - List all collections
- `POST /api/collections` - Create new collection
- `DELETE /api/collections/<name>` - Delete collection
- `POST /api/collections/<name>/rename` - Rename collection
- `POST /api/collections/<name>/select` - Set as active gallery

### Image Management
- `GET /api/collections/<name>/images` - List images in collection
- `POST /api/collections/<name>/images` - Upload image to collection
- `DELETE /api/collections/<name>/images/<filename>` - Delete image
- `GET /api/collections/<name>/images/<filename>` - Get/view image

## Usage Guide

### Creating a Collection

1. Navigate to **Collections** page from the menu
2. Click **"New Collection"** button
3. Enter a name (letters, numbers, spaces, hyphens, underscores allowed)
4. Click **"Create"**

### Uploading Images

1. Select a collection from the list
2. Use the file input to select one or multiple images
3. Images are uploaded automatically
4. Thumbnails appear in the images grid

### Setting Active Gallery

1. Navigate to the **Screensaver** page
2. Select **Gallery** as the screensaver type
3. Choose a collection from the **Image Collection** dropdown
4. Click **Update Configuration**
5. If screensaver is running, it will restart with the new collection

### Deleting Images

1. Select a collection
2. Find the image thumbnail
3. Click the trash icon on the image card
4. Confirm deletion

### Renaming Collections

1. Select a collection
2. Click **"Rename Collection"**
3. Enter new name
4. If collection is currently selected as active gallery, the selection updates automatically

### Deleting Collections

1. Select a collection
2. Click **"Delete Collection"**
3. Confirm deletion (this deletes all images in the collection!)
4. If the collection is currently selected in Screensaver settings, you'll receive a warning

## Settings Configuration

Collections settings are stored in `settings.toml`:

```toml
[screensaver.gallery]
wallpapers_dir = "wallpapers"  # Legacy fallback
collections_dir = "~/.tapestry/collections"  # Collections root
selected_collection = "wallpapers"  # Active collection name
```

## Migration Process

On first startup with collections feature:

1. Check if `~/.tapestry/collections/` exists and is empty
2. Check if legacy `wallpapers/` directory exists with images
3. If both conditions are true:
   - Copy all images from `wallpapers/` to `~/.tapestry/collections/wallpapers/`
   - Log migration success
4. If no legacy directory exists:
   - Create empty `wallpapers` collection as default

## Security Features

### Validation
- Collection names: alphanumeric, spaces, hyphens, underscores only (max 100 chars)
- Filenames: no path components allowed (prevents directory traversal)
- File types: PNG, JPG, JPEG, GIF, BMP, TIFF, WebP only

### Protection
- Cannot delete currently active collection
- Cannot overwrite existing collections
- Path validation prevents escaping collections directory
- Dangerous collection names (., .., .git) are rejected

## Error Handling

- Graceful fallback to legacy wallpapers directory if collection not found
- Informative error messages in UI
- Backend validation with detailed error responses
- Upload progress tracking with failure counts

## Testing the Feature

### Manual Testing Steps

1. **Start the application:**
   ```bash
   tapestry-webui
   ```

2. **Access Collections page:**
   - Navigate to http://localhost:5000/collections
   - Verify page loads with empty state or migrated wallpapers

3. **Create a collection:**
   - Click "New Collection"
   - Enter "Test Collection"
   - Verify it appears in the list

4. **Upload images:**
   - Select the collection
   - Upload multiple images
   - Verify thumbnails appear
   - Check file count updates

5. **Set as active gallery:**
   - Go to Screensaver page
   - Select "Gallery" type
   - Choose the collection from dropdown
   - Click "Update Configuration"
   - Start screensaver and confirm it uses images from the collection

6. **Rename collection:**
   - Select a collection
   - Click "Rename Collection"
   - Enter new name
   - Verify update in list

7. **Delete image:**
   - Click trash icon on an image
   - Confirm deletion
   - Verify image removed

8. **Delete collection:**
   - Create a test collection
   - Try to delete the active collection (should fail)
   - Select and delete the test collection
   - Verify deletion

### API Testing with curl

```bash
# List collections
curl http://localhost:5000/api/collections

# Create collection
curl -X POST http://localhost:5000/api/collections \
  -H "Content-Type: application/json" \
  -d '{"name": "Test API Collection"}'

# Upload image
curl -X POST http://localhost:5000/api/collections/Test%20API%20Collection/images \
  -F "image=@/path/to/image.jpg"

# List images
curl http://localhost:5000/api/collections/Test%20API%20Collection/images

# Select collection
curl -X POST http://localhost:5000/api/collections/Test%20API%20Collection/select

# Delete image
curl -X DELETE http://localhost:5000/api/collections/Test%20API%20Collection/images/image.jpg

# Rename collection
curl -X POST http://localhost:5000/api/collections/Test%20API%20Collection/rename \
  -H "Content-Type: application/json" \
  -d '{"new_name": "Renamed Collection"}'

# Delete collection
curl -X DELETE http://localhost:5000/api/collections/Renamed%20Collection
```

## Future Enhancements (Ideas)

- [ ] Bulk image operations (select multiple, delete multiple)
- [ ] Collection search/filter
- [ ] Image metadata (tags, descriptions)
- [ ] Collection sharing/export
- [ ] Image editing (crop, rotate, filters)
- [ ] Slideshow preview of collection
- [ ] Organize images within collection (reorder)
- [ ] Import from URLs
- [ ] Recursive collections (sub-collections)

## Troubleshooting

### Collections not appearing
- Check `~/.tapestry/collections/` directory exists
- Verify directory permissions
- Check browser console for JavaScript errors

### Images not uploading
- Verify file types are supported
- Check file size (16MB max per Flask config)
- Ensure collection exists
- Check disk space

### Migration not working
- Check if `wallpapers/` directory exists
- Verify read permissions on legacy directory
- Check logs for migration errors
- Manually create `wallpapers` collection if needed

### Screensaver not using collection
- Go to Screensaver page and verify correct collection is selected
- Restart screensaver after changing collection selection
- Check that the selected collection has images
- Verify `settings.toml` has correct `selected_collection`

## Architecture Notes

### Design Decisions

1. **File-based storage:** Collections are directories for simplicity and portability
2. **User directory:** Using `~/.tapestry/` keeps user data separate from code
3. **Validation:** Strict name validation prevents security issues
4. **Migration:** Automatic migration provides smooth upgrade experience
5. **Fallback:** Legacy support ensures no breaking changes

### Performance Considerations

- Image thumbnails generated by browser (CSS object-fit)
- API returns metadata, not image data for listings
- Lazy loading of collection details (click to view)
- Sequential upload with progress tracking

## Contributing

When extending this feature:

1. Maintain backward compatibility with legacy `wallpapers_dir`
2. Add validation for any user input
3. Use the collections_manager module for all file operations
4. Update this documentation
5. Add error handling and logging
6. Test migration scenarios
