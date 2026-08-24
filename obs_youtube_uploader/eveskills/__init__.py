"""EVE skill plan readiness: SSO, ESI reads, plan parsing, and scoring.

Twelve of the thirteen modules here are pure or filesystem-only and run
in CI on Linux; only dpapi.py is Windows-only. That split is deliberate
and matches preview/ -- the logic worth testing must not be trapped
behind an API that only exists on the build machine.
"""
