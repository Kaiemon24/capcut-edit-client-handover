# Project identity and style-specific naming

| Need | Path | Rule |
|---|---|---|
| Reuse a known name | [Known task identity](#known-task-identity) | Preserve exact supplied display names and retained answers. |
| Ask only missing values | [Style naming policy](#style-naming-policy) | Use the selected style's own template, not another style's convention. |
| Find or create the project | [Resolve and create](#resolve-and-create) | Separate naming metadata, real destination, creation authority and native proof. |
| Prepare metadata safely | [Helper and checks](#helper-and-checks) | The helper asks/proposes only; it never creates or authenticates a draft. |

## Known task identity

For EDIT_TIMELINE, first distinguish creating a NEW project from locating or revising an existing one. Bind `projectIdentity.intent: CREATE` for new-name preparation; `LOOKUP_EXISTING` (with LOOKUP/EXISTING compatibility aliases) means metadata lookup only, never creation or revision authority. Reuse a safe exact legacy name for existing lookup and preserve the actual immutable baseline name for owned revision, even if it predates the new format. Never rename an existing project merely to retrofit naming. An explicit new full name retains its spelling and prefix only when it passes the new-name contract below; report a precise conflict instead of silently stripping a suffix or inventing another name. A source filename, source directory, guessed episode or template example is not a supplied project identity. Bind projectIdentity.name, evidenceRef, optional native path/ID and lookup evidence in the task brief. Receiving only a route selection does not supply these facts.

SRT_ONLY does not require a native project. Preserve the known output mode and all source/audio/style decisions. Keep current-run naming facts in task data, not active style profiles.

## Style naming policy

Every NEW name contains at least two nonempty trimmed parts separated by `_`. Default the first part to the confirmed selected editing style's naming label, not the recipient or an unrelated style ID. Any middle context is optional and must have task evidence. The final part is the episode title or number; numeric episodes render as `EP 1`, `EP 7` or the evidenced zero-padded equivalent. An episode title remains the supplied title in one final part. Never append a workflow state such as draft, review, fb, feedback, trial or test as the final part or a trailing status label. Keep that state in task/review metadata, receipts or the checklist. Do not generate a workflow-state middle part either; a keyword alone does not invalidate a separately evidenced explicit middle context. Do not invent a status/version suffix to resolve a name collision; resolve the actual episode/context or destination instead.

Saved styles may declare `projectNaming.mode: STYLE_EPISODE`, matching `styleId`, `defaultPrefix`, `separator: _`, optional `contextTemplate` and `episodePrefix: EP `. The selected MrsNga naming label is `MrsNga`; a known `shootBatch: 5` produces optional middle part `Dot5`, and episode 1 produces `MrsNga_Dot5_EP 1`. If no context is supplied, a known episode 7 produces `MrsNga_EP 7`; do not ask for a batch merely because an older template required it. Another style uses its own confirmed naming label. A missing label or episode asks only those unresolved facts, not a new full-name interview. Supplied full NEW names may use an explicit different prefix while retaining the required parts/episode ending. Do not infer batch/episode from media folders.

Bind `projectIdentity.episode` to a positive number or episode title and optional `context` to evidenced middle parts; the helper retains `namingParameters.episode`, `episodeLabel`, `shootBatch` and `context` compatibility inputs with `parameterEvidenceRefs`. Preserve supplied zero padding. Legacy TEMPLATE/EXACT_NAME profiles remain readable but do not exempt newly created names from this global CapCut naming contract. Known style/name answers are reused; a name string or lookup intent alone does not prove a native project exists.

Bind namingParameters and per-field parameterEvidenceRefs. The helper checks supplied facts and missing fields; it does not authenticate their provenance. Reject unsafe names, path traversal, expression/attribute/index placeholders and format conversions rather than silently repairing a target.

## Resolve and create

New editing tasks default to agent creation of a new task-specific CapCut project once its name and scope are sufficient. Do not routinely ask the user to create a blank project. Use an available, authorized, compatible native app or local creator; preserve the applicable headless/hidden execution rule. Existing tool availability never authorizes installation, compatibility forcing, app shutdown or unrelated project reuse.

First resolve the exact native display name against permitted project metadata. A CLI projects query may filter folder basenames even when --names prints display names; an empty query result is not proof that the display-name project is absent. Read only needed metadata, retain only matches, and disambiguate collisions without overwriting or inventing a suffix. If a verified task project exists, reuse it only within the current requested edit scope. If no project exists and creation is authorized, create it yourself through a passing route. A name proposal is not a created project.

Before filesystem creation/registration, require the editor saved/closed, verified source/template compatibility, safe store/path and collision checks, scoped backup, and precision-preserving shared-index handling from Assembly. Never use a raw JavaScript whole-index rewrite when unsafe-large integers exist. Keep unrelated index rows/headers/types exact. Do not fake version markers, force-write, overwrite an existing project or copy private project content into a generic template. If the only available creator or native proof is blocked, hold that dependent action, state the exact capability/state needed, continue independent preparation and ask only for that prerequisite. Do not reopen the settled name/method or ask the user to perform creation by default.

Creation is complete only when the new draft identity/canvas/clock/registration and absence of unrelated changes are read back. Overall editing still requires actual content, independent caption objects, one-line style, playback and save/close/reopen proof. A blank shell or tool success never clears the video finish line.

## Helper and checks

scripts/project_naming.py supplies safe_name, selected_profile, resolve_project_identity and the separate new-name validator. `safe_name` remains filesystem safety for legacy lookups; it must not become a renamer. Intake binds intent and proposes names; the native producer independently validates NEW names before compilation/creation so a caller cannot bypass the rule with a raw plan. Owned revision still requires the actual hash-bound baseline and exact identity. Complete preparation produces PROPOSED_NAME_PENDING_APP_MATCH, not native acceptance or apply eligibility. Template and task examples never grant create/write authority.

Test default/explicit prefixes, optional context, episode numbers/titles and zero padding, other/missing styles, unsafe/empty parts and trailing workflow states, SRT-only, evidence gaps and partial inputs. Exercise actual NEW compilation/creation validation plus unchanged legacy lookup/owned revision, collision refusal and metadata-only limits. Carry naming and creation dependencies into the task brief and native checklist. Keep actual questions, answers, state labels and lookup evidence task-owned; return to editing after this support step.
