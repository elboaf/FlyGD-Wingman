# Overview/layout implementation gate reassessment

## Correction

The binding design says **unproven dependencies block the affected case**. The
implementation checkpoint incorrectly escalated uncertainty about selection and
retirement into a universal stop before any document-adapter development.

The domain model remains:

1. Named filter definitions.
2. Each tab's own overview-filter and bracket-filter assignments.
3. Tabs assigned to overview-window groups.
4. Character-local geometry and supported window state.

There is no established single global filter overriding those assignments.
`activeOverviewPreset` is not part of the portable model; its name alone does not
establish whether it represents runtime selection or editor bookkeeping.

## Evidence now available

The operator emptied the existing Test directory; the assistant verified and
recorded that empty baseline before initialization. A subsequent no-change
startup/shutdown control showed no normalized DAT setting-value changes.

Saving the named custom filter then:

- added exactly one definition, retaining all 36 prior definitions unchanged;
- retained default-profile identity/metadata;
- copied the contents of one existing definition exactly;
- changed one tab's overview assignment to the new name;
- added `activeOverviewPreset` with that same name.

This proves the observed creation/reference relationship, not an exhaustive
built-in classifier or a generic cache-reset rule. In particular, identical
contents do not distinguish a custom copy from its built-in source.

The assistant withdrew its unsupported implication that exporting a YAML file
was an in-game settings change. The unrelated EVE client on another profile was
left running for the read-only capture; source byte/membership stability and the
absence of the test character's window were checked. This does not change the
application's stronger publication guard.

Raw captures remain outside Git. An independent architecture assessment read
repository evidence and the capture ledger; its direct reads of the private
aggregate files were permission-blocked. Capture results above come from the
controller's actual capture/comparison runs, not independent reproduction by
that reviewer.

## Case-based dependency matrix

| Area | Safe implementation branch | Unresolved case |
| --- | --- | --- |
| Existing filter records | Preserve unrelated records; retain identical collisions without rewriting stored records | Differing exact-name collision without established custom status must refuse |
| New definitions | Add supported noncolliding custom definitions without replacing the catalogue | Unclassified protected-namespace names must refuse, not become a prefix-based classifier |
| Default identity | Preserve recipient `defaultoverview` metadata | No identity copying/reconstruction from sender data |
| `activeOverviewPreset` | Preserve its value/absence while its named reference remains valid | No guessed first-filter assignment or deletion; concrete dangling/unsupported reference refuses |
| Tab-selection records | Preserve absence and demonstrably unaffected records | Ambiguous invalidation caused by new IDs, ordering, names or grouping refuses that transformation |
| Other metadata | Preserve recipient history/profile metadata and unrelated sections | Do not declare unknown non-null dependencies harmless or wipe sections as a shortcut |
| Window topology | Use active group structure, check all affected stacks; implement cases not requiring retirement | Surplus active windows requiring an unproved retirement operation refuse |
| Stack state | Refuse included/affected non-null stack dependencies | Do not detach mixed stacks or copy sender stack IDs |
| Owned values | Validate known representations; follow approved full-clear versus partial-retain policy | Unsupported actual representations refuse; ordinary booleans do not need exhaustive manual experiments |

Preservation is a conservative policy, not proof that an unknown field is
irrelevant. The implementation must make the accepted preconditions and refusals
explicit and exercise them through tests.

## Development sequence

Resume Task 4 in bounded slices. First implement pure recipient-document
application for the supported branches and explicit refusal of the unresolved
ones. It remains unexposed: no controller endpoint, filesystem publication or GUI
is enabled by this slice.

The complete exporter still owes **all supported custom definitions plus tab
dependencies**. Exporting only referenced definitions, treating every stored name
as custom, or hand-typing a private built-in catalogue is not an authorized
shortcut. Differing custom-name replacement and surplus retirement likewise
remain required functionality, not silently removed release requirements.

The original Task 4 is not complete merely because a guarded subtask passes.
Final whole-feature and live-EVE acceptance remain separate. No further manual
clicks/screenshots are requested by this reassessment; any later request must
identify a specific unresolved behavior and why it is necessary.

## Ruling and cost

Ruling: replace the universal development stop with the case matrix above and
resume pure adapter work — this follows the approved design's affected-case
refusal rule — if a preserved dependency later proves significant, its accepted
case must be tightened or corrected before publication/acceptance. Partial
implementation must not be presented as a narrowed but completed product.
