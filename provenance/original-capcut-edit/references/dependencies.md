# Dependencies and one-way owners

| Need | Path | Rule |
|---|---|---|
| Resolve owned files | [Local closure](#local-closure) | No project, download or scratch dependency. |
| Resolve shared authority | [Shared owners](#shared-owners) | Load existing canonical owner only when triggered. |
| Select actual execution tools | [Runtimes](#runtimes) | Availability and approval are separate. |
| Claim independence or delivery | [Readiness](#readiness) | Static closure is not isolated/native proof. |

## Local closure

Owned audio-first production: scripts/assemble_audio.py and its meaningful tests
copy original PCM16 samples from an explicit normal-speed source/target plan into
a new gain1 WAV, with sample projection, original decoder provenance and exact
readback. It uses only the standard library and does not classify quiet/fillers,
hear, resample, pad, normalize, write CapCut or provide user acceptance. The sibling
prepare_voice_review.py provides the checked2x listening copy afterward. Together
they remove any execution dependency on a private project's audio assembly script.

Entry: `SKILL.md`. Conditional leaves: this directory's Gate 0, content/captions, assembly, B-roll, native verification and benchmark files. Owned naming mechanics: scripts/project_naming.py plus synthetic tests; the intake helper and native producer import it from this package, resolving selected styles locally. Intake proposes/questions only; NEW compilation/creation independently checks the underscore/style-context-episode name contract. Legacy lookup and exact baseline-bound owned revision retain literal names. The naming helper itself performs no app/store mutation and supplies no write authority.

Owned take procedure: references/take-review.md is loaded through the content
leaf for actual source selection or repeated-idea repairs. It keeps semantic
occurrence judgment, partial-restart chains and fresh candidate coverage with
the agent; no string matcher or task-history script selects the winning take.

Owned mechanics: `scripts/prepare_cut.py`, `scripts/prepare_voice_review.py` and their meaningful synthetic tests. The listening-copy helper uses only Python standard-library PCM WAV handling and does not decode video, hear speech or change app audio. Owned task-instance templates: brief, reviewed cut-plan shape, native checklist and benchmark record. Saved parameterized profile: `styles/nga.json`. They resolve relative to this skill. No operating dependency may point to a project, download snapshot, retired history, attachment or Codex visualization.

Owned pre-write mechanics: `scripts/check_native_apply.py`, its synthetic tests and `references/pre-native-apply.md`, with the sibling dependency_proof.py. They use only Python standard-library files/hash/JSON/WAV handling, check task-supplied current pacing/onset evidence and never write a native draft or hear audio. A consistency result is neither permission nor native acceptance.

Owned execution coverage: scripts/execution_audit.py and scripts/test_execution_audit.py use only Python standard-library PCM16 WAV/JSON processing. The pre-native guard imports this sibling module. It surveys explicit task-calibrated RMS/peak thresholds, recomputes complete acoustic candidates and cue/cut/source legs, and checks raw-ID/sentence/retained semantic-lock coverage. It does not transcribe, hear, choose safe cuts, authenticate supplied reviews, write app data or supply installation authority. Task data must supply current source IDs/clocks, caption groups, prior locks and actual review evidence; no private project is an operating dependency.

Owned capability planning: scripts/capability_preflight.py and scripts/test_capability_preflight.py use Python standard-library JSON/hash/files to select scoped next checks from current task observations. The entry, Gate0, assembly and recovery route to references/tool-preflight.md; templates/brief.json binds the task receipt. The calling agent invokes supported tools under their own provider contracts. This helper never installs, initializes a runtime, drives UI, hears, writes drafts or replaces current content/native evidence. Its file hashes are consistency evidence, not authentication.

Owned native production: scripts/native_timeline.py and templates/native-template.json compile source windows, independent captions and supporting video into the declared tested CapCut structure. Its separate create-new-only writer keeps editor/version/source/store/precision/backup/current-guard checks and exact readback. scripts/native_revision.py and its tests add only READDRAFT_UPDATE_OWNED: an actual immutable baseline preserves existing project/timeline identity, binds the exact index and nine before-file hashes, and uses a separately authorized per-file atomic revision with current guard and reconciliation. It never writes the shared index or another project. scripts/prepare_review_draft.py binds the explicit CREATE or owned-revision destination and complete pending inventories, never user consent or invented review. scripts/dependency_proof.py provides exact inherited frame-phase validation and claim-scoped unchanged-dependency adoption with original source bindings and reviewer provenance. Their local imports/template and meaningful tests are part of this package; a private task script is not a fallback dependency. Read native-pipeline.md before either write. The packaged producer supports new-project creation, this exact owned-revision operation and NO_SOURCE_REPEAT plans. Conditional source reuse and other existing-project operations retain their specialized policy and compatible-writer requirements; no force route is provided.

Owned optional derived-picture production: scripts/render_aroll_master.py and its
tests use Python standard library plus the sibling source_hash_session.py and
explicit existing FFmpeg/FFprobe executables. They normalize an explicitly chosen
picture FPS once, autorotate/contain-fit once, trim declared normalized frame
windows and concatenate H264 picture while copying supplied PCM16 stereo48k audio.
Current tool support, source FPS/canvas, hashes and frame/sample representability
must pass; no resampling or audio filter makes an invalid map fit. The receipt
binds commands/tools, source/output probes, exact decoded PCM and original-cut
crosswalk. scripts/source_derivation.py and its tests validate that crosswalk,
original history and current accepted master/slice identities before dependent
guard use. This guarded derived-history path currently supports one original to
one master at 30 fps; the renderer's standalone other-FPS checks do not extend it.
It recognizes the packaged render receipt and the explicitly supported legacy
task receipt by schema, rather than assuming their field names are interchangeable.
Neither helper hears, chooses words/cuts or grants native acceptance.
The rendered file cannot restore discarded original handles. Keep original
recordings and task evidence; never promote task media or receipts into this closure.

Generated media referenced by the native app belongs in a stable, compact
project-owned asset location chosen before rendering, separate from deep Teacher
evidence folders. The optional master.copyProvenance binding permits only a
checked same-byte copy while retaining the historical render/probe/crosswalk and
source file. It does not infer native relink success from existence/hash/probe or
grant move/delete/overwrite authority. Read the native pipeline for its exact
copy record and current native-path binding; no fixed universal path limit is
assumed.

Owned repeated-file verification: scripts/source_hash_session.py and its tests
provide call-scoped reuse only. The first access reads and hashes the full file,
checks the open handle and path before/after, and rechecks identity, size and
timestamps on reuse and exit. No persistent or caller-supplied hash cache is
accepted. The public pre-native guard starts a separate fresh session, including
when invoked inside preparation; its independent current check remains immediately
before the writer. This reduces duplicate large-media reads within a command,
not cross-run source verification. It is cooperative consistency, not protection
against an adversary restoring file metadata. A drift failure holds the operation.

## Shared owners

Resolve these one-way canonical skills through the current skill index: `video-production` for the encoded-video project lane; `design-production` for non-mechanical new visual systems/generated-visual routing; `voice` and `references/output-voice.md`/`output-handoff.md` for EN/VI authored reader copy before draft, after merge and handoff; `context-compression` and `references/task-continuity-contract.md` for multi-step state; `it-help` and `references/triage-and-prevention.md` for platform faults; `skill-manager` for reusable instruction/profile lifecycle; `project-structure-integrity-check` and `references/operational-independence.md` for readiness. Shared global tool-use and finish-line contracts retain their existing authority. Do not duplicate their bodies or require a reverse callback into the originating project.

## Runtimes

Preparation requires existing Python with its standard library and owned sibling
imports; task outputs are explicit and fresh. Most synthetic tests use inert
fixtures. The optional master-renderer's tests also create tiny synthetic video
through existing FFmpeg/FFprobe and verify real frame/rotation/PCM roundtrips;
these are mechanical tests, not actual-task or native acceptance. Missing tools
are reported as unavailable, never installed by tests. Production rendering also
requires the explicit currently authorized executable paths, fresh identities and
captured versions. Other optional routes use a pinned compatible draft CLI, a
local authorized speech aligner/transcriber or supported native CapCut control.
OpenChatCut needs its own approved runtime/service/license review. No automatic
installer, PATH/GPU change, remote upload, credential discovery or background server
is part of this closure.

## Readiness

Record closure hashes, actual runtime availability, selected branches and missing proof with task evidence. Prove execution without prohibited scratch roots using the shared independence owner's supported isolation method; copying the folder or changing cwd alone is insufficient. A shipped standalone package needs the selected shared-rule closure, rights and isolated operation. Static link/hash checks and synthetic helper tests may pass while isolated model behavior, font fit, actual media and native persistence remain unknown. Withhold those readiness claims rather than fabricate PASS.
