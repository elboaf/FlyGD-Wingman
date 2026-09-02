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

## Settings codec (blue-marshal and its dependencies)

`wingman-settings-codec.exe` is Wingman's own wrapper (source in
`packaging/settings-codec/`, covered by Wingman's own GPL-3.0-only licence)
around blue-marshal, and it reads and writes EVE settings files. The
approach and format notes follow eve-wrench (Tim Kunze), used with the
author's consent.

It is a **statically linked** binary, so every crate below is compiled into
it and its licence travels with it. All are MIT or Apache-2.0 dual-licensed;
unicode-ident additionally carries Unicode-3.0.

Version: 1.0.1 (blue-marshal, pinned `=1.0.1` in
`packaging/settings-codec/Cargo.toml`)
Licence: MIT
Source: https://github.com/TrueBrain/blue-marshal-rs
Licence text: `settings-codec-COPYING.txt`, installed beside the
application. One combined file rather than one per crate, generated from
`packaging/settings-codec/Cargo.lock` at build time by
`packaging/settings-codec/collect_licenses.py` — so it cannot drift from
what the release actually links.

Crates linked in, from that lock file: autocfg, base64, blue-marshal,
equivalent, hashbrown, indexmap, itoa, memchr, num-bigint, num-integer,
num-traits, proc-macro2, quote, serde, serde_core, serde_derive,
serde_json, syn, unicode-ident, zmij.

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

Nine sounds are bundled as `assets/sounds/`, played when a gamelog alert
fires. CC BY 4.0 requires that modifications be disclosed, so each is
listed with what was changed:

| Shipped as | Original | Modifications |
| --- | --- | --- |
| `system-fault.wav` | [System fault](https://notificationsounds.com/wake-up-tones/system-fault-518) | decoded from MP3 to 16-bit PCM WAV |
| `obey.wav` | [Obey](https://notificationsounds.com/standard-ringtones/obey-479) | decoded from MP3 to 16-bit PCM WAV; truncated from 2.48s to 1.5s with a 150ms fade-out |
| `sly.wav` | [Sly](https://notificationsounds.com/application-user-interface-ui-sounds/sly-user-interface-sound) | decoded from MP3 to 16-bit PCM WAV |
| `come-here.wav` | [Come here](https://notificationsounds.com/notification-sounds/come-here-notification) | decoded from MP3 to 16-bit PCM WAV |
| `glassy-knock.wav` | [Glassy soft knock](https://notificationsounds.com/wake-up-tones/glassy-soft-knock-379) | decoded from MP3 to 16-bit PCM WAV; truncated from 2.43s to 1.5s with a 150ms fade-out (the dropped tail is below -90 dB) |
| `isnt-it.wav` | [Isn't it](https://notificationsounds.com/standard-ringtones/isnt-it-524) | decoded from MP3 to 16-bit PCM WAV |
| `lovely.wav` | [Lovely](https://notificationsounds.com/standard-ringtones/lovely-441) | decoded from MP3 to 16-bit PCM WAV |
| `slick.wav` | [Slick](https://notificationsounds.com/soft-subtle-ringtones/slick-notification) | decoded from MP3 to 16-bit PCM WAV |
| `your-turn.wav` | [Your turn](https://notificationsounds.com/message-tones/your-turn-491) | decoded from MP3 to 16-bit PCM WAV |

The conversion is not cosmetic: `winsound.PlaySound` plays RIFF/PCM only
and will not accept an MP3. The two long sounds were shortened because
combat alerts can repeat every second and each new sound replaces the one
still playing, so a 2.5s file could never finish.

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
