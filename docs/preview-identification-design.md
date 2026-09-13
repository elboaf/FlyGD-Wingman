# Preview identification — approved first slice

## Approval and scope

The maintainer approved this direction in the coordination conversation: "sure, lets start there" after the recommendations below. This is a bounded extension of existing preview labels, not a new appearance editor. Implement #214 first; review it before starting #215. Keep separate reviewable changes for the two issues. #217 is explicitly deferred. Other backlog lanes are not part of this branch.

## #214 — label readability

- Add one global label-size preference with a small set of named presets. Preserve the current rendered size as the default; existing settings must retain the current appearance wherever the current label fits. The legacy-size containment exception below is explicitly approved.
- Keep the character name first and the optional Wanderer system name smaller and secondary.
- Retain top-left placement, existing high-contrast text and backgrounds, and Show labels behavior.
- Do not add custom names, text colors, font selection, free positioning, or per-character size overrides.
- Use the existing click-through label overlay and measurement/render cache. Add no additional native windows, polling, or dependencies.
- Explicitly verify both one-line and two-line labels at minimum supported preview sizes. A size setting must not introduce label pixels outside the owning preview or change any real EVE window geometry.
- Approved legacy-size correction: apply the same height containment to every preset, including Standard on undersized restored previews. Omit the secondary system-name line if it cannot fit in the current interior; hide the entire label pill if even the primary character-name line cannot fit. Restore the omitted content when space permits. Do not resize either Wingman's preview or any real EVE source, crop glyphs, or automatically shrink the selected font. The maintainer approved this exception with "yes, lets apply the correction" after being informed that undersized legacy previews currently overflow. Fitting Standard labels retain their existing pixels.
- Settings transactions must preserve truthful applied/persisted outcomes, and the control must obey hydration and per-field ownership rules. Do not apply runtime effects after a refused persistence transaction.
- Preserve move/resize positioning, alert inset handling, runtime off/on, hiding and click-through behavior. Scope cache invalidation to affected labels.
- Select the exact preset values through current rendering/geometry evidence; retain the existing default value. Record that local implementation decision in the implementation notes.

## #215 — per-character recognition (queued, not part of #214 implementation)

- Add an optional small static color marker inside the character-name label, using a curated palette and a None/reset choice.
- This is a manually assigned identification aid, not a role-management system or ship/role inference.
- Keep the actual character name and text contrast unchanged. The marker supplements text rather than replacing it.
- Allow assignment and reset for known offline characters. Retain configured identities through roster pruning.
- No override preserves the existing appearance. The marker follows Show labels and the owner's visibility.
- Keep selection and alert rings unchanged. Do not add colored full-preview borders, animation, thickness controls, or per-character selection colors.
- Reuse #214's settled measurement/cache behavior and the same existing overlay. Assess marker usefulness at typical and minimum preview sizes rather than assuming visibility.

## Independence from saved layouts

Label-size preferences and per-character identification assignments remain global. They are not switched by #213's saved layouts. The approved #213 first slice saves only primary-preview positions, sizes and per-character visibility; crops, companions, keybinds and appearance remain outside that saved-layout boundary.

## Delivery and verification

Read AGENTS.md, PRODUCT.md and DESIGN.md before implementation. Use isolated worktrees, test-first changes and existing architecture. Keep controller orchestration out of the bridge, preserve explicit handler contracts, and do not refactor unrelated preview lifecycle code.

For #214 cover validation/default compatibility, settings rollback/runtime application, one-/two-line rendering and ellipsis, cache invalidation, hidden-label behavior, and the Settings control. Retain bridge-contract, page-convention and executable JS smoke gates. Run the focused affected tests and normal lint/format gates; full-suite evidence requires Node and the built release settings codec as documented in docs/overview-layout-sharing-verification.md.

Browser-render evidence, Windows automated tests, and actual Windows/WebView2/live-EVE smoke are separate evidence classes. Do not claim one proves another. No automated or manual acceptance has been performed for these new features at design approval.

The coordinator owns independent review, integration and issue closure. Do not push, open or merge PRs, or change issue state during implementation without coordinator authorization.
