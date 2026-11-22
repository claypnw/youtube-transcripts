#!/bin/bash
# Batch driver — the channel list read from the follow-lists store.
#
# Clay's order, 2026-11-22: the channels the transcription downloads
# follow stand in the follow-lists store, where Clay edits them on the
# follow-lists page. This driver takes its channel list from
# read_channels.py at the start of the run (the store first, the
# standing channels.txt list as its fallback). It is the standing
# driver from the next batch run on; run_batch.sh, with its written-in
# list, drove the runs through 2026-11-22 and is left standing as the
# record of those runs.
#
# Same run rules as run_batch.sh: a channel's real exit code decides
# its log line — a failure is logged FAILED with its code, never
# "done". A blocked run (exit 2) halts the whole batch at once, because
# every later channel would be tried from the same blocked address. The
# batch ends with a truthful BATCH VERDICT line and exits non-zero if
# any channel failed or the batch was blocked.
cd ~/workspace/youtube-transcripts || exit 1
LOG=~/workspace/youtube-transcripts/output/batch-$(date +%F).log
mkdir -p output
echo "BATCH START $(date)" >> "$LOG"
CHANNELS=$(./venv/bin/python read_channels.py 2>>"$LOG")
if [ -z "$CHANNELS" ]; then
  echo "BATCH VERDICT: no channel list could be read — the batch did not run." >> "$LOG"
  echo "BATCH END $(date)" >> "$LOG"
  exit 1
fi
echo "Channels for this run: $CHANNELS" >> "$LOG"
completed=0
failed=0
blocked=0
failed_channels=""
for handle in $CHANNELS; do
  echo "=== $handle $(date) ===" >> "$LOG"
  ./venv/bin/python get_transcripts.py "@$handle" --days 30 --max 120 >> "$LOG" 2>&1
  code=$?
  if [ "$code" -eq 0 ]; then
    completed=$((completed + 1))
    echo "--- $handle DONE (exit 0) $(date) ---" >> "$LOG"
  elif [ "$code" -eq 2 ]; then
    blocked=1
    failed=$((failed + 1))
    failed_channels="$failed_channels $handle(blocked,exit-2)"
    echo "--- $handle BLOCKED (exit 2) $(date) — halting batch: later channels would use the same blocked address ---" >> "$LOG"
    break
  else
    failed=$((failed + 1))
    failed_channels="$failed_channels $handle(exit-$code)"
    echo "--- $handle FAILED (exit $code) $(date) ---" >> "$LOG"
  fi
done
echo "BATCH VERDICT: completed $completed, failed $failed, blocked $blocked.${failed_channels:+ Failed channels:$failed_channels}" >> "$LOG"
echo "BATCH END $(date)" >> "$LOG"
if [ "$blocked" -ne 0 ]; then
  exit 2
fi
if [ "$failed" -ne 0 ]; then
  exit 1
fi
exit 0
