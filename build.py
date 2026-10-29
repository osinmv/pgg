#!/usr/bin/env python3
"""Download the PGG sheet tab as CSV, build a static site into dist/.

Usage:
    python build.py                    # just build dist/
"""
import csv
import hashlib
import html
import io
import json
import re
import shutil
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

# ---- settings ---------------------------------------------------------------
SHEET_ID = "1AfdvWvnwxMeB2dwwA-cG6haao2VBVEgUrzK2YG6hKh4"
GID = "1686814201"                       # the tab with the players' segment lists
TITLE = "Retro Game Gauntlet"            # page title
PAGES_PROJECT = "rgg"                    # Cloudflare Pages project name
TWITCH = {                               # optional, by exact player name as in the sheet
          "Диана": "https://www.twitch.tv/dzmukin",
          "Максим": "https://www.twitch.tv/lightningmcsim",
          "Фирс": "https://www.twitch.tv/starkey_ru",
          "Александр": "https://www.twitch.tv/grom1k_",
          "Алина": "https://www.twitch.tv/l1ghtfury_bae",
          "Илья": "https://www.twitch.tv/dzmuh",
          "Элеонора Малая": "https://www.twitch.tv/elliottadderley",
          "Денис": "https://www.twitch.tv/marixyana__i",
          "Роман": "https://www.twitch.tv/corpuskulyar",
}
# -----------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "template.html"
AVATARS = ROOT / "avatars"      # put <Player name>.png here
DIST = ROOT / "dist"
HASH_FILE = ROOT / ".last_hash"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"


def fetch_csv():
    req = urllib.request.Request(CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8-sig")
    if raw.lstrip().lower().startswith(("<!doctype", "<html")):
        raise SystemExit("Got a web page instead of CSV: is the sheet shared as 'anyone with the link can view'?")
    return list(csv.reader(io.StringIO(raw)))


def twitch_url(v):
    """Accept a login ("somenick", "@somenick") or a full http(s) URL; anything else becomes a twitch.tv link."""
    v = v.strip()
    if not v:
        return ""
    if v.startswith(("http://", "https://")):
        return v
    return "https://www.twitch.tv/" + quote(v.lstrip("@"), safe="")


def escape_players(players):
    """HTML-escape every text value that came from the sheet."""
    for p in players:
        for k in ("id", "name", "twitch"):
            p[k] = html.escape(p[k])
        for r in p["rows"]:
            r["seg"] = html.escape(r["seg"])


def parse_blocks(rows):
    """Find every block that starts with: <player name> | Отрезок, then read the
    numbered rows below it (number | segment | progress like 0/1)."""
    players = []
    for r, row in enumerate(rows):
        for c in range(len(row) - 1):
            if row[c].strip() and row[c + 1].strip() == "Отрезок":
                items = []
                for rr in rows[r + 1:]:
                    def cell(k):
                        return rr[k].strip() if k < len(rr) else ""
                    if not cell(c).isdigit():
                        break
                    m = re.match(r"(\d+)\s*/\s*(\d+)", cell(c + 2))
                    items.append({
                        "n": int(cell(c)),
                        "seg": cell(c + 1).rstrip(",").strip(),
                        "done": bool(m) and int(m.group(2)) > 0 and int(m.group(1)) >= int(m.group(2)),
                    })
                name = row[c].strip()
                players.append({"id": re.sub(r"\s+", "_", name), "name": name,
                                "twitch": twitch_url(TWITCH.get(name, "")), "rows": items})
    return players


def attach_avatars(players):
    out = DIST / "avatars"
    for i, p in enumerate(players, 1):
        p["avatar"] = ""
        for ext in ("png", "jpg", "jpeg", "webp", "gif"):
            src = AVATARS / f"{p['name']}.{ext}"
            if src.exists():
                out.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, out / f"{i}.{ext}")
                p["avatar"] = f"avatars/{i}.{ext}"
                break
        done = sum(r["done"] for r in p["rows"])
        print(f"  {p['name']:<18} {done}/{len(p['rows'])}  avatar: {p['avatar'] or '-'}")


def build(players):
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    attach_avatars(players)
    escape_players(players)
    players.sort(key=lambda p: -sum(r["done"] for r in p["rows"]))  # most finished first, ties keep sheet order
    payload = json.dumps(players, ensure_ascii=False).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8")
    page = (page.replace("__PLAYERS__", payload)
                .replace("__TITLE__", TITLE)
                .replace("__UPDATED__", datetime.now().strftime("%d.%m.%Y %H:%M")))
    (DIST / "index.html").write_text(page, encoding="utf-8")


def data_hash(players):
    return hashlib.sha256(json.dumps(players, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def main():
    print("Downloading sheet...")
    players = parse_blocks(fetch_csv())
    if not players:
        raise SystemExit("No players found, not touching the site.")
    build(players)
    print(f"Built dist/index.html with {len(players)} players")


if __name__ == "__main__":
    main()
