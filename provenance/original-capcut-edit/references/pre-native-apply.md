# Prerequisites before native filesystem apply

| Need | Path | Rule |
|---|---|---|
| Follow the required stage order | [Mandatory sequence](#mandatory-sequence) | Final acceptance keeps reviewed content/audio; explicitly scoped review destinations use the controlled branch. |
| Create or revise a controlled draft | [Controlled review draft](#controlled-review-draft) | Bind exact CREATE or owned-revision authority and complete pending inventory; no final quality waiver. |
| Revise one exact owned project | [Owned-project revision](#owned-project-revision) | Preserve identity, nine before hashes and index bytes; fresh guard, closed editor and per-file byte checks. |
| Bind current user audio acceptance | [Audio feedback evidence](#audio-feedback-evidence) | An exact current audio/listening-copy decision with resolved feedback precedes native apply. |
| Bind quiet and contextual removals | [Audio edit inventory](#audio-edit-inventory) | Original full raw history, current source-map intersections and actual dispositions remain distinct. |
| Bind and check evidence | [Cooperative consistency check](#cooperative-consistency-check) | Missing or stale evidence blocks writes, not task-local preparation. |
| Audit quiet and establish caption starts | [Content and captions](content-captions.md) | Reviewed pacing first, final edited-audio onsets second; no detector-only acceptance. |
| Check exact proposed bytes before writing | [Owned consistency helper](../scripts/check_native_apply.py) | Run immediately before every filesystem writer; missing proof blocks native apply. |
| Verify playback and persistence afterward | [Native verification](native-verification.md) | A consistency PASS never clears native acceptance. |
| Check every supporting video object | [Mandatory B-roll inventory](#mandatory-b-roll-inventory) | Recompute the current plan and compare all native supporting-video usage before writing. |
| Recompute execution coverage | [Mandatory recomputed execution coverage](#mandatory-recomputed-execution-coverage) | Recompute acoustic, cut/source-leg and protected-span coverage before native writes. |

## Mandatory sequence

For speech CONTENT_EDIT, the official first gate is the content leaf's audio
feedback checkpoint: send the current checked listening copy, resolve feedback,
and bind actual acceptance of that exact audio before any app-store application.
This also applies to controlled new-project and owned-revision review branches. Pending/failed audio
feedback permits task-local preparation only; Teacher approval is not listening
acceptance. Recut audio reopens the gate, while exact unchanged accepted audio
reuses its existing current decision.

For every CLI, SDK or task-authored filesystem writer, default to FINAL_ACCEPTANCE and
first complete the existing content/captions requirements. Only the explicitly authorized
REVIEW_DRAFT branch below permits prepared unresolved content in an explicitly
selected new review project or exact owned-project revision; never silently relabel
an accepted-project update or infer its ownership. A user asking to
continue, an earlier overall listening acceptance or a DRAFT label does not waive
quiet review or actual first-phoneme timing. Without the explicit controlled-review
branch, unreviewed material may be prepared only as clearly provisional files/previews
outside the app store. A reported early caption or long pause invalidates affected
acceptance and dependent timing. Resolve all analogous cases, not just the sample.

For CONTENT_EDIT, audit HEAD, INTERNAL and TAIL using the existing ALL_PAUSES
strictly-over-200000-tick rule. Account for all reviewed eligible quiet, safe
removals and protected residuals; unknown or held intervals block readiness.
The threshold does not mean retain200ms or force zero quiet. Freeze the final
content/source map, then establish every cue's first phonetic event on that exact
edited audio, and only then set each END to the next frozen START. A recut or
app-saved timing change invalidates the old clock and its receipts. Do not reuse
ASR/model/energy times as heard timing, including unchanged within-clip starts.
SUBTITLE_ONLY requires evidenced scope and preserves the existing pace; it never
provides a shortcut for an already authorized content edit.

## Controlled review draft

Read [native pipeline](native-pipeline.md#controlled-review-draft). Explicit current-task
REVIEW_DRAFT has two distinct destination contracts. CREATE_SEPARATE_NEW_PROJECT
requires a previously nonexistent project. READDRAFT_UPDATE_OWNED requires the
exact existing task project and the separately bound baseline/authority below.
The exact source/probe/clock/style/semantic and whole-B-roll preparation records bind the proposed
native/audio/destination/project/timeline identities. Record every pending content/take/
speaker/onset/quiet case; recompute coverage rather than removing risks. Use the owned
prepare_review_draft.py to build mechanical records from explicit inputs. The guard
returns PROVISIONAL_NOT_ACCEPTED, stage REVIEW_DRAFT and finalAcceptance false, never
hearing or permission from a passing checker. Source bounds, speed, text/locks, current
style, full usage/classification/mute, exact write bytes, editor/version/collision/backup
and later native proof still apply. Final release uses all unchanged FINAL_ACCEPTANCE
and native-verification requirements on the actual current revision.

## Owned-project revision

Follow [the exact revision sequence](native-pipeline.md#revise-one-owned-project)
using scripts/native_revision.py. Read-only capture-baseline copies the actual
root index and nine allowed native files to a fresh task directory, verifies
metadata/active-timeline/index identity and returns a capcut-owned-project-baseline/v1
ref. plan.project.revisionIdentity must bind that same immutable ref during compile;
the manifest identityMode is OWNED_REVISION. Default compilation/create-new keeps
fresh IDs and cannot be substituted for a revision.

The original current-task decision must explicitly bind operation
READDRAFT_UPDATE_OWNED, revisionBaseline, destinationPath, projectId and timelineId
alongside the existing task/name/source scope and actual user quote. The review
input additionally sets destinationOperation and revisionBaseline. The helper
mechanically emits claim review-draft-native-update-owned and destination
overwriteExisting true with that exact baseline; a boolean owned/overwrite flag
alone is insufficient. Keep all current-audio, semantic/source and pending-quality
requirements above. This route currently supports REVIEW_DRAFT, not a shortcut to
FINAL_ACCEPTANCE or Teacher activation.

preflight and apply require the actual compatible executable/hash and a closed
editor. They re-read the entire current index plus all nine expected before hashes,
run the real public guard in a fresh verification session and recheck current bytes.
The capcut-owned-project-revision/v1 request binds exact operation/store/name/IDs,
rootIndexSHA256, expectedFiles, appExecutable/appExecutableSHA256,
authorityEvidence and guardManifest. apply also requires a fresh task journal.
The index stays byte-for-byte unchanged, preserving opaque numeric types and other
projects. Each target replacement is staged, checked against its expected bytes
immediately before replacement and read back; the multi-file operation is not one
globally atomic write.

On a partial/effect-then-error result, reconcile the journal, actual index and all
target files before any retry. Recovery restores only an attempted file still
holding this writer's exact after bytes, under the same unchanged index and closed
editor checks. Foreign changes, linked/unreadable files, open app or index drift
hold recovery. Preserve the journal, backups and retained temporary paths; never
force, kill the app, overwrite foreign changes or restore the whole project from
an older snapshot. File readback still leaves actual playback/edit/save-reopen pending.

## Audio feedback evidence

For speech CONTENT_EDIT in either mode, manifest.audioReviewCheckpoint is a
hash-bound capcut-audio-review-checkpoint/v1 with taskId,
status ACCEPTED_BY_USER, audioGain1 equal to manifest.audio, listeningGain2,
gainReceipt, clockMap, feedbackInventory and acceptanceEvidence refs. The guard
checks actual PCM2x/no clipping/same duration/channels/rate and the gain receipt;
the listening copy never replaces gain1 project/analysis audio.

The exact clockMap is the observed source-piece/audio projection. Feedback uses
capcut-audio-feedback-inventory/v1: taskId, audioHash, coverage
ALL_CURRENT_TASK_AUDIO_FEEDBACK, latestFeedbackIds, items with RESOLVED and an
observation, and no unresolvedFeedbackIds. The actual acceptance uses
capcut-user-audio-review/v1, REAL_OBSERVATION, USER_AUDIO_REVIEW, ACCEPTED,
claim audio-content-review-acceptance, exact task/audio/listening/clock-map/
feedback identities, userQuote and userReply. The userReply must preserve the
observed DIRECT_USER_MESSAGE, AUDIO_CONTENT reviewKind, real sourceRef and message;
never manufacture a provider message ID or call a Teacher/package decision audio
acceptance. Hash binding proves consistency, not authenticity of invented prose.

The preparation helper may emit a pending checkpoint before that decision and
still provide task-local output. Missing/failed/stale acceptance blocks native
apply; it does not block audio repair, previews or offline caption planning. An
actually evidenced silent-source exception is narrow; SUBTITLE_ONLY remains
outside content recutting. Exact unchanged accepted audio may reuse its decision;
new cuts or unresolved latest feedback invalidate it.

## Cooperative consistency check

The reviewed evidence fields below describe FINAL_ACCEPTANCE. The controlled
REVIEW_DRAFT branch above uses explicit pending preparation fields and the native
pipeline's complete risk inventory; it never relabels them as reviewed audio.

Run `python scripts/check_native_apply.py --manifest ABSOLUTE_MANIFEST_JSON`
from the selected active skill. Use schema `capcut-native-apply-evidence/v1`:

- `evidenceClass: REAL_OBSERVATION`, actual `branch`, `native` and `audio` objects
  with absolute `path` and `sha256`. Native is the exact proposed draft; audio is
  PCM WAV on its final clock. No synthetic/test receipt is production evidence.
- `clockBinding`: `status: REVIEWED` and `evidence` binding extraction offsets,
  channels, speed, joins, source pieces and gain to those exact identities.
- CONTENT_EDIT `pacing`: `scope: ALL_PAUSES`, `status: REVIEWED`, `auditedScopes`
  exactly HEAD/INTERNAL/TAIL and `criterion` with `minimumQuietDurationTicks:
  200000`, `comparison: STRICTLY_GREATER`, `auditScopes` in that order. Include
  every interval's `id`, `kind`, original `startTick`/`endTick`, `decision` and
  `evidence`. Decisions are REMOVED_SAFE_QUIET, RETAINED_PROTECTED or
  AT_OR_BELOW_THRESHOLD; a HELD or unknown case stays blocked. Retained protected
  quiet requires actual phonetic evidence under the content leaf, not convenience.
- Preserve explicitly selected legacy INTER_SENTENCE_ONLY or SENTENCE_AND_INTRA
  through `scopeEvidence` with claim `pacing-scope-override` binding the exact
  `scope` and existing user authority. Apply the existing 15/5 frame rules and
  audited dispositions under the content leaf; RETAINED_REVIEWED_LEGACY is allowed
  only there. This guard never makes a legacy scope the default or changes FPS.
- SUBTITLE_ONLY `pacing`: `status: NOT_APPLICABLE_PRESERVE_EXISTING_PACE` and scope
  evidence; the helper's absence of content cuts does not prove pace preservation.
- `onsets`: exactly one row per current native text segment, with `segmentId`,
  integer `startTick`, nonempty reversible `rawWordIds`, `status: REVIEWED` and
  first-phoneme `evidence`. Include all cues, not only cut-adjacent risks. Preserve
  unchanged words/grouping/style, exact subsequent end holds and reviewed extremes.
- Each `evidence` is an absolute `path` plus `sha256` for a JSON review record:
  `evidenceClass: REAL_OBSERVATION`, `basis: HUMAN_LISTENING` or
  `SUPPORTED_AUDIO_REVIEW`, `status: PASS`, named `reviewer`, concrete
  `observation`, current `nativeHash`, `audioHash` and exact `claim`.
  Claims are `audio-clock-binding`, `all-pause-audit`, `pacing-scope-override`, `pause-disposition`,
  `subtitle-only-scope` and `caption-first-phoneme`. A pause audit binds the
  `auditedScopes` and sorted `intervalIds`; each disposition binds `intervalId`
  and `decision`; each onset binds `segmentId`, `startTick` and `rawWordIds`.

Keep the command result/hash with the task's write journal and run it immediately
before the SDK's existing editor-closed/version/current-file guards. Any failed,
missing, pending or stale prerequisite means zero native mutation. No force flags,
fake version, global offset or arbitrary delay is a recovery. Read the actual
current store by active IDs and selection; do not overwrite a new app save with
old staged JSON. Protect the shared index separately under assembly rules.

The helper is a cooperative consistency check, not an authentication boundary:
it cannot detect invented human declarations, hear audio, ensure the inventory is
truthful/complete, prove sample-to-source identity from a hash alone, grant write
authority or police a writer that bypasses it. The agent must inspect evidence
authenticity and coverage. Tests prove rejection of declared fixture/ASR/pending/
stale evidence and valid consistency paths only. Current native playback, readable
one-line layout, clean speech, editability and save/reopen remain separate proof.


## Mandatory recomputed execution coverage

Prepare a fresh task report before the guard:

~~~powershell
python scripts/execution_audit.py --native ABSOLUTE_NATIVE_JSON --audio ABSOLUTE_FINAL_PCM16_WAV --plan ABSOLUTE_CAPTION_PLAN_JSON --profile ABSOLUTE_DETECTOR_PROFILE_JSON --output NEW_ABSOLUTE_AUDIT_JSON
~~~

This writes a task-local PREPARED_ONLY_REVIEW_REQUIRED report; it never writes native files or supplies hearing. Bind its absolute path/hash as manifest executionAudit. The guard imports the owned module and recomputes coverage rather than trusting a claimed empty list.

The caption plan supplies mainTrackId, ordered words (id, exact text, reviewed sentenceId, sourceId matching native material_id, sourceStartTick/sourceEndTick), every native cue (segmentId, rawWordIds, nativeText), protectedSpans (id, kind, exact rawText, contiguous wordIds), and acceptedLockBaseline (absolute JSON file/hash containing protectedSpans). Preserve every actual prior user/reviewed lock; a newer explicit supersession is recorded in supersededLocks with lockId and an absolute hash-bound decision whose authority is explicit-user-request, exact lockId, scope and userQuote. A supplied baseline is not authentication of the complete user history. Whole-transcript semanticReview uses basis whole-transcript-semantic-review, exact coveredWordIds and evidence.

The caption-policy-review evidence is REAL_OBSERVATION, PASS, named reviewer/observation and current nativeHash/audioHash, with basis HUMAN_TEXT_REVIEW or SUPPORTED_TEXT_REVIEW and exact coveredWordIds, cueGroups and protectedSpans. This is text review, never hearing evidence. Original audio-only claims still require HUMAN_LISTENING or SUPPORTED_AUDIO_REVIEW. Native text, raw-ID grouping, at most six displayed words, single physical line, logical sentences and all carried locks must agree. Physical one-row fit still requires native proof.

cutInventory lists every current main-source cut and every cue, including first-word source legs and non-risk cases. The guard derives it from actual native clips and current raw source ranges. audio-clock-binding additionally binds mainTrackId. For each derived risk cue, its caption-first-phoneme evidence must include the exact derived row as cutRisk, including both source legs, touched cuts, reasons, raw IDs and current start. A matching cut count alone, END-only refinement, energy edge or ASR confidence cannot supply this proof.

For CONTENT_EDIT, pauseProfile has windowMs 20, hopMs 5 and methods with exactly RMS and PEAK, each with two to five distinct finite thresholdsDbFS between -100 and -1. Select/calibrate numbers per exact recording; these bounds are input validity, not suggested speech/quiet cutoffs. pauseScan is recomputed from exact current WAV at analysis gain 1, channel-max RMS/peak and strict sample-duration >200ms before rounding. Every method's candidate remains present even if another method/model disagrees. Supply calibrationEvidence with existing listening evidence fields and claim pause-detector-calibration plus exact profile.

Every residual candidate needs one pauseDecisions row: id, status REVIEWED, decision RETAINED_PROTECTED or RETAINED_NOT_QUIET and real listening evidence with claim pause-risk-disposition, exact candidateId and decision. Only the existing explicitly selected legacy scope permits RETAINED_REVIEWED_LEGACY. A qualifying residual quiet that is safely removable must be repaired, then final audio/maps/anchors/report rebuilt; do not label it protected for convenience. ASR overlap, missing review, pending rows or omitted candidates block. Original pre-cut interval/safe-removal evidence remains required by pacing; the final survey complements it. SUBTITLE_ONLY instead declares pauseScan NOT_APPLICABLE_PRESERVE_EXISTING_PACE and retains its existing evidenced scope, pace and onsets.

A task-specific quality exception is authority only for its exact displayed draft; it does not create hearing evidence, reusable permission or acceptance of a later revision. A user-reported defect reopens affected quality proof. Never reuse that draft exception or its old audio/onset receipt as verification that a new repair passes. Every writer still retains editor-closed, version, fresh-store, backup, metadata precision, B-roll/gain scope and native playback/save-reopen checks.

## Audio edit inventory

For ALL_PAUSES content editing, manifest.audioEditInventory binds the current
capcut-audio-edit-inventory/v1 record. The review preparer's audioEditPolicy supplies
maxActualRetainedQuietTicks exactly200000, rawSourceWords, rawTranscript,
sourceEditObservations and removedContentRawWordIds (an explicit list, empty when
none). All file inputs are absolute path/SHA-256 refs. rawSourceWords contains the
complete immutable original words with unique stable IDs, not only selected words;
rawTranscript is the original ASR segments/words document and is always required.
The guard compares the full ordered original raw text, segment, time/probability
and source-audio binding. This does not force later caption boundary estimates to
equal the old ASR clock. Preserve that refinement's separate provenance/crosswalk.

sourceEditObservations is REAL_OBSERVATION with removals (legacy fourRemovals is
supported). Each row binds id, originalSourceInterval (logical sourceId,
startTick/endTick), oldTargetIntervals, rawWordIds and contextualReason. Nonempty
removals also require originalSourceSHA256 and a hash-bound sourceIdentity probe
that identifies the actual main recording. The source map must resolve to its
current native material, path/hash and bounds; an unknown map cannot turn retained
speech into a claimed removal. An ASR-omitted filler uses an empty rawWordIds list,
not an invented raw word. The helper preserves original rows and derives actual
retained intersections and source/output reversibility from the current clips.

An optional derived main-video source uses the native pipeline's
[derived-master contract](native-pipeline.md#optional-derived-a-roll-master).
Bind `audioEditPolicy.sourceDerivation` as an absolute hash-bound
`capcut-source-derivation/v1` ref. The current supported mode is one original to
one derived master at 30 fps, normal speed, and one exact contiguous accepted-audio
slice. The record binds original file/probe/PCM/decoder and unchanged full
raw/transcript/removal refs, actual master render/probe/decoded-PCM/acceptance
records, every original-to-master frame window and current master sample range.
Current native material/source-map clocks remain the derived clock; original
history keeps the original source ID and clock. The guard recomputes composition
and sample equality before original-removal intersections. A renamed source ID,
duration-only match or caller declaration cannot substitute for that crosswalk.
This mechanical proof supplies no hearing, safe-cut judgment, caption onset or
native-quality acceptance, and cannot recover discarded picture handles.

If the current material uses a same-byte project asset copy, bind the optional
`master.copyProvenance` under that derivation record. Preserve historical master
file/render/probe/crosswalk refs and verify both actual paths/hash/size with the
source retained. The current native material path must equal the bound copy;
an unrelated alias or modified copy blocks it. Unchanged audio may reuse its
actual current decision, but changed native path/evidence bindings must be
refreshed. Copy consistency and external probing do not clear actual native
media-resolution, playback or save/reopen proof.

The generated record includes all independently recomputed detector candidates
as UNKNOWN/PENDING and original removal-context reviews as
UNKNOWN/PENDING_AUDIO_CONTINUITY. Optional audioEditReview supplies a real
capcut-audio-edit-review/v1 observation: current nativeHash/audioHash, exact
sourceEditObservations ref, claim audio-edit-review, status PASS or PARTIAL,
HUMAN_LISTENING or SUPPORTED_AUDIO_REVIEW basis, named reviewer/observation and
candidateReviews/sourceRemovalReviews. Omitted IDs remain pending; the preparer
does not invent listening. Full audio acceptance is a separate required record.

An actually evidenced detected filler isolated between two pauses must not remain
in either native mode. A tightly attached filler may remain under the content
leaf's explicit HELD_FOR_PHONETIC_SAFETY disposition, exact context evidence and
current audio decision. Unknown model islands are not automatically detected
fillers. Final ALL_PAUSES acceptance needs actual candidate/context dispositions;
merge touching reviewed true-quiet spans before enforcing the200000-tick maximum,
so subdividing one long pause cannot evade it. Complete pending inventories may
enter only the explicitly scoped controlled review branch after current audio acceptance.
Legacy scoped pacing and subtitle-only preservation keep their own requirements.

## Mandatory B-roll inventory

The guard derives every non-main video object using the execution audit's bound `mainTrackId`, never a guessed track order or `hasBroll: false` flag. With no supporting-video objects, no B-roll plan is needed. Otherwise require manifest `bRollAudit` as an absolute JSON path/SHA-256 ref. Its `capcut-native-broll-audit/v1` record binds exact proposed `nativeHash`, `mainTrackId`, a hash-bound `plan` ref and visual `reviewEvidence`. The plan is the complete current `capcut-broll-plan/v1` reviewed plan, with frozen base, all existing/proposed placements and source identities. Default `NO_SOURCE_REPEAT` means one placement per original source identity, even disjoint windows; only the leaf's exact explicit user override permits conditional reuse.

The guard reruns owned `prepare_broll`, rejects HELD/conflicting results, and compares every actual proposed supporting-video object with the combined usage ledger by segment identity, material file hash, exact source/target range, normal speed and zero volume. It also compares the frozen base's actual supporting inventory against `sourceUsageReview.existingPlacements` and binds unchanged main clips/caption clocks. Missing/duplicate/unmapped objects, incomplete old inventory, unsupported source clocks/lineage, changed source files and stale native/plan/base evidence block application. A plan with empty existing placements cannot conceal already present footage. Decorative or unclassified video objects are held rather than silently excluded; resolve their role and supported representation first.

Visual evidence uses the existing REAL_OBSERVATION/PASS/named-reviewer/current-native-and-audio-hashes format, basis HUMAN_VISUAL_REVIEW or SUPPORTED_VISUAL_REVIEW, claim `broll-whole-timeline-review`, and the exact `actualInventory`, `mainTrackId` and `planHash`. Bind `wholeTimelineInventoryComplete: true`, `knownSourceLineageReviewed: true` and nonempty `inventoryObservation`/`lineageObservation`. It must record reviewed source-lineage and whole-inventory completeness. File hashes recognize byte-identical aliases; visual review is still required for differently encoded/cropped copies and near-duplicate views. No helper authenticates declarations or certifies native visual appearance. User feedback reopens that revision's B-roll proof. Preserve every audio, caption, authorization, closed-editor, backup, actual playback and save/reopen gate.
