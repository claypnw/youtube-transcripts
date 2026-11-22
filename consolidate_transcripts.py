#!/usr/bin/env python3
"""Channel transcript consolidator — runs on Muggy's machine (Clay never touches code).

Why this stands (Clay's spec, 2026-11-22): Gemini has trouble with more
than 300 files, so each YouTube channel's transcriptions must stand
together in as few files as possible — every transcription for that
channel inside — under two hard caps on each combined file:
  * at most 475,000 words (whitespace-separated tokens, headers
    included). Clay's settled number: the hard line is 500,000 words,
    and the break is set at 475,000 to stay clear of it;
  * less than 200 megabytes (200,000,000 bytes) in size.
Whichever cap is reached first starts the next file.

Lettered files (Clay's spec, 2026-11-22): when a channel's
transcriptions would reach either cap, the program starts a second
file for that channel — file A, then B, then C, and so on — so a
channel stands as a lettered set of files, each one under both caps.
Files are filled with whole videos only: the split falls only at video
boundaries, a video is never cut in half; when the next whole video
would push the current file past either cap, that video starts the
next lettered file. A channel that fits in one file stands as _A
alone. If a single video on its own crossed either cap, it is still
carried whole in its own file and its report line says FAIL and names
it — it is never cut.

Usage:
  consolidate_transcripts.py [channel|all] [--check]
                             [--out-dir output] [--dest-dir consolidated]
                             [--max-words 475000] [--max-bytes 200000000]

Input: every dated batch file for the channel standing in the output
folder (<channel>_transcripts_<YYYYMMDD>.txt), read in date order.
A later batch file for a channel already holding an earlier one is
folded in the same way.

Output: the lettered set <channel>_all_transcripts_A.txt,
<channel>_all_transcripts_B.txt, ... in the consolidated folder.
Every video block is carried over whole, in order, in the standing
block form (the ==== line, TITLE:, URL:, ==== line, then the text).
A video that stands in more than one input file (same URL) is carried
once — the first copy wins. Re-running replaces the channel's earlier
combined files, so no stale letter is left standing.

One plain line is printed per lettered file: file name, video count,
word count, size, and PASS or FAIL against the two caps.
Exit code: 0 when every file passes, 1 when any file fails (only
possible when a single video crosses a cap on its own), 2 when a
named channel has no transcript files standing.
"""

import argparse
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "output")
DEFAULT_DEST = os.path.join(HERE, "consolidated")

MAX_WORDS = 475_000      # Clay's break point, clear of his 500,000-word line
MAX_BYTES = 200_000_000  # 200 MB, Clay's cap: each file stays under this

SEPARATOR = "=" * 60
FILE_RE = re.compile(r"^(?P<channel>.+)_transcripts_(?P<date>\d{8})\.txt$")


