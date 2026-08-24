# Third-party software in FlyGD Wingman

FlyGD Wingman itself is GPL-3.0-only (see LICENSE). It bundles the
following programs, which are licensed separately. They are under different
GPL versions -- v3 for FFmpeg, v2-or-later for AutoHotkey -- so each carries
its own licence text rather than sharing one, and neither of them is the
licence covering Wingman itself.

## FFmpeg

Version: 7.1 (`ffmpeg-7.1-essentials_build`)
Licence: GNU General Public License v3
Source: https://github.com/FFmpeg/FFmpeg/commit/b08d7969c5
Build scripts: https://github.com/GyanD/codexffmpeg/releases/tag/7.1
Licence text: `ffmpeg-COPYING.txt`, installed beside the application.

## AutoHotkey

Version: 1.1.37.02
Licence: GNU General Public License v2 or later
Source: https://github.com/AutoHotkey/AutoHotkey/releases/tag/v1.1.37.02
Licence text: `AutoHotkey-COPYING.txt`, installed beside the application.

## Fonts

Both are SIL Open Font License 1.1, which is not GPL and imposes no
condition on the application that displays them. Listed because they are
redistributed in the installed tree, which is what triggers the OFL's own
attribution requirement.

### Inter

Version: 4.0
Licence: SIL Open Font License 1.1
Source: https://github.com/rsms/inter
Licence text: `web/fonts/Inter-LICENSE.txt`.
Files: `web/fonts/InterVariable.woff2` (the page) and
`assets/fonts/Inter-Regular.ttf` (preview labels -- Pillow cannot load
woff2, so the same family ships twice in two formats).

### JetBrains Mono

Licence: SIL Open Font License 1.1
Source: https://github.com/JetBrains/JetBrainsMono
Licence text: `web/fonts/JetBrainsMono-OFL.txt`.
Files: `web/fonts/JetBrainsMono-Regular.woff2`.

## Written offer

For either program, we will provide the complete corresponding source code
for the exact version distributed with this application, on request, for a
period of three years from the date you received it. Contact
technical@zoolanders.vip.

The versions above are the exact versions shipped. Pinning matters: an offer
of "the latest upstream release" would not correspond to what you received.
