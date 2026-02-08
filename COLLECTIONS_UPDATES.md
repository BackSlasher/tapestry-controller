# Collections Feature Updates

## Issues Fixed

### 1. **Image Upload Not Refreshing UI** ✅

**Problem:** After uploading images, the UI stayed at "0 images" until the collection was manually re-selected.

**Solution:** Updated `uploadImages()` function in `collections.js` to:
- Reload the collection images list after successful upload
- Reload the collections list to update the image count badge
- Both happen automatically after upload completes

**Files Changed:**
- `src/tapestry/webui/static/collections.js` - Added `await loadCollections()` after upload

### 2. **Moved Collection Selection to Screensaver Page** ✅

**Problem:** Having an "active collection" concept on the Collections page was confusing and not the right place for screensaver configuration.

**Solution:** 
- Removed "Set as Active Gallery" button from Collections page
- Removed "Active" badge from collection list
- Added collection selector to Screensaver configuration page
- Collection selection is now part of Gallery screensaver settings

**Files Changed:**

**Collections Page:**
- `src/tapestry/webui/templates/collections.html` - Removed "Set as Active Gallery" button
- `src/tapestry/webui/static/collections.js` - Removed active badge logic and `selectCollection()` function

**Screensaver Page:**
- `src/tapestry/webui/templates/screensaver.html` - Replaced wallpapers directory selector with collection dropdown
- JavaScript updated to load collections from API instead of hardcoded directories

**Backend:**
- `src/tapestry/webui/app.py`:
  - Updated `update_screensaver_config()` to handle `selected_collection` field
  - Updated `screensaver_status()` to show selected collection name
  - Updated `api_delete_collection()` to show warning if deleting collection that's selected in screensaver
- `COLLECTIONS_FEATURE.md` - Updated documentation to reflect new workflow

---

## Current User Workflow

### Managing Collections

1. **Navigate to Collections page** from main menu
2. **Create collections** with "New Collection" button
3. **Upload images** to any collection
4. **Browse, rename, delete** collections as needed

### Using Collections with Screensaver

1. **Navigate to Screensaver page** from main menu
2. **Select "Gallery" as screensaver type**
3. **Choose a collection** from the dropdown (shows image counts)
4. **Update configuration**
5. **Start/stop screensaver** as normal

---

## Technical Details

### Collection Selection Flow

```
User visits Screensaver page
    ↓
JavaScript loads collections via GET /api/collections
    ↓
Dropdown populated with collection names and image counts
    ↓
Current selected_collection is pre-selected in dropdown
    ↓
User selects different collection and submits form
    ↓
POST /screensaver/config with selected_collection field
    ↓
Settings updated in settings.toml
    ↓
If screensaver active, it restarts with new collection
```

### Image Upload Flow

```
User selects files and uploads
    ↓
For each file: POST /api/collections/<name>/images
    ↓
Files saved to collection directory
    ↓
After all uploads complete:
    ↓
Reload images: GET /api/collections/<name>/images
    ↓
Reload collections list: GET /api/collections
    ↓
UI updates with new images and updated counts
```

---

## Settings Structure

Collections settings in `settings.toml`:

```toml
[screensaver.gallery]
wallpapers_dir = "wallpapers"  # Legacy fallback
collections_dir = "~/.tapestry/collections"  # Collections root
selected_collection = "nature"  # Currently selected for screensaver
```

---

## API Changes

### Endpoints Modified

**DELETE /api/collections/<name>**
- Now allows deleting any collection
- Shows warning if collection is currently selected in screensaver
- Returns `warning` field in success response

**POST /screensaver/config**
- Now accepts `selected_collection` form field
- Updates `settings.screensaver.gallery.selected_collection`

**GET /screensaver/status**
- For gallery type, returns `selected_collection` field
- Uses collection name for `wallpapers_dir` display field

---

## UI/UX Improvements

### Collections Page
- ✅ Cleaner interface without "active" concept
- ✅ Focus on organizing and managing images
- ✅ Automatic refresh after upload
- ✅ Image count updates immediately

### Screensaver Page
- ✅ Collection selector with image counts
- ✅ "Manage collections" link to Collections page
- ✅ Clear indication of which collection is being used
- ✅ All screensaver config in one place

---

## Testing Checklist

- [x] Upload images to collection - UI refreshes automatically
- [x] Collections list shows updated image counts
- [x] Navigate to Screensaver page
- [x] Gallery type shows collection dropdown
- [x] Selected collection is pre-selected
- [x] Change collection and update config
- [x] Start screensaver - uses selected collection
- [x] Delete collection that's selected - shows warning
- [x] Delete other collection - works normally

---

## Breaking Changes

**None** - This is fully backward compatible:
- Existing `wallpapers_dir` setting still works as fallback
- Legacy wallpapers automatically migrated on first run
- Default "wallpapers" collection created if needed

---

## Benefits

1. **Intuitive workflow** - Configuration is where you expect it
2. **Automatic updates** - No manual refresh needed after upload
3. **Better organization** - Collections page focuses on management
4. **Clearer intent** - Screensaver settings all in Screensaver page
5. **Visual feedback** - Image counts shown everywhere
6. **Safety** - Warnings when deleting important collections
