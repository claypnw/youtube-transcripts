#!/usr/bin/env python3
"""Bulk YouTube transcript puller — runs on Muggy's machine (Clay never touches code).

Usage:
  get_transcripts.py <channel-handle> [--days 30] [--max 120]

Writes one combined text file per channel under output/, one section per video
(TITLE / URL / transcript). Resumable: a <channel>_done_ids.txt progress file
stands beside the output; videos already saved are skipped on a re-run.
Paced with randomized 12-22 second pauses. Stops cleanly if YouTube blocks
this machine's address, keeping everything saved so far.
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
YTDLP = os.path.join(HERE, "venv", "bin", "yt-dlp")


def get_channel_videos(channel_handle, days_back, max_videos):
    if not channel_handle.startswith("@"):
        channel_handle = "@" + channel_handle
    url = f"https://www.youtube.com/{channel_handle}/videos"
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
    # Full (non-flat) listing: flat mode returns no upload dates on this
    # machine, and --dateafter needs them. --no-check-certificates: this
    # machine's egress proxy presents a self-signed chain yt-dlp rejects.
    cmd = [YTDLP, "--no-check-certificates", "--dump-json",
           "--dateafter", cutoff,
           "--playlist-end", str(max_videos), url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("ERROR listing channel videos:", result.stderr.strip()[:300])
        return []
    videos = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        data = json.loads(line)
        upload_date = data.get("upload_date")
        if upload_date and upload_date < cutoff:
            continue
        if data.get("id"):
            videos.append((data["id"], data.get("title", "Untitled")))
    return videos


def fetch_transcript_text(video_id):
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id)
    return " ".join(snippet.text for snippet in transcript)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--max", type=int, default=120)
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", args.handle.lstrip("@"))
    stamp = datetime.now().strftime("%Y%m%d")
    output_file = os.path.join(OUT, f"{safe}_transcripts_{stamp}.txt")
    progress_file = os.path.join(OUT, f"{safe}_done_ids.txt")

    done_ids = set()
    if os.path.exists(progress_file):
        with open(progress_file, encoding="utf-8") as f:
            done_ids = {line.strip() for line in f if line.strip()}

    videos = get_channel_videos(args.handle, args.days, args.max)
    print(f"Found {len(videos)} videos in the last {args.days} days. "
          f"Saving to {output_file}")

    saved = skipped = failed = 0
    for i, (vid_id, title) in enumerate(videos, 1):
        if vid_id in done_ids:
            skipped += 1
            continue
        print(f"[{i}/{len(videos)}] {title}")
        try:
            text = fetch_transcript_text(vid_id)
        except Exception as e:
            msg = str(e)
            if "RequestBlocked" in msg or "IpBlocked" in msg or "429" in msg:
                print("BLOCKED by YouTube — stopping; progress is saved.")
                break
            print(f"  -> skipped (no transcript: {msg[:100]})")
            failed += 1
            continue
        with open(output_file, "a", encoding="utf-8") as out:
            out.write(f"\n{'=' * 60}\nTITLE: {title}\n"
                      f"URL: https://youtu.be/{vid_id}\n{'=' * 60}\n")
            out.write(text + "\n")
        with open(progress_file, "a", encoding="utf-8") as prog:
            prog.write(vid_id + "\n")
        done_ids.add(vid_id)
        saved += 1
        time.sleep(random.uniform(12, 22))

    print(f"VERDICT: saved {saved}, already had {skipped}, "
          f"no transcript {failed}. File: {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
