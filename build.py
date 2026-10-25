#!/usr/bin/env python3
"""Download the PGG sheet tab as CSV, build a static site into dist/.

Usage:
    python build.py                    # just build dist/
    python build.py --deploy wrangler  # build, upload to Cloudflare Pages if data changed
    python build.py --deploy git       # build, commit + push dist/ if data changed
    add --force to deploy even if nothing changed
"""
import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

# ---- settings ---------------------------------------------------------------
SHEET_ID = "1AfdvWvnwxMeB2dwwA-cG6haao2VBVEgUrzK2YG6hKh4"
GID = "1686814201"                       # the tab with the players' segment lists
TITLE = "Retro Game Gauntlet"            # page title
PAGES_PROJECT = "rgg"                    # Cloudflare Pages project name
TWITCH = {                               # optional, by exact player name as in the sheet
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
                                "twitch": TWITCH.get(name, ""), "rows": items})
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
    players.sort(key=lambda p: -sum(r["done"] for r in p["rows"]))  # most finished first, ties keep sheet order
    payload = json.dumps(players, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    html = (html.replace("__PLAYERS__", payload)
                .replace("__TITLE__", TITLE)
                .replace("__UPDATED__", datetime.now().strftime("%d.%m.%Y %H:%M")))
    (DIST / "index.html").write_text(html, encoding="utf-8")


def data_hash(players):
    return hashlib.sha256(json.dumps(players, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def deploy(method):
    if method == "wrangler":
        # needs `npx wrangler login` once, or CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID in the env
        subprocess.run(["npx", "wrangler", "pages", "deploy", str(DIST),
                        "--project-name", PAGES_PROJECT, "--branch", "main"], check=True)
    elif method == "git":
        subprocess.run(["git", "add", "dist"], cwd=ROOT, check=True)
        if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
            print("git: nothing to commit")
            return
        subprocess.run(["git", "commit", "-m", "update data"], cwd=ROOT, check=True)
        subprocess.run(["git", "push"], cwd=ROOT, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy", choices=["wrangler", "git"])
    ap.add_argument("--force", action="store_true", help="deploy even if data is unchanged")
    args = ap.parse_args()

    print("Downloading sheet...")
    players = parse_blocks(fetch_csv())
    if not players:
        raise SystemExit("No players found, not touching the site.")
    build(players)
    print(f"Built dist/index.html with {len(players)} players")

    if args.deploy:
        h = data_hash(players)
        if not args.force and HASH_FILE.exists() and HASH_FILE.read_text().strip() == h:
            print("Data unchanged, skipping deploy")
            return
        deploy(args.deploy)
        HASH_FILE.write_text(h)
        print("Deployed")


if __name__ == "__main__":
    main()
