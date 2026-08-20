# obs_youtube_uploader/credentials.py
"""Embedded OAuth client configuration.

The values below are placeholders in the source tree. The release workflow
replaces this file at build time from a repository secret.

Embedding a desktop-app client secret is expected and sanctioned by Google:
for installed applications the flow's security comes from the loopback
redirect and the user's own consent, not from the secret being confidential.
It is extractable from the binary by anyone who cares, and that is fine.
"""

_PLACEHOLDER_ID = "REPLACE_AT_BUILD_TIME.apps.googleusercontent.com"

CLIENT_CONFIG = {
    "installed": {
        "client_id": _PLACEHOLDER_ID,
        "client_secret": "REPLACE_AT_BUILD_TIME",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "redirect_uris": ["http://localhost"],
    }
}


def is_placeholder() -> bool:
    """True when running from source without real credentials injected.

    The release workflow does a literal string replace of the placeholder
    text across the whole file's text — including the right-hand side of
    `_PLACEHOLDER_ID` above, since that same text appears there too. So
    comparing `client_id == _PLACEHOLDER_ID` always sees two equally
    substituted values in a release build and returns True regardless of
    whether real credentials were injected.

    Instead, assemble the sentinel at runtime from fragments that never
    appear contiguously in this file's source text. The workflow's
    substring replace can only rewrite a literal, unbroken match, so it
    cannot touch a value built from separate fragments joined at runtime —
    that sentinel stays fixed, while `client_id` changes underneath it in
    a real build.
    """
    sentinel = "REPLACE" + "_AT_BUILD" + "_TIME"
    client_id = CLIENT_CONFIG["installed"]["client_id"]
    return client_id == f"{sentinel}.apps.googleusercontent.com"
