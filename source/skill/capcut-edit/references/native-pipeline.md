# Native timeline producer and controlled review loop

| Need | Path | Rule |
|---|---|---|
| Prepare the audio-first review | [Assemble cut audio](#assemble-cut-audio) | Use original PCM/source pieces, then the checked listening copy; user acceptance precedes native apply. |
| Match explicitly selected clip edges | [Strict clip-edge alignment](content-captions.md#selected-strict-clip-edge-alignment) | Bind actual clip/word ownership, repair authorized edges and review changed audio before final clocks. |
| Prepare one derived picture source when useful | [Optional derived A-roll master](#optional-derived-a-roll-master) | Preserve accepted PCM exactly, original history and a checked source crosswalk; no native-quality inference. |
| Build editable objects from a source plan | [Compile the timeline](#compile-the-timeline) | Use explicit source windows and the packaged producer, not project-history scripts. |
| Review native captions and picture | [Controlled review draft](#controlled-review-draft) | Current audio accepted first, exact new-project or owned-revision authority and disclosed pending native quality. |
| Preserve exact writes and accepted timing | [Apply a new project](#apply-a-new-project) | Closed editor, compatible version, fresh store, current guard, backups and exact old-index preservation. |
| Revise one existing task project | [Revise one owned project](#revise-one-owned-project) | Exact baseline/identity, closed editor, nine before hashes, unchanged index and scoped byte checks. |
| Reuse unaffected review evidence | [Evidence dependencies](#evidence-dependencies) | Prove relevant dependencies unchanged; preserve the original reviewer and limitations. |
| Establish final acceptance | [Inspect and finish](#inspect-and-finish) | Actual speech, native appearance, editability and save/reopen remain separate required tests. |

NEW project compilation and creation use the shared [project identity](project-identity.md) naming contract: nonempty underscore parts, selected-style default prefix, optional context and episode title/number last. Keep draft/review/fb state in task metadata, never a trailing name label. The producer enforces this separately from filesystem-safe legacy lookup and exact baseline-bound owned revision; naming validation grants no creation/overwrite authority.

## Assemble cut audio

Select takes, contextual hesitation removals and quiet windows as task data under
the content leaf. Use the authorized local decoder to obtain original-clock PCM16
and retain its source/PCM identities, sample format/count, offset and gain1 record.
An identity-valid prior decode may be reused with its actual provenance; matching
duration alone is insufficient. Do not change or normalize project/source audio.

Run `scripts/assemble_audio.py --plan AUDIO_PLAN --output NEW_GAIN1_WAV`. Its
capcut-audio-assembly-plan/v1 supplies explicit mainPieces (id, sourceId,
sourceInTicks, sourceOutTicks, targetInTicks and optional targetOutTicks) and
pcmBindings (sourceId, decoded path/hash, originalSourcePath/hash,
sourceOffsetTicks and hash-bound decoderEvidenceRef). Source and target sample
windows must represent a contiguous, normal-speed, gain1 map with exact common
PCM format. The helper copies actual source samples, records rational endpoint
quantization and verifies output identity. It refuses unrepresentable mappings,
overlapping reused samples, format changes, source replacement or app-store output
rather than resampling, padding or stretching to pass. It does not detect quiet,
classify fillers, choose speakers or supply hearing.

Then run `scripts/prepare_voice_review.py --input GAIN1_WAV --output NEW_LISTENING_WAV`.
Use its checked2x copy for the content leaf's complete audio feedback checkpoint;
retain gain1 as the actual timeline/analysis audio. Any feedback-driven recut
regenerates the sample projection and listening copy. Offline text/visual planning
may continue, but native application waits for acceptance of this current audio.

On a stable assembled candidate, perform the content leaf's spoken-coverage and
restart comparison early enough to resolve defects before audio acceptance. Use
an exact-candidate transcription/alignment where needed; after acceptance reuse it
if that exact audio is unchanged, rather than running the full model twice.
Preserve the original raw-history crosswalk and reviewed wording. Refresh affected
clocks after any recut and do not inherit source-ASR intervals that included removed
quiet/fillers. New caption START estimates still require separate final-audio onset
review; fill only preceding ENDs after freezing current STARTs.

When the task explicitly selects strict first/last caption-to-clip alignment, follow
the content leaf's [selected mode](content-captions.md#selected-strict-clip-edge-alignment).
Choose semantic blocks and actual word/clip ownership first; correct authorized
affected audio edges without clipping speech, then repeat the existing current-audio
feedback checkpoint. Freeze starts only on that new clock. Within each actual
bound clip, match the first caption START and final caption END to its reviewed
edges, retain internal first-word onsets and fill ENDs only within its caption
group. Logical group labels do not turn flat source pieces into a compound clip;
the current producer implements no compound constructor. A physical quiet cut
through a protected phrase requires an evidenced resolution or an explicit held
conflict, not an invented representation, dropped lock or automatic cut snap.
This selected scope changes no raw-word, style, source, native-proof or permission
rule and gives no acceptance to audio that has not actually been reviewed.

## Optional derived A-roll master

Prefer original-source references when they meet the current editing and quality
requirements. Many quiet-removal pieces may make a semantic caption block cross
several physical native clips. An optional task-local derived A-roll master can
join those picture windows once and carry the exact accepted PCM, allowing the
native plan to use longer semantic main-video blocks with separate editable text
and supporting-video objects. It trades an H264 picture generation and render
time for a simpler native source layout; it is not universally faster, a compound
constructor, a final flattened deliverable or evidence of native quality.

Read `scripts/render_aroll_master.py` before use. Its public API is
`render_master(plan_path, audio_path, accepted_audio_sha256, output_dir, ffmpeg_path,
ffprobe_path, *, fps, source_fps, canvas, threads=4, fit_mode='contain')`.

Before rendering generated media that CapCut will reference, choose a stable,
compact project-owned asset location under the declared project layout. Use a
fresh named output directory there with a short meaningful media name; do not
place the app's media inside deep Teacher transaction/evidence folders. Keep
audit/history evidence separate and reference the stable asset by exact path/hash.
The helper's fresh-output requirement does not require a deep evidence path.
Preserve supplied original-media paths and the existing authorized material scope.

The explicit CLI uses the same source plan and actual current gain1 audio:

~~~powershell
python scripts/render_aroll_master.py --plan AUDIO_PLAN --audio ACCEPTED_GAIN1_WAV --audio-sha256 EXACT_WAV_SHA256 --output-dir NEW_PROJECT_MEDIA_DIRECTORY --ffmpeg ABSOLUTE_APPROVED_FFMPEG --ffprobe ABSOLUTE_APPROVED_FFPROBE --fps 30/1 --source-fps EXACT_SOURCE_FPS --canvas-width EVEN_WIDTH --canvas-height EVEN_HEIGHT --threads 4
~~~

The `capcut-audio-assembly-plan/v1` supplies exactly one original `pcmBindings`
source with `sourceId`, `originalSourcePath` and `originalSourceSHA256`.
Each main piece supplies `id`, `sourceId`, `sourceInTicks`, `sourceOutTicks`,
`targetInTicks`, `volume: 1` and explicit normalized `sourceFrameIn`/`sourceFrameOut`;
`targetOutTicks` is optional and speed is absent or1. Legacy `sourceFrameIn30`/`sourceFrameOut30`
are supported only when the declared normalized FPS is 30. Conflicting aliases,
out-of-bounds or overlapping source windows, target gaps, speed/gain changes,
unrepresentable frame/sample clocks and output collisions are refused. A supplied
WAV hash identifies bytes; it does not establish user acceptance.

Use explicitly authorized existing FFmpeg/FFprobe binaries and retain their actual
paths, hashes, versions and complete commands. The producer verifies the declared
fixed source FPS/zero-start clock, autorotates once, normalizes picture FPS once,
fits within the explicit canvas without crop/stretch, trims frame windows and
concatenates normal-speed picture. It writes H264 CRF17/veryfast with the accepted
PCM16 stereo48k audio copied without audio filters, resampling, normalization,
fades or padding. Only thread counts 4 or 8 are supported. Read back exact frame
count, visible dimensions, rotation and duration; coded padding dimensions may
differ from visible width. Decode the output audio and compare every PCM byte to
the accepted input. Keep sampled rendered frames for actual visual inspection,
not an aspect-ratio-only claim. Original inputs are hash/stat-bound across the
call; output is a fresh task directory, never an app or instruction store.

For guarded native use, bind `audioEditPolicy.sourceDerivation` to a task-owned
`capcut-source-derivation/v1` record. The current derived-history validator supports
one original source to one master at 30 fps, normal speed and an exact contiguous
current-audio sample slice. A standalone render at another representable FPS does
not establish that guarded path. Bind the original file/probe/PCM/decoder evidence,
master file/frame count/probe/render receipt/decoded-PCM proof/accepted-audio
decision, the complete original-frame to master-frame crosswalk and the current
audio file/decision/master sample window. Keep `rawSourceWords`, `rawTranscript`
and `sourceEditObservations` as their exact original-history refs. The owned
`source_derivation.validate_source_derivation` composes and checks original PCM,
master and current audio instead of relabeling original ASR/removal clocks as
master clocks. A different audio slice needs its actual current acceptance.

For an existing rendered master, the optional `master.copyProvenance` absolute
path/SHA-256 ref supports a verified same-byte copy to a stable project asset path.
Its `capcut-task-byte-identical-media-copy/v1` record uses status
`BYTE_IDENTICAL_COPY_VERIFIED_NATIVE_RELINK_PENDING`, `original` and `copy` objects
with exact `path`/`sha256`/positive integer `size`, and
`sourceDeletedOrModified: false`. Keep historical
`master.file`, render/probe/decode receipts and frame/sample crosswalk unchanged;
bind both file paths, matching actual SHA-256 and size, and source retention in
the copy record. The current native material must use the exact bound copy path,
not an arbitrary alias. A byte-identical copy is not a recut or fresh listening
acceptance. Refresh affected native path/evidence bindings and require actual
native import/resolution/readback. File existence, hash equality or a successful
external probe alone cannot prove that CapCut has resolved the file. A shorter
path is a practical compatibility precaution, not proof of a universal path-length
cause or numeric application limit.

Register the master as an explicitly derived source in the typed plan with its
actual identity, duration and displayed dimensions. Allocate semantic main clips
on that master clock, then bind independent caption/B-roll clocks under the same
existing rules. Retain the original files and crosswalk for recovery and history.
The derived file contains only selected picture; its native trim handles cannot
recover footage discarded during rendering. Preserve Assembly Route1's existing
trim-handle acceptance or consequential scoped choice; this optional helper does
not grant that decision. A render/PCM proof does not supply
speech judgment, exact caption onsets, native playback or edit/save-reopen proof.

## Compile the timeline

Use `scripts/native_timeline.py` with the selected installed Python and the local
`templates/native-template.json`. Read the complete current helper interface before
creating its task instance. Its input is a task-owned `capcut-timeline-plan/v1`:
explicit project identity/canvas/FPS, source paths and SHA-256/full durations/display
dimensions, ordered source windows, caption text/raw IDs/clocks/style,
and separately editable silent supporting-video windows. Source display dimensions
account for evidenced rotation; preserve coded dimensions/rotation in probe evidence
and do not rotate the decoded picture twice.

The agent still performs source identification, candidate ASR/take review, logical
sentence/phrase judgment, authorized quiet editing and final-clock caption planning.
The producer implements the mechanical plan-to-project conversion; it does not hear,
authenticate model timings, choose speakers, certify grammar or silently create
missing evidence. Reuse only exact identity-valid source/transcription intermediates;
record cached and fresh work separately. A malformed or wrong-topic input is held.

`compile --plan ABS_PLAN --output NEW_OUTPUT` creates a new task output directory
with `files/`, a frozen plan, compiled manifest and semantic readback. It creates
fresh project/timeline/object IDs by default, source-referenced video segments,
independent text objects and overlay tracks plus current multi-timeline sidecars.
For an explicit owned revision, `project.revisionIdentity` binds the captured
baseline below; compilation preserves that project's name and project/timeline
IDs and marks `identityMode: OWNED_REVISION`. Original media stays intact; source
references retain their original handles, while derived-source handles stop at
the rendered media's bounds. Do not copy a previous
episode's native timeline as the new result or import a task-history module.

Validate with `validate --compiled OUTPUT`; use
`inspect --native SAVED_CONTENT --compiled OUTPUT` after app save. Resolve active
materials by ID and actual references, not list position. Saved-file inspection
accepts exact clocks or the integer floor/ceiling values of the same declared
rational frame event for timeline end and target starts/ends. The observed source
end normalization requires an unchanged source start and the same normal-speed
duration change in source and target; other source changes still fail. Full
material duration may retain the original value or serialize the single upward
native-frame rounding of that original duration. This is registration metadata
only: original source duration and excerpt bounds remain authoritative and cannot
expand. Same-category duplicate material IDs are accepted only when their complete
JSON values, including numeric types, are identical; contradictory or cross-category
aliases fail. The readback reports clock, registration and alias normalization
separately. There is no generic microsecond, millisecond or whole-frame tolerance,
and no audio, onset, native appearance or persistence acceptance follows from it.

The packaged template
is sanitized structural data for its declared tested CapCut version, not a private
project or a universal compatibility promise. A version mismatch holds apply;
never change version markers or use force to manufacture compatibility.

Apply the selected current style explicitly, including its readable size/width,
position, verified installed font resource, and UTF16 ranges of final emoji text.
Compilation success/no newline cannot prove one native line, glyphs or appearance.
Preserve all existing caption semantics, short-remainder rules, case/punctuation,
numbering/long-lead-in exception, style applicability and source-usage policies.

## Controlled review draft

Keep `FINAL_ACCEPTANCE` as the default pre-native mode. It retains actual reviewed
speech/take/quiet/onset and final acceptance requirements. A draft label, missing
tool, generic continue request or passing synthetic test never changes that mode.

An explicitly authorized current-task `REVIEW_DRAFT` selects one exact operation:
`CREATE_SEPARATE_NEW_PROJECT` creates a previously nonexistent review project;
`READDRAFT_UPDATE_OWNED` revises only the exact task project bound by the immutable
baseline and authority below. Neither operation silently replaces another or an
accepted project. Bind the user decision, exact proposed native/audio
hashes, destination, project/timeline IDs, source scope, style profile and prepared
source/word/caption map. Inventory every pending take/speaker/lexical ambiguity,
source pause and recomputed residual, every cue onset and cut risk. Keep true
observations and machine proposals distinct. No omitted or pending item becomes
heard/PASS because it appears in the timeline. Required current audio acceptance
is a separate actual user checkpoint, not a pending item that this branch waives.

Speech CONTENT_EDIT also requires the exact current audio/listening-copy user
acceptance checkpoint before native apply, in both final and controlled-review modes.
A missing or failed audio review blocks app-store writes while offline preparation
continues. The current guard checks its `capcut-review-draft/v1` record and outputs
`PROVISIONAL_NOT_ACCEPTED`, `stage: REVIEW_DRAFT`, `finalAcceptance: false` with
the pending-quality inventory. This is eligibility for the specifically authorized
review workflow, not permission issued by a checker or quality acceptance. Source
identity/bounds, normal speed, no invented words or hidden raw-ID loss, carried
semantic locks, text policy, style identity, complete object inventory, B-roll
source classification/edges/minimum length/mute/usage, exact write bytes, editor
state and backups still apply. Synthetic evidence is never production evidence.

Candidate cuts are first auditioned in task-local listening copies and resolved
through the required current-audio feedback checkpoint. Only then may native
onset/layout review proceed in the explicitly authorized review destination. Keep conservative source handles and
disclose uncertain cuts; never claim all pauses removed, latest take proven or
correct phonetic onset from ASR/energy alone. Fill gaps by extending the previous
caption END only after freezing the proposed/current STARTs; label model-derived
STARTs pending until reviewed on final audio. If a draft cut changes, invalidate
affected audio/onsets/overlays and rebuild before another review.

After compilation run `scripts/prepare_review_draft.py --compiled OUTPUT --audio
FINAL_PCM16_WAV --input REVIEW_INPUT --output NEW_REVIEW_DIRECTORY`. Its
`capcut-review-draft-input/v1` supplies taskId/destinationPath, the exact
destinationOperation, hash-bound original
decision, actual captionReview, styleProfile, audioProjection, sourceProbe and
B-roll meaning review, plus the detector profile, pending take/word uncertainties
and pre-cut pacing intervals. Read the helper's complete current schema. The
caption review must enumerate every proposed retained caption word, cue and carried lock; do not replace
the agent's text judgment with a generated PASS. Bind planHash as `sha256:` plus
compiled-manifest.planSHA256, which identifies the producer's frozen plan bytes,
not a differently formatted input file. The helper generates native-ID-bound
records and recomputed inventories, then runs the guard. It does not decode audio,
choose cuts, invent user consent or supply hearing. Keep its complete receipt.

An unchanged accepted audio decision may survive a caption-only or verified
same-byte media-reference change when the whole plan/native UUID/path metadata
changes the clock-map wrapper hash. Keep the exact gain1 audio, listening-copy,
resolved-feedback inventory, task and direct AUDIO_CONTENT user reply/quote
identities unchanged, and preserve immutable prior acceptance-binding provenance.
The current gain receipt and every non-clock acceptance field must still pass the
unchanged strict checkpoint validator. A changed audio hash requires actual user
review of that new audio; a changed task/listening/feedback/reply or any additional
checkpoint error blocks this reuse. Never edit the old acceptance or replace its
observed quote, source reference or review scope with a new hearing claim.

Pass the existing `audioReview` refs to `prepare_review_draft.py`; no new caller
flag is required. Only when that validator finds solely the old clock binding
mismatch, the helper may emit a fresh `audio-acceptance-clock-binding.json` using
the same `capcut-user-audio-review/v1` decision with current `clockMapHash`,
`priorAcceptanceEvidence`, `oldClockHash`, `currentClockMap`,
`bindingBasis: IDENTICAL_ACCEPTED_AUDIO` and `newUserDecision: false`.
The original decision remains byte-exact. The independent fresh native and
source-to-audio guard must still prove the current normal-speed sample map; metadata
rebinding never skips it or grants native-write authority. This preserves only
the exact audio-content decision. Caption onsets, appearance, editable objects
and save/reopen proof remain separately current, with affected proof refreshed.

Before invoking this helper or starting expensive source verification, inspect
`pacingIntervals` as an array of direct row objects. Each row needs a unique
nonempty `id`, `kind: HEAD | INTERNAL | TAIL`, integer original-source
microsecond `startTick` and `endTick` (1000000 ticks per second, not seconds or
booleans), `0 <= startTick < endTick`, and `decision`. The helper copies these
rows to `manifest.pacing.intervals`; endpoints stored only inside a nested
detector payload do not supply the required direct fields. Preserve that original
payload, source identity/context and uncertainties rather than inventing values
or substituting removal-window or final edited-clock coordinates.

For provisional unknowns use `decision: PENDING` or `HELD` and retain the reason.
Other decisions are `REMOVED_SAFE_QUIET`, `RETAINED_PROTECTED` and
`AT_OR_BELOW_THRESHOLD`, each requiring actual current hash-bound
`pause-disposition` evidence matching `intervalId` and `decision` under the
[pre-native evidence contract](pre-native-apply.md#cooperative-consistency-check).
Only `AT_OR_BELOW_THRESHOLD` applies to intervals at or below 200000 ticks; the
other two reviewed decisions apply above it. Overall `pacing.status: REVIEWED`
also requires current `all-pause-audit` evidence covering every interval ID and
HEAD/INTERNAL/TAIL scope. Row-shape inspection proves no heard quiet, phonetic
boundary or caption onset, never waives current user-audio acceptance, and grants
no native-write authority.

Use the helper's recomputed inventory over every cue/cut, not a curated onset
shortlist, to account for source-leg risk. A first-word model range spanning quiet
or multiple/earlier retained legs cannot use its earliest surviving fragment as
an automatic onset. Reconcile the complete word's accepted occurrence and source
ownership before its current START; preserve ambiguous cases as pending. Neither
the helper's coverage nor matching first/last geometry authenticates that event.

For the ALL_PAUSES happy path also supply audioEditPolicy with the exact200000
maximum, original full rawSourceWords, original rawTranscript,
sourceEditObservations and explicit removedContentRawWordIds. Keep full original
ASR history separate from selected/refined caption words. Optional audioEditReview
binds actual context observations; omitted judgments stay pending. The helper
generates manifest.audioEditInventory and checks actual source-map intersections,
not a caller's claim that a filler was removed. Follow [Audio edit inventory](pre-native-apply.md#audio-edit-inventory)
for the complete field and mode contract before invoking this route.

Model word intervals may span actual quiet. A specifically authorized provisional
test may set allowModelWordIntervalOverlap in its bound original decision. In this
branch only, preserve the original intervals and derive every removed/retained
intersection as PENDING_AUDIO_CONTINUITY. Every selected word must retain nonempty,
nonduplicated source legs. Never shorten word intervals merely to fit a proposed
cut, omit risk rows or call their cuts safe to pass. A separately established
source/final-audio boundary refinement preserves the old estimate, exact new clock,
raw-word crosswalk, method and actual evidence; a new model estimate is still
pending hearing. A fully removed word still blocks; FINAL_ACCEPTANCE does not
inherit this exception. Review the actual joins before accepting the result.

For provisional B-roll use the exact same task authority with
`contentCaptionCheckpoint: PROVISIONAL_PREPARED`, not a fabricated final PASS.
This permits reviewing picture together with prepared content in the selected
review destination; it does not change the final content-before-B-roll checkpoint or source
policy. Source shortage holds additional placements. An explicit three-source,
one-placement-each test stays three scenes; never fill the rest by repeated views.

## Apply a new project

`apply-new --compiled OUTPUT --request APPLY_REQUEST --journal NEW_JOURNAL`
uses an exact task-owned `capcut-new-project-apply/v1` request. Inspect the current
helper schema and bind real user authority; never copy a synthetic request into
production. It supports creation only, not editing/renaming/deleting existing
projects. The actual installed executable/version, real store/index, fresh source
and compiled-file hashes, unique name/IDs and closed editor are checked before
mutation. A passing current pre-native check is required immediately before writing.

Take a scoped journal/backup and retain every unselected shared-index row and root
header byte-for-byte, including opaque numeric tokens beyond JavaScript's safe
integer range. New task insertion must preserve the original array body. Recheck
the exact index and destination before/after the guard and atomic mutation; drift,
collision, open editor or compatibility refusal stops the write. Never force it.

An effect-then-error or partial copy is an uncertain write. Inspect the journal,
actual index and new folder before retrying; restore only owned bytes under the
original authority and preserve foreign changes. Keep retained partial output and
backups for reconciliation rather than recursively deleting user content. File
registration/readback is not native playback or final acceptance.

## Revise one owned project

Use `scripts/native_revision.py` only for the explicit operation
`READDRAFT_UPDATE_OWNED`. This is a separate writer from create-only `apply-new`;
neither can be substituted for the other. First read the current live project by
its actual metadata, root-index row and active timeline, then capture exact bytes
without changing the native store:

~~~powershell
python scripts/native_revision.py capture-baseline --store ABSOLUTE_NATIVE_STORE --name EXACT_EXISTING_NAME --output NEW_TASK_BASELINE_DIRECTORY
~~~

`capture_baseline(store_path, name, output_dir)` returns a hash-bound
`capcut-owned-project-baseline/v1` ref. It copies the entire current root index and
nine allowed project files, checking stable identity/bytes; it does not grant
ownership or native acceptance. Set `plan.project.revisionIdentity` to that exact
immutable ref. `native_timeline` calls `compile_identity(ref, name)` to validate
the live baseline and preserve its project/timeline IDs and name, while marking
the compiled manifest `OWNED_REVISION`. It does not manufacture inherited phase
evidence or change normal-speed clocks. New-project compilation retains fresh
IDs; `apply-new` refuses an owned-revision compile.

The nine scoped files are `draft_content.json`, `template-2.tmp`,
`Timelines/<timelineId>/draft_content.json`,
`Timelines/<timelineId>/template-2.tmp`, `draft_meta_info.json`,
`Timelines/project.json`, `timeline_layout.json`, `draft_virtual_store.json` and
`key_value.json`. The shared index is observed/backed up but never rewritten by
this writer. Preserve every other project file and all unselected projects.

The original current-task review decision binds `operation:
READDRAFT_UPDATE_OWNED`, the exact `revisionBaseline`, destination path and
project/timeline IDs alongside task/name/source scope and the actual user quote.
Set review-input `destinationOperation` and `revisionBaseline` to the same scope.
The preparer emits authority claim `review-draft-native-update-owned`, baseline
index hash and nine before hashes; `overwriteExisting: true` or an `owned` flag
alone is insufficient. This implemented revision branch is `REVIEW_DRAFT` only
and keeps the current-audio checkpoint and all source/text/style/B-roll checks.

Prepare a task-owned `capcut-owned-project-revision/v1` request with the exact
operation, `storePath`, `name`, `projectId`, `timelineId`, `rootIndexSHA256`,
`expectedFiles`, actual `appExecutable`/`appExecutableSHA256`, `authorityEvidence`
and `guardManifest`. Inspect the complete current schema and real authority;
synthetic requests are not production evidence. Run read-only preflight first,
then apply only under that exact current scope:

~~~powershell
python scripts/native_revision.py preflight --compiled COMPILED_OUTPUT --request EXACT_REVISION_REQUEST
python scripts/native_revision.py apply --compiled COMPILED_OUTPUT --request EXACT_REVISION_REQUEST --journal NEW_TASK_JOURNAL_DIRECTORY
~~~

`preflight(compiled_dir, request)` and
`apply_revision(compiled_dir, request, journal_dir)` verify the compatible actual
CapCut executable/version and actual closed-editor process state, the whole index
and every expected before hash, compiled identities/bytes and a fresh public
pre-native guard. Apply retains an independent fresh guard immediately before
writing. It backs up the exact index/nine before files, stages each selected
replacement, compares current bytes immediately before replacement and reads
back the result. Index bytes and opaque numeric types remain intact; each file
replacement is atomic, but the nine-file operation is not globally atomic.

On drift, open editor, foreign/linked/unreadable data or partial/effect-then-error,
inspect the current journal, index and every target before any retry. Automatic
recovery restores only an attempted file still containing this writer's exact
after bytes, with a valid backup and unchanged index/closed editor. A foreign
change holds recovery rather than being overwritten. Retain backup, journal and
temporary paths for reconciliation; never force, kill the app, restore the whole
project or silently capture a new baseline as authority for changed user data.
The success status is file readback only: native playback, independent edit and
save–close–reopen remain pending until actually observed on this revision.

## Evidence dependencies

Use `scripts/dependency_proof.py` to fingerprint the actual dependencies of a
particular claim. Keep exact whole-file hashes for write ownership. For evidence
adoption, bind both native snapshots, the exact audio and claim-specific source,
audio-map/caption/text/style/supporting-inventory dependencies plus the original
receipt. Only unchanged relevant dependencies can transfer that same observation.
Do not replace its reviewer/time/scope with fresh hearing or native acceptance.
The original observation must already bind its relevant original media/font paths
and hashes. Current matching files cannot retroactively prove what an old review
used; a missing original binding holds adoption rather than creating provenance.
Changed wording, source cuts, gain, speed or onset invalidates relevant claims;
unrelated resource cleanup is accepted only after active-object identity is proved.

Normal-speed frame clocks may contain an inherited source/target phase. Preserve
the separately evidenced actual source and target endpoints against the bound
baseline and rational timeline FPS. Do not compute target END from source length,
apply a universal epsilon, round away a phase, change speed or retime the project
to satisfy a checker. Unbound/changed phase or unsupported speed remains held.

## Inspect and finish

Follow [native verification](native-verification.md) on the current project. Check
speech/takes/restarts/joins, all real quiet strictly over 200ms with phonetic handles,
true final-audio caption starts followed by END-only holds, semantic groups and
readable one-row style, meaningful silent footage and source use. Use supported
native pixels/playback, an authorized scoped independent text/video edit, then
save–close–reopen and semantic readback. Record user-reported and personally
observed proof separately. Native API failure holds only dependent proof.

A review draft remains provisional until its pending items have actual dispositions
and required final checks pass on that current revision. Neither a rendered preview,
compiled project, passing guard nor source/runtime sync certifies final quality.
Continue independent authorized preparation and fixes; ask only for the exact
missing decision or observation after the concrete reviewable project is ready.
