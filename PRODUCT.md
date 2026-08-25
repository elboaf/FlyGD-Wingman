# PRODUCT.md

What FlyGD Wingman is, who it is for, and what belongs in it.

`DESIGN.md` says how the window is built. This says what it is — the
question that has to be answered before "should this be a destination?"
can be. It was not written down for the first four features, and the
result was that every one of them was added as a peer of the Uploader
without anyone deciding it should be.

`register: product` — the UI serves the tool; it is not the product.


## What it is

**An EVE Online multiboxing toolkit for wormhole space, which also uploads
your fight footage to YouTube.**

The README still describes it the other way round — an OBS-to-YouTube
uploader with EVE extras — and mentions none of Bookmarks, Previews,
Skills or Profiles. That framing is out of date and should not be used to
decide anything.

The order matters because it settles arguments. A feature that helps
someone fly several accounts through wormhole space belongs here. A
feature that improves video uploading in general does not, unless it
happens to serve the first.


## Who it is for

People who fly **multiple EVE accounts at once, in wormhole space**, and
record their fights.

The domain vocabulary is the evidence and the audience test. The default
keybinds are `Set Root`, `Grab Sig ID`, `Finisher: C1`–`C6`,
`Finisher: C13 (shattered)`, `e Tag (end of life)`, `/ Tag (half mass)`,
`f Tag (frig hole)`, `c Tag (critical)`, `Convert EvE-Scout Bookmarks`.
None of that is explained anywhere in the app, and it should not be. If a
reader needs "what is a frig hole" answered, they are not the user.

So: **assume fluency.** Do not explain EVE. Do explain Wingman — where a
folder is, why a keybind did not register, what a settings profile is
about to overwrite.

Specifically, **FlyGD**. The bookmark workflow encodes one group's
conventions and does not have to be neutral about them: the finisher
scheme, the tag letters and the EvE-Scout conversion are house style, and
naming them plainly beats generalising them into something nobody
recognises.

It is GPL-3.0 and public because **other groups are welcome to fork it for
their own conventions**. That is a design constraint, not just a licence:
where house style is baked in, it should be somewhere a fork can change
without unpicking logic. `bookmarks.py`'s `BIND_LABELS` and
`RECOMMENDED_BINDS` are the current example — a table near the top of one
module, which is the right shape. Keep it that way.


## What is primary

Three things, equally:

- **Uploading fight footage** — the original app, and the only thing that
  touches a Google account.
- **Client previews** — what makes flying several accounts at once
  possible.
- **Bookmark keybinds** — wormhole mapping and rolling, and the only
  feature that runs continuously in the background.

Then, well behind: **Profiles and Skills**. Fleet-preparation work, done
occasionally in a block and then not thought about for weeks.

None of the three outranks the others. A change that helps one at the
clear expense of another needs a reason.

### Importance is not the same axis as frequency

The three co-primaries are the proof, and this is the rule that was
missing when the title bar filled up:

| | how important | how often *visited* | where it lives |
|---|---|---|---|
| Uploading | primary | constantly | a destination |
| Previews | primary | twice, ever | a Settings section |
| Bookmarks | primary | twice, ever | a Settings section |
| Skills | secondary | rarely | a destination |

Two equally primary features are Settings sections and a secondary one is
a destination. That is not an inconsistency, it is the actual rule:

**Does the user come here to *do* something and stay, or to *set something
up* and leave?** The first is a destination. The second is a Settings
section, however important the feature is.

Previews and Bookmarks are as important as uploading and are still
configuration, because neither produces anything on its own screen — they
configure keybinds that fire in EVE and windows that appear on the
desktop. Skills is less important and is still a destination, because
checking a roster against a doctrine is something you sit and do.


## What it must not become

- **It must not set a running EVE client's position or size.** Not moved, not
  resized, not repositioned. EVE reads a resize as a resolution change and
  rewrites its own configuration; a test once destroyed three characters'
  settings that way. Previews are separate windows that mirror a client.
  Exactly two show-state calls are exempt, and no others: `SW_RESTORE` on
  activation, already shipped, and minimize, for the opt-in
  minimize-inactive setting. Maximize is NOT exempt — `SW_SHOWMAXIMIZED`
  fills the window to the work area, the same geometry hazard in
  show-state clothing. This is a hard line, not a preference.
- **It must not upload anything the user did not select.** Nothing leaves
  the machine without an explicit action.
- **It must not automate gameplay.** It sends keystrokes the user pressed,
  to a window the user is looking at. It does not act for them.
- **It must not require the EVE tools to upload a video**, or a Google
  account to use the EVE tools. The two halves must stay independent.


## Tone

Plain, specific, and short. This is a utility used beside a game, often
mid-fleet, on a second monitor.

- Say what happened and what to do. "That folder does not exist." — not
  "An error occurred."
- Never apologise, never pad. There is no room for a sentence that only
  restates a heading.
- Name things the way the user does. "Profiles", not "settings sets".
  "Keybind", not "chord" or "gesture".
- State cost before an irreversible action, with the real number in it.


## Constraints

Windows only. A tray app that starts hidden, in one frameless window, dark
only. Minimum **840x625 CSS pixels, at every display scaling** — the
minimum resolves in logical units, so the viewport floor is the same
number at 100% and at 200%. `DESIGN.md` carries the measurement and the
correction it replaces.

Free and open source, GPL-3.0. No telemetry. No account except the user's
own Google account for their own uploads, and their own Discord webhook.

No framework, no build step. Nothing in the repository executes the page,
so every UI change needs a hand pass against `docs/smoke-checklist.md`.
