#!/usr/bin/env python3
"""Nightly channel transcript consolidation — runs on Muggy's machine.

Clay's order, 2026-11-22: a recurring nightly job that looks at the
individual channel transcription files, folds any new ones into each
channel's combined file, and keeps track of what has already been
folded in so no transcription is ever combined twice.

How it runs, per channel:
  * The channel's dated batch files in output/ are compared — name,
    size, and SHA-256 hash — against consolidation-state.json, the
    standing record of the sources already folded in.
  * Nothing new or changed: the channel is left alone entirely.
  * New or changed sources: the combining program
    (consolidate_transcripts.py) re-runs for that channel alone, from
    a snapshot copy of its sources (so a download still writing to
    output/ can never tear a fold), and the channel's combined files
    are rebuilt whole — the combining program already dedupes by URL,
    so a video that stands in two batch files is carried once.
  * A combined file whose content changed is published to the
    repository claypnw/youtube-transcripts under consolidated/
    through the standing publish road (github_publish.py), and the
    matching copy in the Drive folder "Consolidated YouTube
    Transcripts" is replaced: the new version is uploaded, then the
    old copy is trashed (trash only, never a permanent delete). A
    combined letter that no longer stands is removed the same way on
    both sides.
  * The record is then updated for that channel and saved before the
    next channel is touched, so a stopped run never loses its place.

A night with nothing new anywhere: no publish, no Drive touch, one
printed line, exit 0. A fault — a publish verdict that is not PASS, a
Drive step that fails, a combined file the combining program marks
FAIL — is printed in plain words and the run exits 1 so the scheduled
job reports it the same night. A channel whose fold faults keeps its
old record entry, so the next night tries that channel again.

Usage: nightly_consolidate.py [--dry-run]
  --dry-run compares and reports only; it folds, publishes, and
  writes nothing.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "output")
DEST_DIR = os.path.join(HERE, "consolidated")
STATE_PATH = os.path.join(HERE, "consolidation-state.json")
LOCK_PATH = os.path.join(HERE, ".nightly_consolidate.lock")
CONSOLIDATOR = os.path.join(HERE, "consolidate_transcripts.py")
PUBLISHER = os.path.expanduser(
    "~/workspace/custom-connectors/custom.github/bin/github_publish.py")
GWS = "/opt/hatch/bin/hatch_gws_cli"
REPO = "youtube-transcripts"
DRIVE_FOLDER_ID = "1_Bk9zeyqFBEQytTyJf1wTsNJ_VH5Nu82"
TZ = ZoneInfo("America/Phoenix")

FILE_RE = re.compile(r"^(?P<channel>.+)_transcripts_(?P<date>\d{8})\.txt$")


def now_stamp():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M %Z")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_entry(path):
    return {
        "name": os.path.basename(path),
        "size": os.path.getsize(path),
        "sha256": sha256_of(path),
    }


def scan_sources():
    """channel -> [file_entry, ...] in date order, from output/."""
    found = {}
    for path in glob.glob(os.path.join(OUT_DIR, "*_transcripts_*.txt")):
        m = FILE_RE.match(os.path.basename(path))
        if not m:
            continue
        found.setdefault(m.group("channel"), []).append(
            (m.group("date"), path))
    return {
        channel: [file_entry(p) for _, p in sorted(paths)]
        for channel, paths in found.items()
    }


def combined_files(channel):
    """The channel's combined files as they stand in consolidated/."""
    out = []
    pattern = os.path.join(
        DEST_DIR, glob.escape(channel) + "_all_transcripts_*.txt")
    for path in sorted(glob.glob(pattern)):
        entry = file_entry(path)
        entry["md5"] = md5_of(path)
        out.append(entry)
    return out


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"version": 1, "updated": None, "channels": {}}
    with open(STATE_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_state(state):
    state["updated"] = now_stamp()
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, STATE_PATH)


def source_signature(entries):
    return [(e["name"], e["size"], e["sha256"]) for e in entries]


