#!/bin/bash
# Retry driver for the 2026-11-22 re-run: YouTube has flagged this
# machine's address ("Sign in to confirm you're not a bot" at listing,
# RequestBlocked at fetch) after the day's heavy downloading.
#
# Standing rule since 2026-11-22: after a bot-check flag, WAIT HOURS,
# not minutes — the wait below is 3 hours (10800 seconds) between test
# fetches, and the same 3 hours after a batch that stops on the flag.
# Every added ask against a standing flag risks extending it, so the
# driver makes exactly one test fetch per wait and nothing more.
# Progress is saved per video, so every batch attempt advances the
# set. Gives up after 6 batch attempts and leaves the state standing
# for the report.
cd ~/workspace/youtube-transcripts || exit 1
DLOG=output/rerun-driver-2026-11-22.log
TEST_ID=rfQLy4ZP76k
FLAG_WAIT=10800
attempt=0
while [ "$attempt" -lt 6 ]; do
  # Test whether the flag has lifted — one fetch, nothing more.
  ./venv/bin/python - "$TEST_ID" >> "$DLOG" 2>&1 <<'PYEOF'
import sys
from youtube_transcript_api import YouTubeTranscriptApi
try:
    t = YouTubeTranscriptApi().fetch(sys.argv[1])
    print("TEST FETCH OK", len(" ".join(s.text for s in t)))
except Exception as e:
    print("TEST FETCH FAILED", type(e).__name__)
    sys.exit(1)
PYEOF
  if [ $? -ne 0 ]; then
    echo "$(date) bot-check flag still standing — waiting 3 hours before the next test fetch" >> "$DLOG"
    sleep $FLAG_WAIT
    continue
  fi
  attempt=$((attempt + 1))
  echo "$(date) test fetch OK — batch attempt $attempt" >> "$DLOG"
  ./run_batch.sh
  code=$?
  echo "$(date) batch attempt $attempt exited $code" >> "$DLOG"
  if [ "$code" -eq 0 ]; then
    echo "$(date) BATCH COMPLETE" >> "$DLOG"
    exit 0
  fi
  if [ "$code" -eq 2 ]; then
    echo "$(date) batch stopped on the bot-check flag — waiting 3 hours before the next test fetch" >> "$DLOG"
    sleep $FLAG_WAIT
  else
    echo "$(date) batch ended with failures (exit $code) — waiting 30 minutes before the next attempt" >> "$DLOG"
    sleep 1800
  fi
done
echo "$(date) GAVE UP after 6 batch attempts" >> "$DLOG"
exit 1
