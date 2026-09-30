# Multiple crops per character: nested stable ids, definition-count cap, hide-bias toggle-all

The crops design deliberately shipped zero-or-one crop per character and
promised the schema would permit more later; issue #272 is that later
feature. Moving to up to four crops per character forces three durable
choices — how a crop is identified once a character owns several, what the
global cap actually counts, and what right-click means over mixed states —
and each is settled here so the schema, the runtime and the Settings page
cannot drift apart.

## Decisions

- **Identity:** crops persist nested by owner — `character → crop id →
  definition` (schema version 2). The crop id is assigned at creation,
  persisted, and never reused or renumbered after a delete; its creation
  sequence is the crop's stable display order ("Crop 1") and its global-cap
  tiebreak order. Migration is lossless: each version-1 entry becomes that
  owner's first crop with region, geometry and enabled state preserved, and
  malformed entries keep being dropped individually. A flat
  `crop id → definition` map with an owner field was rejected (every reader
  filters by owner, and identity becomes a rewrite on any owner change) as
  were user-named crops (rename and uniqueness management for at most four
  entries).
- **Cap accounting:** the global-limit refusal keys off *saved, enabled
  definitions*, not transient live count — creating a new definition is
  refused once 32 enabled definitions exist, so the message is always
  truthful and restart-stable, while runtime suppression continues to apply
  on top (enabled crops whose owner is offline don't hold a live slot).
  `MAX_LIVE_CROPS` rises 8 → 32 as a product decision: 8 was a measured
  prototype gate and 32 outruns it, so a scripted many-crop smoke on real
  multi-client hardware is a human **release gate**, not a merge gate. Live
  slots fill alphabetically by owner, then by crop order — the shipped
  ordering rule extended per crop rather than replaced.
- **Toggle-all:** right-clicking a main preview is hide-biased over saved
  flags — if any of the owner's crops is enabled, all become disabled; if
  none is, all become enabled. This matches the gesture's dominant intent
  ("make these go away") and stays a perfect toggle in the uniform states.
  It is distinct from hide-active (#212), which changes runtime visibility
  only and keeps composing with per-crop enabled flags unchanged.