# ---------------------------------------------------------------- Drive

def gws_json(args):
    proc = subprocess.run(
        [GWS, "drive"] + args,
        capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(
            f"gws {' '.join(args[:3])} failed (exit {proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()[:400]}")
    text = proc.stdout.strip()
    return json.loads(text) if text else {}


def drive_folder_files():
    """name -> {id, size, md5} for the consolidated-files Drive folder."""
    params = {
        "q": f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
        "fields": "files(id,name,size,md5Checksum)",
        "pageSize": 1000,
    }
    result = gws_json(["files", "list", "--params", json.dumps(params)])
    out = {}
    for f in result.get("files", []):
        out[f["name"]] = {
            "id": f["id"],
            "size": int(f.get("size", 0)),
            "md5": f.get("md5Checksum"),
        }
    return out


def drive_upload(local_path, name):
    body = {"name": name, "parents": [DRIVE_FOLDER_ID]}
    result = gws_json([
        "files", "create",
        "--json", json.dumps(body),
        "--upload", local_path,
        "--upload-content-type", "text/plain",
    ])
    if not result.get("id"):
        raise RuntimeError(f"Drive upload of {name} returned no file id")
    return result["id"]


def drive_trash(file_id):
    gws_json([
        "files", "update",
        "--params", json.dumps({"fileId": file_id}),
        "--json", json.dumps({"trashed": True}),
    ])


def drive_sync(channel, new_combined, faults):
    """Make the Drive folder match the channel's combined files.

    New version uploaded first, old copy trashed after — a failed
    upload leaves the old copy standing and records a fault.
    """
    current = drive_folder_files()
    prefix = channel + "_all_transcripts_"
    wanted = {e["name"]: e for e in new_combined}
    for name, entry in sorted(wanted.items()):
        local_path = os.path.join(DEST_DIR, name)
        standing = current.get(name)
        if standing and standing["md5"] == entry["md5"]:
            continue
        try:
            drive_upload(local_path, name)
        except Exception as exc:  # noqa: BLE001 — fault is reported whole
            faults.append(f"{channel}: Drive upload of {name} failed: {exc}")
            continue
        if standing:
            try:
                drive_trash(standing["id"])
            except Exception as exc:  # noqa: BLE001
                faults.append(
                    f"{channel}: Drive trash of the old copy of {name} "
                    f"failed: {exc}")
    for name, standing in current.items():
        if name.startswith(prefix) and name not in wanted:
            try:
                drive_trash(standing["id"])
            except Exception as exc:  # noqa: BLE001
                faults.append(
                    f"{channel}: Drive trash of the removed file {name} "
                    f"failed: {exc}")


# ---------------------------------------------------------------- GitHub

def publish_changes(send, delete, faults, label):
    """One publish-road run for a channel's changed combined files."""
    if not send and not delete:
        return True
    args = [sys.executable, PUBLISHER, "--repo", REPO, "--branch", "main"]
    for local_path, target in send:
        args += ["--file", local_path, target]
    for target in delete:
        args += ["--delete", target]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=1800)
    out = proc.stdout + proc.stderr
    verdict = None
    for line in out.splitlines():
        if "VERDICT" in line:
            verdict = line.strip()
    if proc.returncode == 0 and verdict and "PASS" in verdict:
        return True
    faults.append(
        f"{label}: publish to {REPO} did not pass "
        f"(exit {proc.returncode}; verdict: {verdict or 'none printed'})")
    return False


# ---------------------------------------------------------------- fold

