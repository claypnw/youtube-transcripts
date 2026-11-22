#!/usr/bin/env python3
"""Channel transcript consolidator — runs on Muggy's machine (Clay never touches code).

Why this stands (Clay's spec, 2026-11-22): Gemini has trouble with more
than 300 files, so each YouTube channel's transcriptions must stand as
ONE single file per channel — every transcription for that channel
inside it — under two hard caps on the combined file:
  * no more than 500,000 lines long;
  * less than 200 megabytes (200,000,000 bytes) in size.

Usage:
  consolidate_transcripts.py [channel|all] [--check]
                             [--out-dir output] [--dest-dir consolidated]
                             [--max-lines 500000] [--max-bytes 200000000]

Input: every dated batch file for the channel standing in the output
folder (<channel>_transcripts_<YYYYMMDD>.txt), read in date order.
A later batch file for a channel already holding an earlier one is
folded in the same way.

Output: ONE combined file, <channel>_all_transcripts.txt, in the
consolidated folder. Every video block is carried over whole, in order,
in the standing block form (the ==== line, TITLE:, URL:, ==== line,
then the text). A video that stands in more than one input file (same
URL) is carried once — the first copy wins.

Caps: the combined file is built and counted BEFORE anything is
written. If it would cross a cap, nothing is written for that channel
and a FAIL line names the cap and by how much — the file is never
silently split or cut.

One plain line is printed per channel: file name, video count, line
count, size, and PASS or FAIL against the two caps.
Exit code: 0 when every channel passes, 1 when any channel fails,
2 when a named channel has no transcript files standing.
"""

import argparse
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "output")
DEFAULT_DEST = os.path.join(HERE, "consolidated")

MAX_LINES = 500_000
MAX_BYTES = 200_000_000  # 200 MB, Clay's cap: the file must stay under this

SEPARATOR = "=" * 60
FILE_RE = re.compile(r"^(?P<channel>.+)_transcripts_(?P<date>\d{8})\.txt$")


def parse_blocks(text):
    """Split one batch file's text into video blocks.

    Returns a list of (url, block_text) in file order. block_text is the
    whole standing block — opening ==== line through the last text line —
    with trailing blank lines stripped and exactly one trailing newline.
    Lines that stand outside any block are not carried.
    """
    lines = text.split("\n")
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        if (
            lines[i].strip("=") == ""
            and len(lines[i]) >= 10
            and i + 3 < n
            and lines[i + 1].startswith("TITLE: ")
            and lines[i + 2].startswith("URL: ")
            and lines[i + 3].strip("=") == ""
            and len(lines[i + 3]) >= 10
        ):
            url = lines[i + 2][len("URL: "):].strip()
            j = i + 4
            body = []
            while j < n:
                if (
                    lines[j].strip("=") == ""
                    and len(lines[j]) >= 10
                    and j + 3 < n
                    and lines[j + 1].startswith("TITLE: ")
                    and lines[j + 2].startswith("URL: ")
                    and lines[j + 3].strip("=") == ""
                    and len(lines[j + 3]) >= 10
                ):
                    break
                body.append(lines[j])
                j += 1
            while body and body[-1] == "":
                body.pop()
            block_lines = [SEPARATOR, lines[i + 1], lines[i + 2], SEPARATOR] + body
            blocks.append((url, "\n".join(block_lines) + "\n"))
            i = j
        else:
            i += 1
    return blocks


def channel_files(out_dir):
    """Map channel name -> its dated batch files, in date order."""
    found = {}
    for path in glob.glob(os.path.join(out_dir, "*_transcripts_*.txt")):
        m = FILE_RE.match(os.path.basename(path))
        if not m:
            continue
        found.setdefault(m.group("channel"), []).append((m.group("date"), path))
    for channel in found:
        found[channel] = [p for _, p in sorted(found[channel])]
    return found


def build_combined(paths):
    """Read the batch files in order; return (content, video_count)."""
    seen_urls = set()
    parts = []
    count = 0
    for path in paths:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        for url, block in parse_blocks(text):
            if url in seen_urls:
                continue
            seen_urls.add(url)
            parts.append("\n" + block)
            count += 1
    return "".join(parts), count


def fmt_size(num_bytes):
    return f"{num_bytes:,} bytes"


def run(channel_arg, out_dir, dest_dir, max_lines, max_bytes, check_only):
    found = channel_files(out_dir)
    if channel_arg == "all":
        channels = sorted(found)
        if not channels:
            print(f"no channel transcript files stand in {out_dir}")
            return 2
    else:
        if channel_arg not in found:
            print(f"{channel_arg}: no transcript files stand in {out_dir}")
            return 2
        channels = [channel_arg]

    any_fail = False
    for channel in channels:
        name = f"{channel}_all_transcripts.txt"
        content, videos = build_combined(found[channel])
        line_count = len(content.splitlines())
        byte_count = len(content.encode("utf-8"))

        over = []
        if line_count > max_lines:
            over.append(
                f"over the line cap by {line_count - max_lines:,} lines "
                f"({line_count:,} of {max_lines:,})"
            )
        if byte_count >= max_bytes:
            over.append(
                f"over the size cap by {byte_count - max_bytes + 1:,} bytes "
                f"({fmt_size(byte_count)} against a {fmt_size(max_bytes)} cap)"
            )
        if over:
            any_fail = True
            print(f"{name}: {videos} videos, {line_count:,} lines, "
                  f"{fmt_size(byte_count)} — FAIL: " + "; ".join(over)
                  + " — nothing written")
            continue

        if check_only:
            print(f"{name}: {videos} videos, {line_count:,} lines, "
                  f"{fmt_size(byte_count)} — PASS (check only, not written)")
            continue

        os.makedirs(dest_dir, exist_ok=True)
        target = os.path.join(dest_dir, name)
        with open(target, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        # Read the written file back: the counts that stand on disk rule.
        with open(target, "rb") as fh:
            raw = fh.read()
        disk_lines = len(raw.decode("utf-8", errors="replace").splitlines())
        print(f"{name}: {videos} videos, {disk_lines:,} lines, "
              f"{fmt_size(len(raw))} — PASS")

    return 1 if any_fail else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Combine each channel's transcript batch files into "
                    "one file per channel, under Clay's two caps.")
    ap.add_argument("channel", nargs="?", default="all",
                    help="channel name, or 'all' (the default)")
    ap.add_argument("--check", action="store_true",
                    help="count and report only; write nothing")
    ap.add_argument("--out-dir", default=DEFAULT_OUT,
                    help="folder holding the dated batch files")
    ap.add_argument("--dest-dir", default=DEFAULT_DEST,
                    help="folder the combined files are written to")
    ap.add_argument("--max-lines", type=int, default=MAX_LINES,
                    help="line cap (default: Clay's 500,000)")
    ap.add_argument("--max-bytes", type=int, default=MAX_BYTES,
                    help="size cap in bytes (default: Clay's 200,000,000)")
    args = ap.parse_args(argv)
    return run(args.channel, args.out_dir, args.dest_dir,
               args.max_lines, args.max_bytes, args.check)


if __name__ == "__main__":
    sys.exit(main())
