#!/usr/bin/env python3
"""Bulk YouTube transcript puller — runs on Muggy's machine (Clay never touches code).

Usage:
  get_transcripts.py <channel-handle> [--days 30] [--max 120]
                     [--delay 12-22] [--out-dir output]

Writes one combined text file per channel per day under the output folder,
one section per video (TITLE / URL / transcript).

Resume design (corrected 2026-11-20 after Maggie's review):
  The per-video cache under <out>/cache/<channel>/<video-id>.json is the
  authoritative record — one file per successfully fetched transcript.
  The dated combined file is REBUILT from that cache on every run (and
  after every new save), so it always contains every selected video that
  has ever been saved for the channel, on any day. A re-run therefore
  never re-fetches a saved video and never silently drops one: the
  <channel>_done_ids.txt progress file is kept in step with the cache,
  and a progress entry with no cache entry behind it (for example from
  the pre-cache version) is first recovered by importing the sections of
  any existing combined files for the channel into the cache; if no saved
  transcript can be found for it anywhere, it is fetched again rather
  than skipped.

Failure handling (corrected 2026-11-20):
  Exit codes — 0 success (a legitimately empty date window is success);
  2 blocked by YouTube; 3 channel listing failed; 4 transport/unknown
  fetch failure. Failures are classified by exception TYPE, never by
  searching the exception message text. Only a genuine "no captions"
  outcome (NoTranscriptFound / TranscriptsDisabled, or a per-video
  unavailable outcome) is recorded in <channel>_no_transcript_ids.txt.
  A block or a network/transport failure stops the run, is NOT recorded
  as "no transcript", and exits non-zero, keeping everything saved so far.

Paced with randomized pauses (default 12-22 seconds; --delay 0-0 in tests).
Dates use the America/Phoenix (Arizona) calendar.
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
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
YTDLP = os.path.join(HERE, "venv", "bin", "yt-dlp")
ARIZONA = ZoneInfo("America/Phoenix")

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_LISTING_FAILED = 3
EXIT_FETCH_FAILED = 4

# Classification categories for a failed transcript fetch.
NO_TRANSCRIPT = "no_transcript"    # captions genuinely unavailable for this video
BLOCKED = "blocked"                # YouTube is blocking this machine's address
TRANSPORT = "transport"            # network / HTTP transport failure
UNKNOWN = "unknown"                # anything else — never counted as no-transcript


class ListingError(Exception):
    """The channel listing itself failed (distinct from an empty window)."""


def classify_fetch_error(exc):
    """Classify a fetch exception by its TYPE and cause chain.

    Returns one of NO_TRANSCRIPT, BLOCKED, TRANSPORT, UNKNOWN.
    Message text is never searched: RequestBlocked/IpBlocked messages do
    not contain those class names, which is how the old version
    misclassified blocks as "no transcript".
    """
    try:
        from youtube_transcript_api import _errors as yt_errors
    except Exception:
        yt_errors = None
    try:
        import requests
    except Exception:
        requests = None

    # Walk the exception and its cause/context chain: transport failures
    # are often wrapped inside a library exception.
    chain = []
    seen = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        chain.append(cur)
        cur = cur.__cause__ or cur.__context__

    if yt_errors is not None:
        # Blocked first: IpBlocked is a subclass of RequestBlocked.
        if any(isinstance(e, yt_errors.RequestBlocked) for e in chain):
            return BLOCKED
        # Genuine per-video "nothing to take" outcomes.
        no_caption_types = tuple(
            t for t in (getattr(yt_errors, n, None) for n in (
                "NoTranscriptFound", "TranscriptsDisabled",
                "VideoUnavailable", "VideoUnplayable", "AgeRestricted",
                "InvalidVideoId", "NotTranslatable",
                "TranslationLanguageNotAvailable"))
            if isinstance(t, type))
        if any(isinstance(e, no_caption_types) for e in chain):
            return NO_TRANSCRIPT
        # A request that failed at the HTTP layer is transport, not captions.
        if any(isinstance(e, yt_errors.YouTubeRequestFailed) for e in chain):
            return TRANSPORT
    if requests is not None:
        http_error = getattr(requests.exceptions, "HTTPError", None)
        if http_error is not None and any(
                isinstance(e, http_error) and
                getattr(getattr(e, "response", None), "status_code", None) == 429
                for e in chain):
            return BLOCKED
        if any(isinstance(e, requests.exceptions.RequestException)
               for e in chain):
            return TRANSPORT
    if any(isinstance(e, (ConnectionError, TimeoutError, OSError))
           for e in chain):
        return TRANSPORT
    return UNKNOWN


def get_channel_videos(channel_handle, days_back, max_videos):
    """Return the selected videos; raise ListingError if listing fails.

    An empty list is a legitimate result (no videos in the window) and is
    only returned when yt-dlp itself succeeded.
    """
    if not channel_handle.startswith("@"):
        channel_handle = "@" + channel_handle
    url = f"https://www.youtube.com/{channel_handle}/videos"
    cutoff = (datetime.now(ARIZONA) - timedelta(days=days_back)).strftime("%Y%m%d")
    # Full (non-flat) listing: flat mode returns no upload dates on this
    # machine, and --dateafter needs them. --no-check-certificates: this
    # machine's egress proxy presents a self-signed chain yt-dlp rejects.
    cmd = [YTDLP, "--no-check-certificates", "--dump-json",
           "--dateafter", cutoff,
           "--playlist-end", str(max_videos), url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ListingError(
            f"yt-dlp exited {result.returncode}: "
            f"{result.stderr.strip()[:300]}")
    videos = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            raise ListingError(f"unparseable yt-dlp output line: {e}")
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


# --- per-video cache -------------------------------------------------------

def cache_path(cache_dir, video_id):
    return os.path.join(cache_dir, f"{video_id}.json")


def cache_put(cache_dir, video_id, title, text):
    os.makedirs(cache_dir, exist_ok=True)
    tmp = cache_path(cache_dir, video_id) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"id": video_id, "title": title, "text": text}, f,
                  ensure_ascii=False)
    os.replace(tmp, cache_path(cache_dir, video_id))


def cache_get(cache_dir, video_id):
    path = cache_path(cache_dir, video_id)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


SECTION_RE = re.compile(
    r"TITLE: (.*)\nURL: https://youtu\.be/([A-Za-z0-9_-]+)\n=+\n"
    r"(.*?)(?=\n={10,}\nTITLE: |\Z)", re.DOTALL)


def import_legacy_outputs(out_dir, safe, cache_dir):
    """Recover transcripts saved by the pre-cache version.

    Parses every existing combined file for this channel and puts each
    section into the cache, so a progress entry from the old version is
    backed by a real saved transcript before resume decisions are made.
    Returns the number of sections imported.
    """
    imported = 0
    for name in sorted(os.listdir(out_dir)):
        if not (name.startswith(f"{safe}_transcripts_")
                and name.endswith(".txt")):
            continue
        with open(os.path.join(out_dir, name), encoding="utf-8",
                  errors="replace") as f:
            content = f.read()
        for title, vid_id, text in SECTION_RE.findall(content):
            if cache_get(cache_dir, vid_id) is None:
                cache_put(cache_dir, vid_id, title.strip(), text.strip())
                imported += 1
    return imported


def rebuild_combined(out_dir, output_file, videos, cache_dir):
    """Rewrite the combined file from the cache for the selected videos.

    Every selected video with a cache entry appears, in listing order,
    whatever day it was fetched. Written to a temp file and replaced in
    one step, so an interruption never leaves a half-written file.
    Returns the number of sections written.
    """
    sections = []
    for vid_id, _title in videos:
        entry = cache_get(cache_dir, vid_id)
        if entry is not None:
            sections.append(entry)
    if not sections:
        return 0
    tmp = output_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as out:
        for entry in sections:
            out.write(f"\n{'=' * 60}\nTITLE: {entry['title']}\n"
                      f"URL: https://youtu.be/{entry['id']}\n{'=' * 60}\n")
            out.write(entry["text"] + "\n")
    os.replace(tmp, output_file)
    return len(sections)


def read_id_file(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def append_id(path, video_id):
    with open(path, "a", encoding="utf-8") as f:
        f.write(video_id + "\n")


def parse_delay(spec):
    try:
        lo, hi = spec.split("-", 1)
        return float(lo), float(hi)
    except Exception:
        raise argparse.ArgumentTypeError(
            f"delay must look like 12-22, got {spec!r}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--max", type=int, default=120)
    ap.add_argument("--delay", type=parse_delay, default=(12.0, 22.0),
                    metavar="LO-HI",
                    help="pause range in seconds between fetches "
                         "(default 12-22; tests use 0-0)")
    ap.add_argument("--out-dir", default=OUT,
                    help="output folder (default: output/ beside the script)")
    args = ap.parse_args(argv)

    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", args.handle.lstrip("@"))
    stamp = datetime.now(ARIZONA).strftime("%Y%m%d")
    output_file = os.path.join(out_dir, f"{safe}_transcripts_{stamp}.txt")
    progress_file = os.path.join(out_dir, f"{safe}_done_ids.txt")
    no_transcript_file = os.path.join(out_dir, f"{safe}_no_transcript_ids.txt")
    cache_dir = os.path.join(out_dir, "cache", safe)

    # Recover any pre-cache saves before trusting the progress file.
    imported = import_legacy_outputs(out_dir, safe, cache_dir)
    if imported:
        print(f"Recovered {imported} previously saved transcript(s) "
              f"into the per-video cache.")

    done_ids = read_id_file(progress_file)
    no_transcript_ids = read_id_file(no_transcript_file)

    try:
        videos = get_channel_videos(args.handle, args.days, args.max)
    except ListingError as e:
        print(f"ERROR listing channel videos: {e}", file=sys.stderr)
        print(f"VERDICT: FAILED — channel listing failed; nothing was "
              f"fetched and nothing was recorded as no-transcript. "
              f"File: {output_file}")
        return EXIT_LISTING_FAILED

    print(f"Found {len(videos)} videos in the last {args.days} days. "
          f"Saving to {output_file}")
    if len(videos) >= args.max:
        print(f"NOTE: the {args.max}-video cap was reached; this may not "
              f"be the channel's complete {args.days}-day inventory.")

    saved = skipped = no_transcript = 0
    stop_code = EXIT_OK
    stop_reason = ""
    for i, (vid_id, title) in enumerate(videos, 1):
        if vid_id in no_transcript_ids:
            no_transcript += 1
            continue
        if vid_id in done_ids:
            if cache_get(cache_dir, vid_id) is not None:
                skipped += 1
                continue
            # Progress claims it but no saved transcript exists anywhere:
            # fetch it again rather than silently dropping it.
            print(f"WARNING: progress record lists {vid_id} but no saved "
                  f"transcript was found; fetching it again.")
        print(f"[{i}/{len(videos)}] {title}")
        try:
            text = fetch_transcript_text(vid_id)
        except Exception as e:
            category = classify_fetch_error(e)
            if category == NO_TRANSCRIPT:
                print(f"  -> no transcript available "
                      f"({type(e).__name__}); recorded as no-transcript.")
                append_id(no_transcript_file, vid_id)
                no_transcript_ids.add(vid_id)
                no_transcript += 1
                continue
            if category == BLOCKED:
                print("BLOCKED by YouTube — stopping; progress is saved. "
                      "This video was NOT recorded as no-transcript.")
                stop_code, stop_reason = EXIT_BLOCKED, "blocked by YouTube"
            elif category == TRANSPORT:
                print(f"NETWORK/TRANSPORT failure ({type(e).__name__}) — "
                      f"stopping; progress is saved. This video was NOT "
                      f"recorded as no-transcript.")
                stop_code, stop_reason = EXIT_FETCH_FAILED, "transport failure"
            else:
                print(f"UNEXPECTED failure ({type(e).__name__}: "
                      f"{str(e)[:150]}) — stopping; progress is saved. "
                      f"This video was NOT recorded as no-transcript.")
                stop_code, stop_reason = EXIT_FETCH_FAILED, "unexpected failure"
            break
        cache_put(cache_dir, vid_id, title, text)
        if vid_id not in done_ids:
            append_id(progress_file, vid_id)
            done_ids.add(vid_id)
        saved += 1
        # Keep the delivered file complete and current after every save,
        # so an interruption never loses or truncates what stands saved.
        rebuild_combined(out_dir, output_file, videos, cache_dir)
        lo, hi = args.delay
        if hi > 0:
            time.sleep(random.uniform(lo, hi))

    in_file = rebuild_combined(out_dir, output_file, videos, cache_dir)
    if stop_code != EXIT_OK:
        print(f"VERDICT: FAILED ({stop_reason}) — saved {saved} new, "
              f"already had {skipped}, no transcript {no_transcript}; "
              f"{in_file} saved transcript(s) stand in the file. "
              f"File: {output_file}")
        return stop_code
    print(f"VERDICT: saved {saved}, already had {skipped}, "
          f"no transcript {no_transcript}. File: {output_file}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
