# Explorer Tab Right Panel Layout Update

**Date:** November 21, 2025  
**Author:** Anzal  
**Status:** Completed

## Overview

Updated the ExplorerTab layout to move the Analysis Selection section to the right panel, below the File Explorer, creating a more organized and space-efficient interface.

## Changes Made

### 1. Analysis Selection Group - Moved to Right Panel

**Previous Location:** Left panel, below File Information group

**New Location:** Right panel, between File Explorer and Y-axis controls

#### Implementation Details

```python
# Now in right panel, after File Explorer tree_group
analysis_group = QtWidgets.QGroupBox("Analysis Selection")
analysis_layout = QtWidgets.QVBoxLayout(analysis_group)
analysis_layout.setContentsMargins(5, 5, 5, 5)
analysis_layout.setSpacing(5)

# Contains:
# - Add Recording to Set button
# - Clear Analysis Set button
# - Analysis Set label (shows count)

right_main_layout.addWidget(analysis_group)
```

### 2. File Explorer Group - Size Adjustment

**Change:** Modified stretch factor from `stretch=1` to `stretch=0`

**Reason:** Allows the File Explorer to be more compact, making room for the Analysis Selection section below it without taking excessive vertical space.

```python
right_main_layout.addWidget(tree_group, stretch=0)  # Reduced from stretch=1
```

### 3. File Cycling Buttons - Confirmed Present

**Location:** Top of center panel (above plots)

**Components:**
- `<< Prev File` button
- File index label (e.g., "2/5: filename.abf")
- `Next File >>` button

**Status:** Already present and properly configured. Buttons are:
- Visible when multiple files are loaded from a folder
- Hidden for single-file sessions
- Connected to `_prev_file_folder()` and `_next_file_folder()` methods
- Automatically enabled/disabled based on position in file list

## Layout Structure

### Before
```
┌─────────────┬──────────────┬────────────┐
│ Left Panel  │ Center Panel │ Right Panel│
│             │              │            │
│ Display     │  [Plots]     │ File Tree  │
│ Options     │              │            │
│             │              │            │
│ Manual      │              │ Y Controls │
│ Limits      │              │            │
│             │              │            │
│ Channels    │              │            │
│             │              │            │
│ File Info   │              │            │
│             │              │            │
│ **Analysis**│              │            │
│ **Selection**│             │            │
└─────────────┴──────────────┴────────────┘
```

### After
```
┌─────────────┬──────────────┬────────────┐
│ Left Panel  │ Center Panel │ Right Panel│
│             │              │            │
│ Display     │ << Prev File │ Open File  │
│ Options     │ [1/5: file]  │ File Tree  │
│             │ Next File >> │ (compact)  │
│ Manual      │              │            │
│ Limits      │  [Plots]     │ **Analysis**│
│             │              │ **Selection**│
│ Channels    │              │            │
│             │              │ Y Controls │
│ File Info   │              │            │
│             │              │            │
└─────────────┴──────────────┴────────────┘
```

## Benefits

1. **Better Organization:** Analysis controls grouped with file management on right side
2. **Logical Flow:** File selection → Analysis selection → Y-axis controls
3. **Left Panel Decluttered:** More space for display options and channel controls
4. **Consistent Grouping:** File-related operations now on the right side
5. **Space Efficiency:** File tree more compact, making room for analysis controls

## Technical Details

### File Modified
- `src/Synaptipy/application/gui/explorer_tab.py`

### Key Changes
1. Removed Analysis Selection group from left panel (line ~420)
2. Added Analysis Selection group to right panel (line ~552)
3. Modified File Explorer stretch factor (line ~551)
4. Maintained all button connections and functionality

### UI References Preserved
All UI element references remain intact:
- `self.add_analysis_button`
- `self.clear_analysis_button`
- `self.analysis_set_label`
- `self.file_tree`
- `self.prev_file_button`
- `self.next_file_button`
- `self.folder_file_index_label`

## File Cycling Buttons Behavior

The file cycling buttons at the top of the center panel have the following behavior:

### Visibility Logic (from `_update_ui_state()`)
```python
is_folder = len(self.file_list) > 1

# Buttons are visible only when multiple files are loaded
prev_file_button.setVisible(is_folder)
next_file_button.setVisible(is_folder)
folder_file_index_label.setVisible(is_folder)

# Enabled based on position
prev_file_button.setEnabled(is_folder and current_file_index > 0)
next_file_button.setEnabled(is_folder and current_file_index < len(file_list) - 1)

# Label shows: "2/5: filename.abf"
```

### When Buttons Appear
- ✅ When opening a file that has sibling files in the same folder
- ✅ When multiple files are dropped/loaded
- ❌ When loading a single file with no siblings
- ❌ When no file is loaded

## Testing

### Structural Verification
```bash
python -c "from src.Synaptipy.application.gui.explorer_tab import ExplorerTab; ..."
```

**Results:**
- ✅ All UI components created successfully
- ✅ File cycling buttons present and configured
- ✅ Analysis section moved to right panel
- ✅ File Explorer on right panel with proper sizing
- ✅ No linter errors

### Visual Testing Steps
1. Launch application: `python -m Synaptipy`
2. Navigate to Explorer tab
3. Verify right panel layout:
   - Open File button at top
   - File Explorer (tree view) below
   - Analysis Selection below file tree
   - Y-axis controls at bottom
4. Load a file from a folder with multiple files
5. Verify file cycling buttons appear above plots:
   - `<< Prev File` on left
   - File index in center (e.g., "2/5: test.abf")
   - `Next File >>` on right
6. Test file cycling functionality
7. Add recording to analysis set using button in right panel

## Compatibility

- ✅ Backward compatible with existing code
- ✅ All signals and slots preserved
- ✅ No breaking changes to public API
- ✅ Session manager integration intact
- ✅ File cycling logic unchanged

## Related Files

This update complements the AnalyserTab refactoring (see `ANALYSER_TAB_REFACTORING.md`), creating a consistent right-panel control scheme across both tabs:

- **ExplorerTab:** File operations + Analysis selection on right
- **AnalyserTab:** File list + Item selector on right (in sidebar)

## Future Enhancements

1. Consider making File Explorer collapsible to save space when not needed
2. Add keyboard shortcuts for file cycling (e.g., Ctrl+Left/Right)
3. Consider adding file filtering options to the File Explorer
4. Add drag-and-drop support for analysis set (already implemented for file tree)

## Conclusion

The ExplorerTab right panel has been successfully reorganized to:
- Move Analysis Selection controls closer to file management operations
- Maintain all existing functionality including file cycling buttons
- Improve overall UI organization and user workflow
- Create a more logical left-to-right information flow

All changes are production-ready and enhance the user experience without breaking existing functionality.

