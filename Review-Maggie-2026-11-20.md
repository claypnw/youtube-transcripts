# YouTube transcript program — Maggie's independent review

Review version 0.1 — November 20, 2026. Static source review; not a live batch PASS.

## Exact source reviewed

- get_transcripts.py — blob d03c0ba69a696e34147d9e401ec657a42de5d552
- run_batch.sh — blob 02a5c94bb98d8d9c9edd98823f1ae0860be05f17
- README states one FoundMyFitness video succeeded on Muggy's host. I have not independently rerun that test or the full batch.
- All 11 handles in the batch match Clay's channels.txt list. Defaults match the handoff: last 30 days, maximum 120 per channel, one combined channel text file.

## Corrections needed before claiming the full task finished

1. **Cross-day resume omits previously saved videos from the new daily combined file.** The global channel_done_ids.txt suppresses fetching across days while the output filename changes every day. A new day's file may therefore omit every earlier video still inside the selected window. Preserve existing outputs. Use an authoritative per-video cache and rebuild the complete selected channel collection from it, or another verified design that guarantees every selected cached video appears in the delivered combined file. Test same-day resume, next-day rerun, and interrupted output/checkpoint updates.
2. **Errors can report success.** A failed channel listing returns an empty list and main exits 0. A recognized block breaks the video loop, then main also exits 0. The batch shell ignores status and writes 'done' after every channel. Return distinct nonzero failure/blocked statuses, preserve partial output, and make the batch report actual completed/partial/blocked counts. A block should halt the batch rather than immediately trying the next channel from the same blocked address. A legitimate empty date window must remain distinguishable from a failed listing.
3. **Block classification searches only exception text.** RequestBlocked/IpBlocked may be exception type names without those literal names in their message. Classify explicit exception types and keep transport failures separate from genuinely unavailable captions. Generic network errors must not be counted as 'no transcript.'
4. **No analysis stage or finished user interface is shown.** Retrieval is useful, but Clay requested retrieval, download and analysis without him installing, typing or running commands. Supply readable per-channel results and a combined analysis with source/video references and coverage gaps. Use existing free capabilities; no new paid service or user setup is authorized by this review.
5. **TLS verification is disabled in listing.** The --no-check-certificates flag is explained as an environment certificate issue. Use a correctly trusted certificate chain on the approved host rather than treating disabled verification as a portable requirement. Record the actual test; do not ask Clay to fix his router or change IP addresses.
6. **Time and scope must be explicit.** The script uses host-local datetime.now(). Use the requested Arizona calendar/window or record the actual time zone. Report when the 120-video cap truncates a channel; do not call it a complete 30-day channel inventory unless that is verified.

## Acceptance evidence still required

- Complete 11-channel inventory with selected and retrieved counts, date window and each missing video/reason.
- Resumability proof that the delivered combined file remains complete across days and failures.
- A blocked-source test must produce a visible partial/failure outcome, never success or 'no transcript.'
- Actual transcript and analysis delivery Clay can use in Chrome without code or installation.
- Cloud execution independent of Clay's PC, and costs confirmed within existing free entitlements.

Maggie requests Muggy's independent response and corrected version/test record. Do not alter a running batch in place or delete partial results; stage and verify the corrected program before replacing the current source. This review does not authorize charges, rotate IPs, bypass service access controls, or certify production readiness.
