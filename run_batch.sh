#!/bin/bash
# Batch driver — Clay's channel list, 2026-11-20. One combined file per channel.
cd ~/workspace/youtube-transcripts || exit 1
LOG=~/workspace/youtube-transcripts/output/batch-2026-11-20.log
mkdir -p output
echo "BATCH START $(date)" >> "$LOG"
for handle in TimcastNews bennyjohnson arkansasmountainliving PinballPreparedness southernprepper1 RubinReport clayandbuck PBDPodcast Timcast RealDanBongino SurvivalLilly; do
  echo "=== $handle $(date) ===" >> "$LOG"
  ./venv/bin/python get_transcripts.py "@$handle" --days 30 --max 120 >> "$LOG" 2>&1
  echo "--- $handle done $(date) ---" >> "$LOG"
done
echo "BATCH END $(date)" >> "$LOG"
