<p align="center">
  <img src="docs/assets/wingman-logo.png" alt="FlyGD Wingman" width="180">
</p>

<h1 align="center">FlyGD Wingman</h1>

<p align="center"><strong>Your wormhole multiboxing wingman.</strong></p>

<p align="center">
  <a href="https://wingman.zoolanders.vip/">Website</a> ·
  <a href="https://github.com/elboaf/FlyGD-Wingman/releases">Download</a> ·
  <a href="https://wingman.zoolanders.vip/privacy">Privacy Policy</a> ·
  <a href="https://wingman.zoolanders.vip/terms">Terms of Service</a>
</p>

FlyGD Wingman is a free, open-source Windows desktop application for flying
several EVE Online accounts at once in wormhole space. It sits in your system
tray and gives you one window for the things that surround a fleet: bookmark
keybinds for mapping and rolling, live previews of your running clients, and a
way to get the footage you just recorded onto YouTube.

Three things it does, in no particular order:

- **Bookmark keybinds** for wormhole mapping — Set Root, Grab Sig ID, class
  finishers, lifecycle tags, EvE-Scout conversion.
- **Live previews** of every running EVE client, so you can watch and switch
  between accounts without alt-tabbing.
- **Uploads your OBS recordings to YouTube**, optionally stitched, optionally
  with the EVE combat logs covering them posted to Discord.

Nothing is uploaded until you select it and press the button, and Wingman never
touches a running client's window.

The upload half works with any OBS recording and needs no EVE install; the EVE
half needs no Google account. Neither requires the other.

<p align="center">
  <img src="docs/assets/wingman-screenshot.png" width="850"
       alt="The FlyGD Wingman window: a dark, frameless title bar carrying the app's destinations and a settings gear. The Uploader is a two-pane layout: the left pane lists OBS recordings with filename, how long ago each was modified, size and length; the right pane has Upload — title, description, a stitch option and a combat-log option — above Publish, with the destination channel and buttons to upload the selection, retry, or delete.">
</p>

## What Wingman does

- **Watches your OBS recording folder.** The folder is detected from OBS
  Studio's own configuration on first run; you can also point it anywhere.
- **Notifies you when a recording is ready** — a tray notification by default,
  or it can raise the window immediately.
- **Lists your recordings** with filename, date, size, and duration.
- **Stitches a selection into one video** (via bundled FFmpeg), earliest
  recording first.
- **Uploads what you select to your YouTube channel**, with a title,
  description, privacy setting, and category you control. Uploads are
  resumable and retry transient network failures.
- **Shows the resulting YouTube link** in the list, with Copy and Open buttons.
- **Deletes recordings from your local disk** after an explicit confirmation.
  This only ever touches local recording files, never anything on YouTube.
