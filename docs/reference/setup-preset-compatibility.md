# Physical preset compatibility

## Boundary and behavior

`wingman/evesettings/setup_documents.py` normalizes two client-proved physical
DAT representations in fresh projections, before existing model validation:

- A preset definition may omit `alwaysShownStates`; the projection supplies a
  fresh empty list. `groups` and `filteredStates` remain required. Explicit null,
  false, malformed lists, unsupported fields and aliases still refuse.
- Ship-label `bold`, `italic` and `underline` may contain exact integer `0`,
  projected as boolean `False`. Exact integer `1` for `underline` projects as
  boolean `True`. Already-supported integer `1` for bold/italic stays integer
  `1`; booleans and optional field absence remain unchanged. This is not general
  truthiness admission: other integers, floats, strings and containers refuse.

The public portable JSON model is unchanged: it still requires explicit
`alwaysShownStates` and refuses integer `0` style flags and underline integer `1`.
Native YAML and the generic codec have not been relaxed. Source dictionaries,
label order/multiplicity, effective unsaved-generation precedence, resource
budgets and canonical-body fingerprints retain their existing contracts.
Equivalent recipient records keep their original physical representation and
stamp; differing supported content is written explicitly by the existing writer.
Fingerprints validate supplied bodies, never reconstruct missing bodies.

## Static client evidence

Observed on 2026-09-08 by read-only static inspection of selected public client
archive members. No client code was executed, imported or vendored. Inspection
used ZIP reads, zlib decompression and xdis Python 2.7 bytecode disassembly
(magic 62211, marshal body after the eight-byte pyc header). xdis is not an app
dependency.

Archive `C:/CCP/EVE/tq/code.ccp` SHA-256:
`8c258c1b840470f6ea10b58af2dde858feabffb619f468450e19adbc71160013`.

| Member | SHA-256 |
| --- | --- |
| `overviewPresets/overviewSettingsConst.pyj` | `3a6e13df79225ac0ea8fd92bd87f55fc62bc6dd53cb02b409a0be215048f721a` |
| `eve/client/script/parklife/overview/presetservice.pyj` | `eb6f226d8b9ad2c4db54831c36ae2b7a99f449aa7c6b0e586ddbcfd1a2789115` |
| `eve/client/script/parklife/bracketMgr.pyj` | `7e81ad2fe062d1ee00e706c612c9bd51dea98bee062539ca18a37b51ae279a63` |
| `eve/client/script/ui/inflight/bracketsAndTargets/bracketNameFormatting.pyj` | `6d1f1c295b81543fd062801be399dcf573a68c03a702e1d5dfbeffb6bc64735c` |

- `overviewSettingsConst` binds the always-shown setting constant to
  `alwaysShownStates`.
- `presetservice.GetAlwaysShownStates` (source start 369, return 371) and
  `GetAlwaysShownStatesByPresetKey` (start 388, return 392) use dictionary lookup
  with an empty-list default for that field. `GetPresetFromKey` (start 323)
  returns an existing nonempty saved/unsaved record; its whole-preset fallback
  does not apply to a record containing the other two lists. Explicit invalid
  values are not replaced by the missing-key default.
- `bracketMgr.GetDisplayNameWithShipLabels` (start 434, offsets 600–705) obtains
  each formatting flag with a false default and passes it to the formatter.
- `bracketNameFormatting.TagWithBold` (start 5), `TagWithUnderLine` (start 10)
  and `TagWithItalic` (start 15) truth-test the flag: false leaves the labels
  unchanged; true applies the respective tag. This establishes the effects of
  exact integer zero and one used by the narrow DAT adapter rules above.

## Verification limits

Regressions use invented source/recipient documents and the already-public
canonical body in `tests/test_ui_setup_v24.py`. The native integration regression
exercises export, review, new-profile creation, codec encoding/readback and
re-export, including actual output booleans and unchanged original test files.
Neither those tests nor static client inspection establish live EVE reload,
new-profile acceptance or admission of any preset library content. Private
captures are not repository fixtures and are not modified by this correction.
