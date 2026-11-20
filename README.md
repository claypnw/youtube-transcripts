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
