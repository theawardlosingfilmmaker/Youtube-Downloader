"""SanTube without a window: download from the command line (used by Claude in the
background; nothing appears on screen).

  python santube_cli.py URL [--mp4|--mp3|--wav|--m4a] [--quality 4k|2k|1080p|720p]
                         [--start 1:42:10 --end 1:42:25] [--out FOLDER] [--name NAME]
  python santube_cli.py --update          # update yt-dlp and ffmpeg now
  python santube_cli.py --info URL        # title, length, best quality available

Prints one JSON line at the end: {"ok": true, "file": "...", "bytes": ...} or {"ok": false, "error": "..."}.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import santube_core as core  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="SanTube headless downloader")
    ap.add_argument("url", nargs="?")
    g = ap.add_mutually_exclusive_group()
    for k in ("mp4", "mp3", "wav", "m4a"):
        g.add_argument(f"--{k}", dest="kind", action="store_const", const=k)
    ap.add_argument("--quality", default="1080p")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--out")
    ap.add_argument("--name")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--info", action="store_true")
    ap.add_argument("--no-update", action="store_true")
    a = ap.parse_args()
    try:
        if a.update:
            print(json.dumps({"ok": True, "update": core.update_all(force=True)}))
            if not a.url:
                return
        if not a.url:
            ap.error("give a URL")
        if not a.no_update:
            core.update_all()
        if a.info:
            i = core.info(a.url)
            hs = sorted({f.get("height") for f in i.get("formats", []) if f.get("height")})
            print(json.dumps({"ok": True, "title": i.get("title"), "channel": i.get("channel"),
                              "duration": i.get("duration"), "url": i.get("webpage_url"), "heights": hs}, ensure_ascii=False))
            return
        path = core.download(a.url, kind=a.kind or "mp4", quality=a.quality, start=a.start,
                             end=a.end, out_dir=a.out, name=a.name, auto_update=False)
        print(json.dumps({"ok": bool(path), "file": path,
                          "bytes": os.path.getsize(path) if path and os.path.exists(path) else None},
                         ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)[-500:]}))
        sys.exit(1)


if __name__ == "__main__":
    main()