- **Bundles EVE Online combat logs to Discord** — optional, and unrelated to
  your Google account. See
  [Discord & EVE combat logs](#discord--eve-combat-logs).

### The EVE tools

- **Bookmark keybinds.** Eighteen actions for wormhole mapping and rolling —
  Set Root, Grab Sig ID, a finisher per class (C1–C6, C13 shattered, HS/LS/NS),
  the lifecycle tags (end of life, half mass, critical, frig hole), and
  EvE-Scout bookmark conversion. Registered globally but scoped to the EVE
  windows you enable, so they do nothing in your browser. Runs on a bundled
  AutoHotkey engine.
- **Live client previews.** A small always-on-top mirror of each running EVE
  client. Click one to switch to that client; drag to move, drag the corner to
  resize, and positions are remembered per character. Per-character keybinds
  and cycle-forward / cycle-back chords work from any application. Wingman
  never moves or resizes the game window itself — EVE reads a resize as a
  resolution change and rewrites its own configuration.
- **Profiles.** Copy one character's or account's EVE settings onto others,
  with a backup taken first and restore available.
- **Skills.** Per-character readiness against skill plans you keep in a folder,
  read through EVE SSO and ESI. Shows what is trained, training, or missing.
- **Fittings.** A persistent local library built from the Personal Fittings on
  the EVE characters you authorize. Equivalent loadouts are consolidated even
  when their names or numbered slot positions differ; you can curate names and
  collections, then explicitly copy selected fits to selected characters.

Profiles, Skills, and Fittings are secondary fleet-preparation destinations.
The EVE tools are on by default. If you only want the uploader, turn them off in
**Settings → General** and Profiles, Skills, Fittings, and the EVE Settings
sections are hidden; the window drops to the Uploader alone.

### EVE authorization, Skills, and Fittings

Settings → Characters is the only place to authorize, reconnect, or forget EVE
characters.

Wingman can hold these four CCP scopes across Skills and Fittings:

```text
esi-characters.read_skills.v1
esi-skills.read_skillqueue.v1
esi-fittings.read_fittings.v1
esi-fittings.write_fittings.v1
```

The first two scopes power Skills. The fitting read scope imports a
character's Personal Fittings. The fitting write scope is used only after you
select library entries, select target characters, review the exact
remote-write count, and confirm the copy. Wingman does not continuously
synchronize fits, never automatically deletes or replaces a fit on a
character, and does not call ESI's remote fitting-delete route.

Existing Skills-only consent remains valid for Skills. A character stays
**Skills only** in Fittings until you reconnect that same character from
Settings → Characters and add the fitting scopes.

Wingman matches the character EVE returns against the sign-in that started the
flow, not against a specific scope combination. If Wingman already knows that
character's owner and EVE returns a different one, the sign-in is refused. If
no owner is saved yet, the returned owner is accepted for compatibility with
older Skills-only records.

If you cancel before EVE replies, the cancellation wins. If EVE replies first,
that reply wins and the later cancel is ignored.

EVE exposes Personal Fittings, not alliance or corporation fittings. To bring
an alliance doctrine into Wingman:

1. Copy it to one character's Personal Fittings in EVE.
2. Refresh that character in Wingman.
3. Use the recent import and source character to identify the new entries.
4. Add those entries to an `Alliance` collection and curate their names or
   descriptions as needed.

A fitting create can time out after EVE received it but before Wingman received
the response. That result is **Unknown**, not Failed. Wingman does not retry
it: the fitting/character pair remains blocked until a fresh authoritative read
after EVE's five-minute cache horizon proves whether the fitting exists. This
prevents an automatic retry from creating a duplicate.

**Forget character is global from Settings → Characters.** It removes that
character's shared EVE credential and its Skills and Fittings snapshots.
Library entries learned from the character remain. If an Unknown fitting write
is still unresolved, Forget is refused until reconciliation so the evidence and
credential needed to resolve it are not discarded. If cleanup is only partly
saved, Wingman keeps the character blocked from being added again until
reconciliation proves what survived.

Fittings state is local and persistent under `%LOCALAPPDATA%\FlyGD Wingman\`:

- `eve_authority.json` holds shared character identity, granted scopes, and
  DPAPI-protected refresh credentials;
- `eve_skills.json` holds Skills-only snapshots and selections;
- `eve_fittings.json` holds the curated library, collections, character
  presence, snapshots, and unresolved write evidence; and
- `eve_fittings_names.json` is a rebuildable type-name cache.

As with the rest of Wingman, there is no FlyGD backend and no telemetry.

## Typical workflow

This is the upload path. The bookmark keybinds and client previews are set up
once in Settings and then used in-game; they need nothing from this flow.

1. You record something in OBS Studio.
2. Wingman notices the finished recording and notifies you.
3. You click the tray icon to open the window.
4. You tick the recording(s) you want.
5. Optionally tick **Stitch selected videos** to merge them into one.
6. You fill in a title and description and press **Upload**. Leave **Also
   post combat logs to Discord** ticked to have Wingman collect the EVE
   logs covering the recording and post them alongside.
7. Wingman uploads directly to your YouTube channel — on first upload it opens
   your browser so you can sign in to Google and grant permission.
8. The **Link** column marks the row with ↗. Right-click it to **Copy link**
   or **Open in browser**, or just double-click the row.

## Google & YouTube access

Wingman requests exactly one Google OAuth scope:

```
https://www.googleapis.com/auth/youtube.upload
```

In plain English: this permission lets Wingman upload video files you have
selected to the YouTube channel of the Google account you signed in with. It
is the narrowest scope that allows a video upload, and it is the only scope
the application asks for.

**Why it is required.** Uploading a video is the application's core purpose.
The YouTube Data API endpoint Wingman calls is
[`videos.insert`](https://developers.google.com/youtube/v3/docs/videos/insert),
which requires this scope. Wingman makes no other YouTube API call.

**What this means in practice:**

- **Uploads only happen when you start them.** Wingman never uploads
  automatically. A video is uploaded only after you select it and press
  **Upload**. If you configured a Discord webhook, matching combat logs are
  posted there after the video publishes. Detecting a new recording produces
  a notification and a list entry — nothing more.
- **Sign-in only happens when you ask for it**, either via
  **Settings → Connect Google Account** or automatically at the moment of your
  first upload if you have not connected yet.
- **Wingman does not request access to Gmail**, Google Drive, Google Contacts,
  Google Photos, or your Google profile.
- **Wingman does not request the broader `youtube` or `youtube.force-ssl`
  scopes**, so it has no access to your viewing history, subscriptions,
  playlists, comments, or analytics. The only YouTube API method it calls is
  `videos.insert` — it never lists, reads, edits, or deletes anything already
  on your channel.
- **Your Google credentials are stored locally**, on your own computer, by the
  desktop application. See [Where credentials live](#where-credentials-live).
- **No FlyGD-operated backend receives Google OAuth tokens or other
  application data.** See the [Privacy section](#privacy) network table for
  the external services each feature contacts and what it sends.
- **Video data goes straight from your computer to Google.** The upload is a
  resumable upload made by the application to the YouTube Data API. It does
  not pass through any FlyGD-controlled infrastructure.

### OAuth flow

Wingman uses Google's OAuth 2.0 flow for **installed / desktop applications**.
Pressing **Connect Google Account** opens your default browser at Google's
consent screen; Google redirects back to a temporary loopback listener
(`http://localhost` on an ephemeral port) that the application starts for the
duration of the sign-in and then shuts down. The client configuration embedded
in official builds is a desktop-application OAuth client, for which Google
documents that the client secret is not treated as confidential — the flow's
security comes from the loopback redirect and your own consent.

### Where credentials live

The resulting credentials — including the refresh token, so you do not have to
sign in again on every launch — are written to a JSON file in your Windows
user profile:

```
%LOCALAPPDATA%\FlyGD Wingman\token.json
```

To be precise about what that does and does not give you: the file is stored
in your per-user profile directory, and the application asks the operating
system for owner-only permissions on it. On Linux and macOS (used for
development and CI) that request is enforced. **On Windows it is not** —
Python's `os.chmod` only toggles the read-only attribute there and does not
set a real ACL. The file is **not encrypted**, and Wingman does **not** use
Windows Credential Manager or DPAPI. Treat it as a plaintext credential
sitting in your user profile: anyone who can read your profile directory, or
who is an administrator on the machine, can read it.

### Revoking access

You can revoke Wingman's access at any time from your Google Account:
**Google Account → Security → Your connections to third-party apps &
services**, or directly at
[myaccount.google.com/connections](https://myaccount.google.com/connections).
Removing access there immediately invalidates the stored token. You can also
simply delete `%LOCALAPPDATA%\FlyGD Wingman\token.json` to sign out
locally.

### YouTube Terms of Service

Wingman uploads through the YouTube Data API, so videos you upload with it are
subject to the [YouTube Terms of Service](https://www.youtube.com/t/terms) and
the [YouTube Community Guidelines](https://www.youtube.com/howyoutubeworks/policies/community-guidelines/).
The link to YouTube's terms is also shown in the application itself, in
**Settings → Google account**, next to the sign-in button.

For the full data-handling statement, see the
[FlyGD Wingman Privacy Policy](https://wingman.zoolanders.vip/privacy).

## Discord & EVE combat logs

This feature is optional, off until you configure it, and **completely
separate from Google sign-in**. It uses no Google credentials and sends no
Google user data anywhere.

When a Discord webhook is configured, an upload does a second thing once the
video is published: it works out the time span the selected recordings cover,
collects the EVE Online gamelog files from your local `Gamelogs` folder that
overlap that span, zips them, and posts the archive to the webhook URL you
entered in Settings. That is the entire scope of the feature: local EVE log
files, to a Discord channel you chose. Remove the webhook in Settings to upload
videos without posting combat logs to Discord.

Notes:

- EVE writes log timestamps in UTC, and the window is computed in UTC, so it
  can look offset from your system clock by your local UTC offset. That is
  expected.
- Discord caps webhook attachments at 10 MB. A realistic 16-log archive from
  one fight compresses to roughly 38 KB, so this rarely comes up. If it does —
  or if the post fails for any other reason — the archive is kept on disk and
  its path is shown so you can upload it by hand. It is deleted only after a
  successful post.

> **A Discord webhook URL is a bearer credential.** Anyone who has it can post
> to that channel, it never expires, and the only way to revoke it is to delete
> the webhook in Discord. Wingman stores it in plaintext in `settings.json` and
> redacts it from its own log file, but that does not help if you paste it
> elsewhere. Do not post it publicly or leave it visible in a screenshot.

## Installation

1. Download the latest installer from the
   [Releases page](https://github.com/elboaf/FlyGD-Wingman/releases).
   It is named `FlyGD-Wingman-Setup-<version>.exe`; releases published before
   the rename are named `OBS-YouTube-Uploader-Setup-<version>.exe`.
2. Run it. It installs per-user, so there is no administrator prompt.
3. Launch Wingman. It appears in the system tray. Connect your Google account
   when you make your first upload, or up front via **Settings → Connect
   Google Account**.

Python, FFmpeg, and the OAuth client configuration are bundled — there is no
separate OBS script to install, and no Google Cloud project for you to set up.

Once each time Wingman starts, it checks the GitHub release API in the
background for a newer stable release. If one is available, the Settings gear
shows a dot and **Settings → General → About Wingman** offers **Download
update**. **Check again** repeats only the release check; the installer is not
downloaded until you choose **Download update**, and it is never installed
until you confirm. Wingman checks the downloaded size and GitHub-published
SHA-256 before opening the normal visible installer. That SHA-256 provides
same-channel integrity — it confirms that the download matches GitHub's
release record — but it does not prove publisher identity because the asset
and digest come from the same source.

**Windows will warn you** that it "protected your PC": the installer and the
application are not code-signed. Guided updates keep this warning and the
visible installer rather than bypassing either one. Click **More info** → **Run
anyway**. This happens once per machine, for the installer and for the first
launch. This is about code signing, and is unrelated to Google sign-in.

## Settings

Settings open from the gear in the title bar and are grouped down the left.
There is no Save button: every field applies as you set it. Folder paths and
the webhook apply on **Enter** or from their own buttons, so a half-typed path
is never acted on.

| Setting | Default | Notes |
|---|---|---|
| Show the EVE tools | on | Off hides Profiles, Skills, and the two EVE sections. Only switchable off while both EVE features are off, so it can never hide a running feature's off switch. |
| Privacy | `unlisted` | `private`, `unlisted`, or `public` |
| Category ID | `20` (Gaming) | [YouTube category IDs](https://developers.google.com/youtube/v3/docs/videoCategories/list) |
| When a recording finishes | Tray notification | Or open the uploader window immediately |
| Recording folder | auto-detected from OBS | Browse or re-detect at any time |
| Gamelogs folder | auto-detected | Usually `Documents\EVE\logs\Gamelogs` |
| Discord webhook | *(none)* | Channel → Integrations → Webhooks → Copy URL. Treat it like a password. |
| Bookmark keybinds | off, one bound | Enabling starts the AutoHotkey engine. Only EvE-Scout conversion ships bound; the rest are yours to set. |
| Client previews | off | Enabling starts a discovery sweep and a foreground hook. |
| Reopen previews in place | on | Off opens each preview in a default stack instead. Positions are remembered either way. |

Settings are stored at `%LOCALAPPDATA%\FlyGD Wingman\settings.json`.

## Privacy

Wingman is local-first. It has no backend, no account system, no analytics,
and no telemetry. Everything it stores — your settings, your Google OAuth
token, its log file, and temporary stitched video files — lives under
`%LOCALAPPDATA%\FlyGD Wingman\` on your own machine.

These features make the following network connections:

| Destination | When | What is sent |
|---|---|---|
| GitHub release APIs and release downloads | Wingman's release API is checked once each time Wingman starts, including when Windows starts it hidden at sign-in. **Check again** repeats that check and **Download update** explicitly downloads its installer; there is no polling or automatic download. Separately, FightRecorder stays local until you choose **Check for updates**, **Install**, or **Update** on its Settings card; those actions check its GitHub release and Install/Update downloads the plugin DLL. | The automatic Wingman check identifies the installed Wingman version in its User-Agent, and each request carries ordinary network connection metadata and identifies the repository or release asset requested. FightRecorder checks do not send the installed plugin version. No Wingman settings, EVE or Google account data, filenames, recordings, or telemetry are sent. |
| CCP EVE SSO and ESI (`login.eveonline.com`, `esi.evetech.net`) | You authorize or reconnect a character from Settings → Characters; Wingman refreshes that character's skills, queue, and attributes, refreshes its Personal Fittings when you ask Fittings to do so, or resolves uncached skill plans through unauthenticated universe ID/name (`/universe/ids`), type metadata, and group metadata lookups. Profiles looks up local character IDs first through unauthenticated `/characters/{id}/` requests, then uses `/universe/names` for remaining display names. | EVE SSO receives Wingman's registered client ID, redirect URI, requested read-only skills/queue scopes, requested fitting read/write scopes, and PKCE values, then the authorization code or stored EVE refresh token at its token endpoint. Authenticated ESI skills, queue, and attributes requests carry the character ID and EVE bearer access token. Authenticated ESI fitting reads and writes carry the character ID and EVE bearer access token. Unauthenticated name and metadata lookups carry skill names, type/group IDs, or the Profiles character IDs being resolved, with no EVE token. Wingman does not send CCP its settings, local EVE `.dat` files, Google credentials, Discord webhook or combat logs, filenames, or recordings. |
| Google / YouTube APIs | You sign in, or upload a video | OAuth sign-in, and the video files you selected plus the title, description, privacy, and category you set |
| A Discord webhook you configure | You press **Upload** while a webhook is configured, after the video publishes successfully | A zip of the local EVE log files covering the selected recordings, plus a short summary message |

Your Google account data and OAuth token go only to Google, never to Discord,
GitHub, or CCP. EVE tokens go only to CCP's EVE SSO and ESI endpoints. Full
statement:
[Privacy Policy](https://wingman.zoolanders.vip/privacy) ·
[Terms of Service](https://wingman.zoolanders.vip/terms).

## Upload limits

YouTube upload capacity is governed by the YouTube Data API quota granted to
this project. That quota is **per project and shared across every user of the
application**, not per Google account, so heavy use by one person can exhaust
it for everyone else until it resets (daily, at midnight Pacific Time). When
that happens, Wingman recognises the API's `quotaExceeded` response and says
so in plain language rather than showing an error code — wait until the
following day.

A second, separate limit applies to **your own channel**: YouTube caps how
many videos one channel may upload per day, and rejects the video with
`uploadLimitExceeded` once you pass it. This one affects only you, not other
users of the app, and it is reported separately. The cap is tightest on
channels that are new or not phone-verified — verifying at
[youtube.com/verify](https://www.youtube.com/verify) raises it (and lifts the
15-minute limit on video length). The allowance resets, so wait a day and
upload again.

## Upgrading from 1.x

1. In OBS, open **Tools → Scripts** and remove the old script (`obs_trigger.py`
   or similar). It is no longer used — the tray application watches the
   recording folder directly.
2. Uninstall or delete your old checkout; it is not needed once the tray
   application is installed.
3. After installing, open **Settings → Connect Google Account** and sign in
   once. Old `client_secrets.json` and token files are not reused — there is no
   migration of stored credentials or settings.

## Building from source

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
python -m wingman
```

CI gates on all three: the suite, `ruff check`, and `ruff format --check`.
Running the format check locally is worth the second it takes — otherwise
the first you hear of it is a red pull request.

### After cloning

```
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

The repository was reformatted with `ruff format` in one commit touching
136 files. Without this setting, `git blame` attributes all of them to
that reformat rather than to whoever wrote the code. The setting is
per-clone and cannot be committed, so every clone needs it once.

Official releases are built in two ways. The primary path is
[`.github/workflows/autorelease.yml`](.github/workflows/autorelease.yml):
merge a bump of `__version__` in `wingman/__init__.py` to `main`, and the
workflow tests, builds and publishes the release, creating the `vX.Y.Z` tag
itself — publishing pauses for an approval click if the `release` GitHub
environment has reviewers configured. The fallback path is
[`.github/workflows/release.yml`](.github/workflows/release.yml), which
triggers on a manually pushed `v*` tag. Both inject
the project's own Google OAuth desktop-client configuration from repository
secrets at build time. **Those credentials are never committed to this
repository** — `wingman/credentials.py` contains only
placeholders in the source tree.

So a build from source has no working Google OAuth client until you supply your
own. To run YouTube uploads end to end you need to create a Google Cloud
project, enable the YouTube Data API v3, create an **OAuth client ID of type
"Desktop app"**, and put its client ID and secret into `CLIENT_CONFIG` in
`wingman/credentials.py`. Everything except **Connect Google Account** works
without this. Do not commit real credentials back to the repository.

The EVE application is a separate external release prerequisite. The client ID
and exact loopback redirect are defined in `wingman/eveauth/application.py`.
Before publishing a build, the corresponding application registration at
EVE Developers must accept all four scopes used by Wingman, including both
`esi-fittings.read_fittings.v1` and `esi-fittings.write_fittings.v1`. Changing
the source scope list cannot widen what the registered application accepts. A
fork should register its own EVE application and replace the client ID rather
than ship under Wingman's identity.

As of 4.0.0, the Python package directory, the executable name, and the
`%LOCALAPPDATA%` state folder are all named `wingman` / `FlyGD Wingman`,
matching the product name. Earlier releases kept the old
`OBSYouTubeUploader` identifiers unchanged after the product was first
renamed, so that existing installs would stay upgradeable without extra
migration code. 4.0.0 retires that constraint instead of carrying it
forward: the installer uninstalls a 3.x install by its old identity before
installing the new one, and the app migrates
`%LOCALAPPDATA%\OBSYouTubeUploader\` to `%LOCALAPPDATA%\FlyGD Wingman\` on
first launch, so upgrading from 3.x keeps your settings and sign-in
automatically.

Packaging lives in [`packaging/`](packaging/) (PyInstaller spec and Inno Setup
script). Manual pre-release verification steps are in
[`docs/smoke-checklist.md`](docs/smoke-checklist.md).

CI reports on every pull request but does not *gate* one until branch
protection is configured, which is a repository setting and cannot be
committed. The procedure is in
[`docs/branch-protection.md`](docs/branch-protection.md) — until it is
applied, a pull request with a red Windows leg is still mergeable.

## Support

- Bugs and feature requests:
  [GitHub Issues](https://github.com/elboaf/FlyGD-Wingman/issues)
- Email: [technical@zoolanders.vip](mailto:technical@zoolanders.vip)
- Product information: [wingman.zoolanders.vip](https://wingman.zoolanders.vip/)

For anything touching your Google account or the data Wingman handles, email is
the fastest route — please do not include tokens, webhook URLs, or other
credentials in a public issue.

## License and affiliations

Copyright (C) 2026 elboaf and the FlyGD Wingman contributors.

Released under the [GNU General Public License, version 3 only](LICENSE) (`GPL-3.0-only`).

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation, version 3.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
General Public License for more details.

FFmpeg and AutoHotkey are bundled and are licensed under the GPL. See
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for versions, sources, and
a written offer of source.

FlyGD Wingman is an independent, unofficial project. It is not affiliated
with, endorsed by, or sponsored by Google LLC, YouTube, the OBS Project /
OBS Studio, CCP hf. / EVE Online, or Discord Inc. Google, YouTube, OBS Studio,
EVE Online, and Discord are trademarks of their respective owners and are used
here only to describe compatibility.

EVE Online and all related logos and images are trademarks or registered
trademarks of CCP hf.