def fold_channel(channel, sources, faults):
    """Rebuild the channel's combined files from a snapshot of sources.

    Returns the new combined-file entries, or None when the combining
    program itself failed to run.
    """
    snapshot = tempfile.mkdtemp(prefix=f"consol-{channel}-")
    try:
        for entry in sources:
            shutil.copy2(os.path.join(OUT_DIR, entry["name"]),
                         os.path.join(snapshot, entry["name"]))
        proc = subprocess.run(
            [sys.executable, CONSOLIDATOR, channel,
             "--out-dir", snapshot, "--dest-dir", DEST_DIR],
            capture_output=True, text=True, timeout=1800)
        for line in proc.stdout.splitlines():
            print(f"  {line}")
        if proc.returncode not in (0, 1):
            faults.append(
                f"{channel}: the combining program stopped "
                f"(exit {proc.returncode}): "
                f"{(proc.stderr or '').strip()[:400]}")
            return None
        if proc.returncode == 1:
            # A single video crosses a cap on its own; the file stands
            # whole, but Clay hears about it the same night.
            faults.append(
                f"{channel}: the combining program marked a file FAIL "
                f"(a single video crosses a cap on its own; it was "
                f"carried whole, never cut)")
        return combined_files(channel)
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fold new channel transcription files into each "
                    "channel's combined files, publish and copy what "
                    "changed, and update the standing record.")
    ap.add_argument("--dry-run", action="store_true",
                    help="compare and report only; change nothing")
    args = ap.parse_args(argv)

    # One run at a time; a lock older than six hours is stale.
    if os.path.exists(LOCK_PATH):
        age = datetime.now().timestamp() - os.path.getmtime(LOCK_PATH)
        if age < 6 * 3600:
            print("Another consolidation run is already standing "
                  "(lock file present); this run ends.")
            return 0
        os.remove(LOCK_PATH)
    with open(LOCK_PATH, "w", encoding="utf-8") as fh:
        fh.write(now_stamp() + "\n")

    try:
        return run(args.dry_run)
    finally:
        try:
            os.remove(LOCK_PATH)
        except OSError:
            pass


def run(dry_run):
    state = load_state()
    recorded = state.setdefault("channels", {})
    current = scan_sources()
    faults = []
    folded = []

    for channel in sorted(set(current) | set(recorded)):
        if channel not in current:
            print(f"{channel}: no source files stand in output/ any "
                  f"more; its record and combined files are left as "
                  f"they stand.")
            continue
        sources = current[channel]
        old = recorded.get(channel)
        if old and source_signature(old.get("sources", [])) == \
                source_signature(sources):
            continue

        print(f"{channel}: new or changed source files — folding in.")
        if dry_run:
            folded.append(channel)
            continue

        new_combined = fold_channel(channel, sources, faults)
        if new_combined is None:
            continue

        old_combined = (old or {}).get("combined", [])
        old_by_name = {e["name"]: e for e in old_combined}
        send = []
        for entry in new_combined:
            prev = old_by_name.get(entry["name"])
            if not prev or prev["sha256"] != entry["sha256"]:
                send.append((os.path.join(DEST_DIR, entry["name"]),
                             f"consolidated/{entry['name']}"))
        new_names = {e["name"] for e in new_combined}
        delete = [f"consolidated/{name}" for name in old_by_name
                  if name not in new_names]

        ok = publish_changes(send, delete, faults, channel)
        if ok:
            drive_sync(channel, new_combined, faults)
            recorded[channel] = {
                "sources": sources,
                "combined": new_combined,
                "folded_at": now_stamp(),
            }
            save_state(state)
            folded.append(channel)
        else:
            print(f"{channel}: publish failed; its record is left "
                  f"unchanged so the next run tries again.")

    if not folded and not faults:
        print("Nothing new: every channel's sources match the record; "
              "no combined file was rebuilt, published, or copied.")
        return 0
    if folded and dry_run:
        print("Dry run only — nothing was written. Would fold in: " +
              ", ".join(folded) + ".")
    elif folded:
        print("Folded in: " + ", ".join(folded) +
              ". Changed combined files were published to "
              "claypnw/youtube-transcripts under consolidated/ and "
              "the Drive copies in 'Consolidated YouTube Transcripts' "
              "were replaced.")
    for fault in faults:
        print("FAULT: " + fault)
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())
