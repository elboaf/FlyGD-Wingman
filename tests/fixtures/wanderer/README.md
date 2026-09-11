# Wanderer deployed v1 fixture provenance

Authority: Wanderer commit `2ddff24516c27ecde7b175991fcd74d608a35932`.
Read with `git show <exact-commit>:<path>`, not the checkout's newer HEAD:

- `docs/tracked-character-locations-api.md`
- `lib/wanderer_app/tracked_character_locations.ex` (`records/6`, `locate/8`)
- `lib/wanderer_app_web/controllers/tracked_character_locations_controller.ex`
  (`respond/4`: exact envelope, opaque revision, weak ETag)
- `lib/wanderer_app_web/schemas/tracked_character_locations.ex`
- `test/integration/api/tracked_character_locations_test.exs`
  (exact sorted envelope, hidden/unmapped/raw precedence, unavailable records)
- `test/support/tracked_locations_fixtures.ex`
- `lib/wanderer_app/character/location_confirmations.ex` (strict 15-second age)

`deployed-v1.json` is a synthetic, deterministic reproduction of those executing
serializer/controller tests, not a live capture. IDs, names, timestamps and
revision are fixture values; no real credentials or location history are copied.
The first record reproduces the visible HOME/Jita case. Hidden data contains no
map name or map timestamp. An unmapped system lacking static data has null names,
not a fabricated `System <id>`. Offline and unknown/unavailable records preserve
identity but null every location/map field. Tests also exercise fresh raw fallback,
empty rosters and rejected malformed candidates.

Wingman deliberately rejects ambiguous normalized character identities, unsafe
single-line text, and non-UTC/future record timestamps rather than guessing which
preview to label. These are client hardening checks, not claims that upstream
currently rejects every such source value. A 304 must never rebuild deadlines;
authentication failure must clear cached data immediately (worker task).
