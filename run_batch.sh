#!/bin/bash
# Batch driver — Clay's channel list, 2026-11-20. One combined file per channel.
#
# Corrected 2026-11-20 after Maggie's review: a channel's real exit code
# decides its log line — a failure is logged FAILED with its code, never
# "done". A blocked run (exit 2) halts the whole batch at once, because
# every later channel would be tried from the same blocked address.
# Since 2026-11-22 exit 2 also covers YouTube's bot-check flag at the
# listing step ("Sign in to confirm you're not a bot"), so a flagged
# address stops the batch at the first channel that hits it. The
# batch ends with a truthful BATCH VERDICT line and exits non-zero if any
# channel failed or the batch was blocked.
cd ~/workspace/youtube-transcripts || exit 1
LOG=~/workspace/youtube-transcripts/output/batch-$(date +%F).log
mkdir -p output
echo "BATCH START $(date)" >> "$LOG"
completed=0
failed=0
blocked=0
failed_channels=""
first=1
for handle in TimcastNews bennyjohnson arkansasmountainliving PinballPreparedness southernprepper1 RubinReport clayandbuck PBDPodcast Timcast RealDanBongino SurvivalLilly; do
  # Pacing between channels (added 2026-11-22): a 180-second pause
  # before every channel after the first, so a full batch spreads its
  # asks instead of firing eleven channel listings back to back — part
  # of what tripped YouTube's bot-check flag on 2026-11-22.
  if [ "$first" -eq 0 ]; then
    echo "--- pausing 180 seconds between channels ---" >> "$LOG"
    sleep 180
  fi
  first=0
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
