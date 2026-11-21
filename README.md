# YouTube bulk transcript puller

One program: `get_transcripts.py`. Give it a channel handle; it pulls the
transcripts of that channel's recent videos and writes ONE combined text
file, one section per video (title, URL, full transcript text).

## What it needs

- Python 3 with two tools installed in a folder named `venv` beside the
  script:
  - `python3 -m venv venv`
  - `./venv/bin/pip install yt-dlp youtube-transcript-api`
- A network road to YouTube that is not blocked. The program runs from
  whatever machine runs it; if that machine's internet address is blocked
  by YouTube (the block that stopped the home PC), the program stops
  cleanly and keeps what it saved. It cannot unblock an address.

## How to run it

```
./venv/bin/python get_transcripts.py @ChannelHandle --days 30 --max 120
```

- `--days` — how far back to go (default 30).
- `--max` — most videos to take (default 120). If the cap is reached the
  program says so; the run may not be the channel's complete inventory
  for the window.
- `--delay LO-HI` — pause range in seconds between fetches
  (default 12-22; tests use `--delay 0-0`).
- `--out-dir` — output folder (default `output/` beside the script;
  tests use a throwaway folder so real progress records stay untouched).

Dates use the America/Phoenix (Arizona) calendar.

## What it writes

Under `output/` beside the script:

- `<Channel>_transcripts_<YYYYMMDD>.txt` — the combined transcripts for
  the selected window.
- `cache/<Channel>/<video-id>.json` — the authoritative per-video
  record: one file per saved transcript (title and full text). The
  combined file is REBUILT from this cache on every run and after every
  new save, so it always contains every selected video ever saved for
  the channel, whatever day it was fetched. A re-run on a later day
  produces that day's combined file complete — nothing already saved is
  re-fetched, and nothing already saved is silently dropped.
- `<Channel>_done_ids.txt` — the progress record, kept in step with the
  cache. Re-running skips videos already saved, so an interrupted run
  picks up where it left off. A progress entry with no saved transcript
  behind it is recovered from any existing combined file for the channel
  first; if no saved transcript exists anywhere, the video is fetched
  again rather than skipped.
- `<Channel>_no_transcript_ids.txt` — videos confirmed to have no
  captions to take. Only a genuine no-captions outcome lands here (see
  failure rules below); these are skipped on re-runs too.

Requests are paced with randomized 12–22 second pauses. The program prints
a final `VERDICT:` line with the counts saved, already had, and skipped.

## Failure rules and exit codes

Failures are classified by the exception's type, never by searching its
message text (a block message does not contain the word "blocked" in the
form the old version searched for, which is how blocks were once counted
as "no transcript").

- Exit 0 — success. A channel with no videos in the window is success
  and is reported as an empty window, not a failure.
- Exit 2 — YouTube blocked this machine's address mid-run. The run
  stops, everything saved so far stands, and the video that hit the
  block is NOT recorded as no-transcript.
- Exit 3 — the channel listing itself failed (for example a channel
  handle that does not exist). Nothing is fetched and nothing is
  recorded as no-transcript.
- Exit 4 — a network/transport failure, or an unexpected error, stopped
  the run. It is never counted as "no transcript".

Only `NoTranscriptFound` / `TranscriptsDisabled` (and per-video
unavailable outcomes such as a removed video) are recorded in the
no-transcript record.

## The batch driver

`run_batch.sh` runs the channel list and logs to
`output/batch-<date>.log`. Each channel's log line states its real
outcome (DONE, FAILED with its exit code, or BLOCKED). A blocked
channel halts the batch at once — later channels would be tried from
the same blocked address. The batch ends with a `BATCH VERDICT:` line
(completed / failed / blocked counts and the failed channels by name)
and exits non-zero if any channel failed or the batch was blocked.

Built 2026-11-20 on Muse's machine and proven end to end there
(@FoundMyFitness, one video, full transcript saved).

## The transcripts/ folder in this repository

The `transcripts/` folder holds the words the program pulled, stored here
with the program at Clay's direction (2026-11-20) so the pulled transcripts
stand in GitHub, not only on one machine. Each channel has two files:

- `<Channel>_transcripts_20261120.txt` — that channel's combined
  transcripts, one section per video (title, URL, full transcript text).
- `<Channel>_done_ids.txt` — the progress record: the number of every
  video already pulled for that channel. Any future run reads it first
  and skips those videos, so no transcript is ever pulled twice and an
  interrupted run picks up where it left off.

### The run that produced these files

Run 2026-11-20 on Muse's machine: Clay's 11 channels, 30 days back, up
to 120 videos per channel. 100 transcripts saved in all. Per channel
(counts from the run's own verdict lines):

| Channel | Saved | Videos with no transcript to take |
|---|---|---|
| TimcastNews | 43 | 57 |
| clayandbuck | 26 | 53 |
| bennyjohnson | 18 | 102 |
| Timcast | 9 | 20 |
| southernprepper1 | 3 | 5 |
| arkansasmountainliving | 1 | 10 |
| PBDPodcast | 0 | 8 |
| PinballPreparedness | 0 — no videos found in the last 30 days | — |
| RubinReport | 0 — no videos found in the last 30 days | — |
| RealDanBongino | 0 — no videos found in the last 30 days | — |
| SurvivalLilly | 0 — no videos found in the last 30 days | — |

Channels with no videos found, and PBDPodcast (videos found, none with a
transcript), have no transcript file. The FoundMyFitness file stands
from the program's first proof run the same day (1 video).
