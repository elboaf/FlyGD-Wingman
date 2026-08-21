# Assets

Images referenced by the project README.

Replacing either one means dropping the new file here under the same name; the
README references them by path and needs no edit.

## `wingman-logo.png`

The FlyGD Wingman emblem. Currently 512×512 PNG with transparency, rendered at
160 px in the README.

- Square, transparent background, at least 512×512.
- Must be original or properly licensed artwork. Do **not** use Google,
  YouTube, OBS Studio, EVE Online, or Discord artwork — this project is not
  affiliated with any of them.

## `wingman-screenshot.png`

The main FlyGD Wingman window, used as the README hero image. Currently
850×678.

- Show several recordings listed and at least one row with a filled-in
  **YouTube Link**, so the core workflow is visible at a glance.
- Set the `width` attribute in README.md to the image's real pixel width;
  a larger value upscales and looks soft.
- **Check before committing**: the YouTube link column exposes a real video ID,
  and an unlisted video is watchable by anyone holding its URL. Never capture
  the Settings dialog with a Discord webhook URL visible — a webhook URL is a
  bearer credential.
