# Third-party software in FlyGD Wingman

FlyGD Wingman itself is GPL-3.0-only (see LICENSE). It bundles the
following programs, which are licensed separately. The two executables are
under different GPL versions -- v3 for FFmpeg, v2-or-later for AutoHotkey --
so each carries its own licence text rather than sharing one, and neither
of them is the licence covering Wingman itself. The fonts and the alert
sounds are not GPL at all; they are listed because redistributing them is
what triggers their own attribution requirements.

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

## Alert sounds

Licence: Creative Commons Attribution 4.0 International (CC BY 4.0)
Source: https://notificationsounds.com
Licence text: https://creativecommons.org/licenses/by/4.0/legalcode

Sounds from [notificationsounds.com](https://notificationsounds.com).

Three sounds are bundled as `assets/sounds/`, played when a gamelog alert
fires. CC BY 4.0 requires that modifications be disclosed, so each is
listed with what was changed:

| Shipped as | Original | Modifications |
| --- | --- | --- |
| `alarm.wav` | [get-outta-here](https://notificationsounds.com/notification-sounds/get-outta-here-505) | decoded from MP3 to 16-bit PCM WAV |
| `ring.wav` | [juntos](https://notificationsounds.com/notification-sounds/juntos-607) | decoded from MP3 to 16-bit PCM WAV; truncated from 3.21s to 1.5s with a 150ms fade-out |
| `notify.wav` | [no-problem](https://notificationsounds.com/notification-sounds/no-problem-notification-sound) | decoded from MP3 to 16-bit PCM WAV |

The conversion is not cosmetic: `winsound.PlaySound` plays RIFF/PCM only
and will not accept an MP3. `ring.wav` was shortened because combat alerts
can repeat every second and each new sound replaces the one still playing,
so a 3.21s file could never finish.

CC BY 4.0 is not a GPL licence and imposes no condition on the application
that plays these files. They are listed here because they are
redistributed in the installed tree, which is what triggers the licence's
attribution requirement -- the same reason the fonts above are listed.


## Written offer

For either program, we will provide the complete corresponding source code
for the exact version distributed with this application, on request, for a
period of three years from the date you received it. Contact
technical@zoolanders.vip.

The versions above are the exact versions shipped. Pinning matters: an offer
of "the latest upstream release" would not correspond to what you received.
