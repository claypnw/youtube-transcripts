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
- `--max` — most videos to take (default 120).

## What it writes

Under `output/` beside the script:

- `<Channel>_transcripts_<YYYYMMDD>.txt` — the combined transcripts.
- `<Channel>_done_ids.txt` — the progress record. Re-running skips videos
  already saved, so an interrupted run picks up where it left off.

Requests are paced with randomized 12–22 second pauses. The program prints
a final `VERDICT:` line with the counts saved, already had, and skipped.

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
