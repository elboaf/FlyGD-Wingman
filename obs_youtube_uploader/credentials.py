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
    """True when running from source without real credentials injected."""
    return CLIENT_CONFIG["installed"]["client_id"] == _PLACEHOLDER_ID
