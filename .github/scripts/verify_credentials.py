"""Verify injected OAuth credentials are well-formed.

Run after the "Inject OAuth credentials" step in
.github/actions/build-installer/action.yml has rewritten
wingman/credentials.py. The importability check earlier in
that action runs BEFORE injection, so nothing else validates
credentials.py after it is rewritten. A secret carrying a trailing space
still produces a syntactically valid file that builds green and is then
rejected by Google at sign-in as "the provided client secret is invalid"
-- with no CI signal at all.

Prints only shapes and lengths, never the values.

Must run via `uv run python packaging/verify_credentials.py` so it
imports wingman from the synced .venv, not the runner's
bare interpreter.
"""

import sys

from wingman import credentials as c

cfg = c.CLIENT_CONFIG["installed"]
cid, sec = cfg["client_id"], cfg["client_secret"]
bad = []

if c.is_placeholder():
    bad.append("is_placeholder() is still True -- the replace did not take")
if cid != cid.strip():
    bad.append("client_id has leading or trailing whitespace")
if sec != sec.strip():
    bad.append("client_secret has leading or trailing whitespace")
if not cid.endswith(".apps.googleusercontent.com"):
    bad.append("client_id does not end with .apps.googleusercontent.com")
if chr(10) in cid or chr(10) in sec:
    bad.append("a value contains a newline")
if not sec:
    bad.append("client_secret is empty")
if " " in sec:
    # Observed for real: the stored secret was the text of a
    # `gh secret set ...` command rather than the value it was
    # meant to set. Google then rejects sign-in with "the provided
    # client secret is invalid" and nothing upstream notices,
    # because a shell command is a perfectly valid Python string.
    bad.append(
        "client_secret contains a space -- it looks like a "
        "command line or a pasted phrase, not a secret"
    )
if not sec.startswith("GOCSPX-"):
    # Google issues desktop-app secrets with this prefix. A value
    # without it is not necessarily wrong, but it has never been
    # right here, so fail loudly rather than ship it.
    bad.append(
        "client_secret does not start with GOCSPX- , which "
        "every Google desktop-app secret does"
    )

print(f"client_id: {len(cid)} chars, ends {cid[-30:]!r}")
print(f"client_secret: {len(sec)} chars, starts {sec[:7]!r}")

for b in bad:
    print("::error::" + b)
sys.exit(1 if bad else 0)
