# Assets

Images referenced by the project README.

Replacing either one means dropping the new file here under the same name; the
README references them by path and needs no edit.

## `wingman-logo.png`

The FlyGD Wingman emblem. Currently a 489×510 PNG with a genuinely
transparent background, rendered at 180 px wide in the README.

- Roughly square, at least ~500 px on the short side.
- **Transparent background, actually transparent.** Check it rather than
  trusting the file: a PNG can be mode `P` with a transparency chunk and still
  be fully opaque once composited. `Image.open(f).convert("RGBA")` and look at
  a corner pixel's alpha — 0 is transparent, 255 is an opaque matte that will
  render as a coloured box on one of GitHub's two themes.
- Bear in mind the README is read on both a light and a dark background. Art
  that is uniformly dark disappears on the dark theme, and vice versa.
- Must be original or properly licensed artwork. Do **not** use Google,
  YouTube, OBS Studio, EVE Online, or Discord artwork — this project is not
  affiliated with any of them.

`obs_youtube_uploader/assets/app.ico` is derived from this file, so replacing
it here does **not** update the application icon — the taskbar, tray, and both
windows keep the old art until the `.ico` is regenerated. The crop is the crest
alone: the wordmark is unreadable below 256 px and its navy text disappears
against a dark taskbar. See the commit that last rebuilt the `.ico`
(`git log -- obs_youtube_uploader/assets/app.ico`) for the exact recipe.

## `wingman-screenshot.png`

The main FlyGD Wingman window, used as the README hero image. Currently
2038×1286, displayed at 850.

- Show several recordings listed. Ideally include at least one row with a
  filled-in **Link**, so the upload half of the workflow is visible at a
  glance — the current shot does not, and is worth replacing when a
  convenient one comes along.
- **Stored at native resolution and downscaled by the browser.** This is a
  change from the previous file, which was stored at exactly its 850 px
  display width. A ~2.4× asset stays sharp on a HiDPI display where a 1:1
  one looks soft, and costs about 120 KB. The rule that matters is the one
  below; matching the two exactly is no longer expected.
- **Never set `width` in README.md ABOVE the image's real pixel width.**
  Upscaling looks soft. Below it is fine and is what the HiDPI asset relies
  on.
- **Check before committing**: the Link column exposes a real video ID, and
  an unlisted video is watchable by anyone holding its URL. Never capture
  the Settings route with a Discord webhook URL visible — a webhook URL is a
  bearer credential.
- Keep the alt text in README.md describing the image that is ACTUALLY
  committed. If the two drift, a screen-reader user is told about a window
  nobody can see.
