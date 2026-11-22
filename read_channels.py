#!/usr/bin/env python3
"""Print the YouTube channels the transcription downloads follow.

Clay's order, 2026-11-22: the channel list stands in the follow-lists
store (a Cloudflare D1 database named "follow-lists", table
youtube_channels), where Clay edits it himself on the follow-lists
page of the menu site. This reader is the batch driver's road to that
list: it reads the store and prints one channel handle per line on
stdout, in the order Clay's list stands.

The fallback: channels.txt, standing beside this program, holds the
list as last read from the store. When the store cannot be read, the
reader prints channels.txt instead and says so on stderr — a run is
never left with no list, and the fallback is never silent. When the
store read succeeds, channels.txt is refreshed from it, so the
fallback stands current.

The environment variable FOLLOW_LISTS_DB_ID overrides the store's
database id; it exists so the fallback road can be proven in tests.

Usage: read_channels.py            (handles on stdout, notes on stderr)
Exit:  0 when a list was printed (from either road), 1 when neither
       road produced a list.
"""

import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

HERE = os.path.dirname(os.path.abspath(__file__))
FALLBACK_PATH = os.path.join(HERE, "channels.txt")
CF_HOST = "api.cloudflare.com"
ACCOUNT_ID = "ff015afa0634d0159522bdc5094c5d08"
DATABASE_ID = os.environ.get(
    "FOLLOW_LISTS_DB_ID", "0f930f60-58d2-475f-a083-68383fe8fa14")
TABLE = "youtube_channels"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused")


def read_store():
    """The store's channel handles, in list order. Raises on failure."""
    body = json.dumps({
        "sql": f"SELECT handle FROM {TABLE} ORDER BY rowid",
    }).encode()
    request = urllib.request.Request(
        f"https://{CF_HOST}/client/v4/accounts/{ACCOUNT_ID}"
        f"/d1/database/{DATABASE_ID}/query",
        data=body, headers={"Content-Type": "application/json"},
        method="POST")
    add_surrogate_to_request(request, "custom.cloudflare",
                             allowed_hosts=[CF_HOST])
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=60) as response:
        payload = read_json_response(response)
    if not payload.get("success", True):
        raise RuntimeError(f"store answered not-success: "
                           f"{str(payload.get('errors'))[:200]}")
    rows = payload["result"][0]["results"]
    return [row["handle"] for row in rows]


def read_fallback():
    if not os.path.exists(FALLBACK_PATH):
        return []
    with open(FALLBACK_PATH, encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip()]


def write_fallback(handles):
    tmp = FALLBACK_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(handles) + "\n")
    os.replace(tmp, FALLBACK_PATH)


def main():
    try:
        handles = read_store()
        if not handles:
            raise RuntimeError("the store's list came back empty")
    except Exception as exc:  # noqa: BLE001 — fallback is the design
        handles = read_fallback()
        if not handles:
            print(f"read_channels: the store could not be read ({exc}) "
                  f"and no fallback list stands in channels.txt",
                  file=sys.stderr)
            return 1
        print(f"read_channels: the follow-lists store could not be "
              f"read ({exc}); using the standing channels.txt list "
              f"instead ({len(handles)} channels)", file=sys.stderr)
        print("\n".join(handles))
        return 0
    try:
        write_fallback(handles)
    except Exception as exc:  # noqa: BLE001 — noted, never blocking
        print(f"read_channels: channels.txt could not be refreshed "
              f"({exc}); the store list still stands for this run",
              file=sys.stderr)
    print("\n".join(handles))
    return 0


if __name__ == "__main__":
    sys.exit(main())