def parse_blocks(text):
    """Split one batch file's text into video blocks.

    Returns a list of (url, title, block_text) in file order. block_text
    is the whole standing block — opening ==== line through the last
    text line — with trailing blank lines stripped and exactly one
    trailing newline. Lines outside any block are not carried.
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
            title = lines[i + 1][len("TITLE: "):].strip()
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
            blocks.append((url, title, "\n".join(block_lines) + "\n"))
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


def gather_blocks(paths):
    """Read the batch files in order; return the deduped block list."""
    seen_urls = set()
    blocks = []
    for path in paths:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        for url, title, block in parse_blocks(text):
            if url in seen_urls:
                continue
            seen_urls.add(url)
            blocks.append((url, title, block))
    return blocks


def letter(index):
    """0 -> A, 1 -> B, ..., 25 -> Z, 26 -> AA, and so on."""
    out = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def pack(blocks, max_words, max_bytes):
    """Fill lettered files with whole videos only.

    Returns a list of dicts: letter, content, videos, words, bytes, and
    over — None, or (title, url, which caps) when the file holds a
    single video that crosses a cap on its own.
    """
    files = []
    cur_parts = []
    cur_videos = 0
    cur_words = 0
    cur_bytes = 0
    cur_first = None

    def close():
        nonlocal cur_parts, cur_videos, cur_words, cur_bytes, cur_first
        if not cur_parts:
            return
        over = None
        if cur_videos == 1 and (cur_words > max_words or cur_bytes >= max_bytes):
            caps = []
            if cur_words > max_words:
                caps.append(f"the word cap ({cur_words:,} of {max_words:,})")
            if cur_bytes >= max_bytes:
                caps.append(f"the size cap ({cur_bytes:,} bytes against "
                            f"{max_bytes:,})")
            over = (cur_first[0], cur_first[1], " and ".join(caps))
        files.append({
            "letter": letter(len(files)),
            "content": "".join(cur_parts),
            "videos": cur_videos,
            "words": cur_words,
            "bytes": cur_bytes,
            "over": over,
        })
        cur_parts = []
        cur_videos = 0
        cur_words = 0
        cur_bytes = 0
        cur_first = None

    for url, title, block in blocks:
        piece = "\n" + block
        piece_words = len(piece.split())
        piece_bytes = len(piece.encode("utf-8"))
        if cur_parts and (cur_words + piece_words > max_words
                          or cur_bytes + piece_bytes >= max_bytes):
            close()
        if not cur_parts:
            cur_first = (title, url)
        cur_parts.append(piece)
        cur_videos += 1
        cur_words += piece_words
        cur_bytes += piece_bytes
    close()
    return files


def run(channel_arg, out_dir, dest_dir, max_words, max_bytes, check_only):
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
        blocks = gather_blocks(found[channel])
        packed = pack(blocks, max_words, max_bytes)

        if not check_only:
            # Replace this channel's earlier combined files, so no stale
            # letter (or the old unlettered form) is left standing.
            os.makedirs(dest_dir, exist_ok=True)
            stale = glob.glob(os.path.join(
                dest_dir, glob.escape(channel) + "_all_transcripts*.txt"))
            for path in stale:
                os.remove(path)

        for f in packed:
            name = f"{channel}_all_transcripts_{f['letter']}.txt"
            if f["over"] is not None:
                any_fail = True
                title, url, caps = f["over"]
                verdict = (f"FAIL: the single video \"{title}\" ({url}) "
                           f"crosses {caps} on its own; carried whole, "
                           f"never cut")
            else:
                verdict = "PASS"
            if check_only:
                print(f"{name}: {f['videos']} videos, {f['words']:,} words, "
                      f"{f['bytes']:,} bytes — {verdict} "
                      f"(check only, not written)")
                continue
            target = os.path.join(dest_dir, name)
            with open(target, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(f["content"])
            # Read the written file back: the counts on disk rule.
            with open(target, "rb") as fh:
                raw = fh.read()
            text = raw.decode("utf-8", errors="replace")
            print(f"{name}: {text.count(chr(10) + 'TITLE: ')} videos, "
                  f"{len(text.split()):,} words, {len(raw):,} bytes — "
                  f"{verdict}")

    return 1 if any_fail else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Combine each channel's transcript batch files into "
                    "a lettered set of files per channel, each under "
                    "Clay's two caps (475,000 words; 200,000,000 bytes), "
                    "split only at video boundaries.")
    ap.add_argument("channel", nargs="?", default="all",
                    help="channel name, or 'all' (the default)")
    ap.add_argument("--check", action="store_true",
                    help="count and report only; write nothing")
    ap.add_argument("--out-dir", default=DEFAULT_OUT,
                    help="folder holding the dated batch files")
    ap.add_argument("--dest-dir", default=DEFAULT_DEST,
                    help="folder the combined files are written to")
    ap.add_argument("--max-words", type=int, default=MAX_WORDS,
                    help="word cap per file (default: Clay's 475,000)")
    ap.add_argument("--max-bytes", type=int, default=MAX_BYTES,
                    help="size cap per file in bytes (default: Clay's "
                         "200,000,000)")
    args = ap.parse_args(argv)
    return run(args.channel, args.out_dir, args.dest_dir,
               args.max_words, args.max_bytes, args.check)


if __name__ == "__main__":
    sys.exit(main())
