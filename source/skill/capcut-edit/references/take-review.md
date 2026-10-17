# Review repeated ideas and select usable takes

| Need | Path | Rule |
|---|---|---|
| Bind the whole source | [Source coverage](#source-coverage) | Keep the original recognition history and account for source regions it omitted. |
| Find variants of one idea | [Group occurrences by meaning](#group-occurrences-by-meaning) | Small wording differences do not make a restarted idea unique content. |
| Choose the retained reading | [Select the last usable occurrence](#select-the-last-usable-occurrence) | Recording order follows completeness, speaker and coherence checks. |
| Build the actual cut | [Apply the selection](#apply-the-selection) | Preserve complete speech, explicit rejections and source-to-output mapping. |
| Catch omissions before audio review | [Check the assembled candidate](#check-the-assembled-candidate) | Compare actual candidate speech with selected units before closing feedback. |
| Record evidence and finish | [Proof and acceptance](#proof-and-acceptance) | Model proposals, text judgment and actual listening remain separate. |

Read this leaf for CONTENT_EDIT take selection or a reported repeated/restarted
idea. It supplements [Content and captions](content-captions.md#take-selection).
It does not authorize content changes for subtitle-only work or supply hearing.

## Source coverage

Keep the complete original ASR document and its source/audio identity immutable.
Build a task-owned occurrence inventory across the whole authorized recording,
including abandoned starts, incomplete clauses, later corrections and voiced
islands omitted by the first model. An ASR segment is neither a logical sentence
nor one take. A single word allocated across a long pause, multiple voiced islands
or a restart is an anomaly to inspect, not a continuous word to preserve blindly.

For each occurrence record a stable id, proposed idea-unit id, original source
identity and in/out, recording order, exact candidate wording with uncertainty,
main/prompter/other/unknown speaker, completeness, relevant facts and neighboring
context. Keep undecided occurrences visible. A script is reference-only unless
explicitly bound otherwise; it is not evidence of what was actually spoken.

## Group occurrences by meaning

Scan both exact wording and semantic variants. Treat two attempts as candidates
for the same idea when they express the same intended claim, action or causal
link in the same local delivery, even if one omits a few words, changes a small
connector, uses a synonym, or stops halfway. A repeated opening followed by a
longer completion is a restart candidate. For example, versions beginning
“vì khi có chuyện xảy ra” and “vì khi có việc xảy ra” may be attempts at the same
claim; a literal string comparison would miss them. Inspect their complete clauses,
recording order, continuation and source context before deciding.

Compare speaker, subject, action, object, claim/result, numbers, negation,
conditions and qualifications. Changed filler or small grammar alone does not
establish a new idea. Changed facts, a contrast, an added necessary qualification,
a different question or deliberate rhetorical repetition may be distinct required
content. Do not discard them from a keyword match or a fixed similarity score.
Use uncertainty rather than silently replacing a material fact with a near match.

Group the complete restart chain, including a short fragment followed by two
longer attempts; do not stop after finding one matching pair. Review the source
before and after each boundary so a trailing fragment cannot survive outside the
selected ASR word list. Actual repeated speech takes precedence over one textual
occurrence or unique raw IDs.

## Select the last usable occurrence

Within each reviewed idea unit, work backward through recording order. Keep the
last complete, usable main-speaker occurrence that expresses the required idea
coherently and joins its neighboring units naturally. A later partial start,
misread, contradictory fact, clipped word or prompter line is not the winning
take merely because it is later. If the last full attempt is usable, reject the
earlier same-idea attempts and partial lead-ins even when their wording differs.
If no attempt is usable, hold that unit instead of dropping or inventing speech.

Record ACCEPT/REJECT/HELD per occurrence and a concrete reason: selected latest
usable full reading, superseded same-idea reading, partial restart, wrong speaker,
misread, meaningful deliberate repeat, or unresolved. Preserve the whole accepted
clause and its useful context. Prefer one complete original occurrence to a
sentence assembled from incompatible fragments of different attempts.

## Apply the selection

Map every accepted and rejected occurrence to exact original source windows.
Remove superseded speech as a take/content edit, not as a quiet-only cut. Reject
its earlier complete clause and loose restart fragments, then check the joins at
the full first/last syllables. Do not start the winning take at its loudest vowel,
borrow a preceding rejected tail, or let phonetic handles reintroduce an earlier
attempt. Preserve normal speed, source trim handles and unchanged other units.

Retain original raw history separately. Keep rejected original IDs with their
reason, and bind selected/refined words and any previously omitted words to their
actual source events with explicit old/new provenance. New proposed IDs may be
needed; never invent a correspondence, mutate the original ASR, force the new
word count to equal the old one, or shorten an old word interval merely to pass.
Reconcile affected sentence/cue locks and display transforms explicitly, then
rebuild current audio, source maps, caption STARTs and END-only holds and B-roll.

## Check the assembled candidate

Before closing audio feedback, compare the stable assembled candidate's transcript
and retained speech with the selected idea units. A fresh local transcription on
that exact audio is useful when the source model omitted or stretched words;
reuse an identity-valid existing candidate transcript rather than rerunning it.
Scan complete and partial repeated meanings across neighboring clauses, extra
voiced islands, words missing from the selected inventory, and abrupt transitions.
An unexplained repeated claim or unrepresented speech is a review item even when
the raw-ID and source-overlap checks pass.

Model differences propose investigation, not automatic content deletion or a
hearing PASS. Review actual source and joined contexts, especially any proposed
cut inside one word or protected spoken phrase. If a user reports a repeat,
inventory all analogous attempts in that idea unit and select its last usable
full occurrence; do not patch only the named repeated token. If a user reports a
clipped join, restore the necessary original speech and test the entire phrase.

## Proof and acceptance

Keep the occurrence inventory, accepted/rejected source ranges, immutable raw
crosswalk, exact pre/post audio sample mapping, detector/model proposals and
before/after listening contexts with the task. Short excerpts must contain full
neighboring words, not create a demonstration-only clipped syllable.

Send the checked listening copy under the official audio-first checkpoint. Bind
the real user's reviewed scope and resolve concrete defects on the current audio
before any native apply. Reuse unaffected accepted content and request only the
changed context where that supplies the missing evidence; do not claim personal
hearing or make the user repeat an unchanged approval. A content recut invalidates
its dependent clock. Current native caption/picture, separate editability and
save–close–reopen proof still follow; a model or inventory cannot certify them.
