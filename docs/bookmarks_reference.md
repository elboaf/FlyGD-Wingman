# Wingman Backend - Usage Documentation

## Overview
Wingman is a hotkey-driven script that helps EVE Online players create properly formatted wormhole bookmarks with automatic incrementing numbering and signature IDs.

## Set Root
Tells Wingman where you are or where you are going. This establishes the base system name for all subsequent bookmarks.

### Valid Selections:
| Selection | Behavior |
|-----------|----------|
| **Nothing** | Sets Home/Zero mode with fresh numbering starting at 1/A. Nothing is moved to clipboard. |
| **Single bookmark** | Sets root from the number on the bookmark text. Fresh numbering begins. The number is copied to clipboard. Useful for the hole you're about to jump and scan, or on a return bookmark. |
| **Entire bookmark list** | Sets root to current system. Intelligently numbers the next bookmark to fill gaps in the existing list. Useful when re-scanning a previously scanned system where some wormholes have expired. |

## Grab Sig ID
Tells Wingman the signature ID for the next bookmark to create.

### Valid Selections:
- Single probe scanner row/line

### Results:
- `-[SIGID]` is moved to clipboard (useful for manually pasting sig ID to return bookmarks)
- The next finisher will use the sig ID in the constructed bookmark text

### Workflow:
1. Select a sig in the probe scanner
2. Press **Grab Sig ID** hotkey
3. Next finisher pressed will append the grabbed sig ID to the bookmark name

## Finishers
Tells Wingman the wormhole class for the bookmark text.

### Valid In:
- Any text field in an enabled EVE Online window
- **Specifically designed for bookmark windows**
- Works in chat fields too (though primarily for bookmarks)

### Features:
- **Autocorrects** on user error (e.g., pressing C3 then C4 will result in proper C4 bookmark text without erroneously incrementing the number)
- **Number only increments** upon the next **Grab Sig ID** action, ensuring correct sequencing

### Available Finishers:
| Finisher | Resulting Class |
|----------|-----------------|
| H | Highsec |
| L | Lowsec |
| N | Nullsec |
| 13 | Shattered (C13) |
| 1 | C1 |
| 2 | C2 |
| 3 | C3 |
| 4 | C4 |
| 5 | C5 |
| 6 | C6 |

## Tags
Appends specific tags to the end of the bookmark string.

### Available Tags:
| Tag | Meaning |
|-----|---------|
| `e` | End of Life (EOL) |
| `/` | Half Mass |
| `f` | Frigate Hole |
| `c` | Critical |

### Features:
- **Validates** bookmark format before appending
- **Enforces mutual exclusivity** (e.g., half mass and critical are mutually exclusive; one will overwrite the other)

### Tag Rules:
- `e` (EOL) can stack with any other tag
- `/` (half mass) and `c` (critical) are mutually exclusive
  - Applying one will remove the other
  - If both exist, `c` takes priority
- `f` (frigate hole) can stack with any other tag

## Example Workflow
1. Set Root → Select system name/bookmark
2. Grab Sig ID → Select probe scanner signature
3. Press Finisher → e.g., "3" for C3
4. (Optional) Press Tags → e.g., "e" for end of life
5. Result: "11-ABC 3 e" or similar formatted bookmark

The bookmark will be automatically constructed and pasted into the active text field.

## Quick Reference Card

### Root Commands
- **Nothing selected** → Home/Zero mode, fresh numbering
- **Single bookmark** → Root set to bookmark, fresh numbering, bookmark number to clipboard
- **Bookmark list** → Root set to current system, fills numbering gaps

### Finisher Classes
| Key | Class |
|-----|-------|
| H | Highsec |
| L | Lowsec |
| N | Nullsec |
| 13 | Shattered |
| 1-6 | C1-C6 |

### Tags
| Key | Meaning |
|-----|---------|
| e | End of Life |
| / | Half Mass |
| f | Frigate Hole |
| c | Critical |

### Key Workflow
Set Root → Grab Sig ID → Finisher → Tags (optional) → Bookmark Created
