"""SanTube core: one download engine shared by the web app (app.py) and the
headless command line (santube_cli.py).

- Keeps yt-dlp, its YouTube helper (yt-dlp-ejs) and the deno JS runtime up to date
  (checked at most once a day, never blocks a download if the update fails).
- Keeps ffmpeg/ffprobe up to date on Windows (checked weekly; the old copy stays if
  anything goes wrong).
- Downloads: MP4 at 4K / 2K / 1080p / 720p (always H.264 + AAC, editor-ready),
  MP3 (320 kbps), WAV, or the original best audio, for a whole video or only a
  clip (start-end).
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
IS_WIN = platform.system() == "Windows"
STATE_FILE = os.path.join(HERE, ".santube_state.json")

# (max width, max height): widescreen films are limited by width, so "1080p" is 1920 wide.
QUALITIES = {"4k": (3840, 2160), "2160p": (3840, 2160), "2k": (2560, 1440), "1440p": (2560, 1440),
             "1080p": (1920, 1080), "fullhd": (1920, 1080), "720p": (1280, 720), "480p": (854, 480)}
AUDIO_FORMATS = ("mp3", "wav", "m4a")

FFMPEG_ZIP = ("https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/"
              "ffmpeg-master-latest-win64-gpl.zip")


# ----------------------------------------------------------------- state / log
def _state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(s):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=1)
    except Exception:
        pass


def _log(msg, log=None):
    (log or (lambda m: print(m, file=sys.stderr)))(msg)


# ----------------------------------------------------------------- ffmpeg
def ffmpeg_dir():
    """Folder holding ffmpeg (+ffprobe). The copy next to SanTube wins on Windows."""
    exe = "ffmpeg.exe" if IS_WIN else "ffmpeg"
    if os.path.exists(os.path.join(HERE, exe)):
        return HERE
    found = shutil.which("ffmpeg")
    return os.path.dirname(found) if found else None


def update_ffmpeg(force=False, log=None):
    """Windows only: replace ffmpeg.exe/ffprobe.exe with the latest build, weekly."""
    if not IS_WIN:
        return "skipped (not Windows)"
    s = _state()
    if not force and time.time() - s.get("ffmpeg_checked", 0) < 7 * 86400 and \
            os.path.exists(os.path.join(HERE, "ffmpeg.exe")):
        return "up to date (checked this week)"
    tmp = os.path.join(HERE, "_ffmpeg_update.zip")
    try:
        _log("Updating ffmpeg...", log)
        urllib.request.urlretrieve(FFMPEG_ZIP, tmp)
        with zipfile.ZipFile(tmp) as z:
            for name in z.namelist():
                base = os.path.basename(name)
                if base in ("ffmpeg.exe", "ffprobe.exe"):
                    new = os.path.join(HERE, base + ".new")
                    with z.open(name) as src, open(new, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    os.replace(new, os.path.join(HERE, base))
        s["ffmpeg_checked"] = time.time()
        _save_state(s)
        return "updated"
    except Exception as e:  # keep the old ffmpeg
        return f"update failed, kept the current ffmpeg ({e})"
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


# ----------------------------------------------------------------- yt-dlp
def update_ytdlp(force=False, log=None):
    """pip-upgrade yt-dlp (+ YouTube helper + deno) at most once a day."""
    s = _state()
    if not force and time.time() - s.get("ytdlp_checked", 0) < 86400:
        return "up to date (checked today)"
    _log("Updating yt-dlp...", log)
    cmd = [sys.executable, "-m", "pip", "install", "-q", "-U", "--disable-pip-version-check",
           "yt-dlp[default]", "deno"]
    if not IS_WIN and not os.environ.get("VIRTUAL_ENV") and sys.prefix == sys.base_prefix:
        cmd.insert(4, "--user")
    flags = 0x08000000 if IS_WIN else 0  # CREATE_NO_WINDOW: nothing flashes on screen
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
    if r.returncode == 0:
        s["ytdlp_checked"] = time.time()
        _save_state(s)
        return "updated"
    return "update failed: " + (r.stderr or r.stdout).strip()[-300:]


def update_all(force=False, log=None):
    return {"yt-dlp": update_ytdlp(force, log), "ffmpeg": update_ffmpeg(force, log)}


def _js_runtimes():
    rt = {}
    try:
        import deno  # pip package that ships the deno binary
        rt["deno"] = {"path": deno.find_deno_bin()}
    except Exception:
        pass
    if shutil.which("node"):
        rt["node"] = {}
    return rt or {"deno": {}}


def base_opts(log=None):
    """Options every yt-dlp call uses."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "js_runtimes": _js_runtimes(),
        "remote_components": ["ejs:github"],
        "retries": 5,
        "fragment_retries": 5,
    }
    fd = ffmpeg_dir()
    if fd:
        opts["ffmpeg_location"] = fd
    for name in ("cookies.txt", "cookiesforSantube.txt"):
        p = os.path.join(HERE, name)
        if os.path.exists(p) and os.path.getsize(p) > 0:
            opts["cookiefile"] = p
            break
    return opts


def _ytdlp():
    import yt_dlp  # an update installed while the app runs takes effect at the next start
    return yt_dlp


def info(url):
    yt_dlp = _ytdlp()
    with yt_dlp.YoutubeDL({**base_opts(), "skip_download": True}) as ydl:
        i = ydl.extract_info(url, download=False)
    if i and i.get("entries"):  # a search or playlist: describe the first video
        i = next(iter(i["entries"]), None) or i
    return i


def _ts(t):
    """'1:42:10' / '102:10' / '6130' / 6130.5 -> seconds (float)."""
    if t is None or t == "":
        return None
    if isinstance(t, (int, float)):
        return float(t)
    parts = [float(p) for p in str(t).strip().split(":")]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def _safe(name):
    keep = "-_.() "
    return "".join(c if c.isalnum() or c in keep else "_" for c in name).strip()[:120] or "clip"


def _ffmpeg_bin(name):
    fd = ffmpeg_dir()
    exe = name + (".exe" if IS_WIN else "")
    return os.path.join(fd, exe) if fd else name


def _probe_vcodec(path):
    try:
        r = subprocess.run([_ffmpeg_bin("ffprobe"), "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
                           capture_output=True, text=True,
                           creationflags=0x08000000 if IS_WIN else 0)
        return r.stdout.strip()
    except Exception:
        return ""


def _to_h264(path, log=None):
    """Make the file editor-ready: H.264 video + AAC audio in MP4. Tries the
    NVIDIA encoder first (fast), then the CPU encoder."""
    if _probe_vcodec(path) == "h264":
        return path
    out = os.path.splitext(path)[0] + ".h264.mp4"
    flags = 0x08000000 if IS_WIN else 0
    for vargs in (["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "18", "-b:v", "0"],
                  ["-c:v", "libx264", "-preset", "medium", "-crf", "17"]):
        cmd = [_ffmpeg_bin("ffmpeg"), "-y", "-v", "error", "-i", path, *vargs,
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", out]
        if subprocess.run(cmd, capture_output=True, creationflags=flags).returncode == 0:
            os.replace(out, os.path.splitext(path)[0] + ".mp4")
            if not path.endswith(".mp4"):
                os.remove(path)
            return os.path.splitext(path)[0] + ".mp4"
    _log("Could not convert to H.264; kept the original file.", log)
    return path


def download(url, kind="mp4", quality="1080p", start=None, end=None, out_dir=None,
             name=None, progress=None, log=None, auto_update=True, pad=0):
    """Download a video or audio file, whole or as a clip.

    kind: "mp4" | "mp3" | "wav" | "m4a"
    quality: "4k" | "2k" | "1080p" | "720p" | "480p" | "best" (video only)
    start/end: clip bounds ("1:42:10", "6130", 6130.5); both optional
    pad: extra seconds kept before start and after end (spare frames and audio
         for the edit; the 181st Degree rule is 10-15 s each side)
    Returns the saved file's path.
    """
    if auto_update:
        update_all(log=log)
    yt_dlp = _ytdlp()
    out_dir = out_dir or os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(out_dir, exist_ok=True)
    s, e = _ts(start), _ts(end)
    clip = s is not None or e is not None
    if clip and pad:
        s = max(0.0, (s or 0) - pad)
        e = e + pad if e is not None else None
    stem = _safe(name) if name else "%(title).90B"
    if clip:
        stem += f"_{int(s or 0)}-{int(e) if e is not None else 'end'}s" if name else \
            "_%(section_start)d-%(section_end)ds"
    opts = {**base_opts(log), "outtmpl": os.path.join(out_dir, stem + ".%(ext)s")}
    if progress:
        opts["progress_hooks"] = [progress]

    kind = (kind or "mp4").lower()
    if kind in AUDIO_FORMATS:
        opts["format"] = "bestaudio/best"
        if kind == "mp3":
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                                       "preferredquality": "320"}]
        elif kind == "wav":
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}]
        else:
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}]
    else:
        wh = QUALITIES.get(str(quality).lower())
        h = wh[1] if wh else None
        cap = f"[width<={wh[0]}][height<={wh[1]}]" if wh else ""
        # Highest resolution up to the chosen size first; H.264 only breaks ties.
        # VP9/AV1 (YouTube's 2K/4K) is converted to H.264 afterwards.
        opts["format"] = f"bv*{cap}+ba/b{cap}/bv*+ba/b"
        opts["format_sort"] = [f"res:{h}" if h else "res", "fps", "vcodec:avc1", "acodec:mp4a"]
        opts["merge_output_format"] = "mp4"
    if clip:
        opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [(s or 0, e if e is not None else float("inf"))])
        opts["force_keyframes_at_cuts"] = True

    saved = []

    def _done(d):
        if d.get("status") == "finished" and d.get("info_dict", {}).get("filepath"):
            saved.append(d["info_dict"]["filepath"])
    opts["postprocessor_hooks"] = [_done]

    with yt_dlp.YoutubeDL(opts) as ydl:
        inf = ydl.extract_info(url, download=True)
    path = saved[-1] if saved else None
    if not path:
        rd = (inf or {}).get("requested_downloads") or [{}]
        path = rd[-1].get("filepath") or (inf or {}).get("filepath")
    if path and kind not in AUDIO_FORMATS:
        path = _to_h264(path, log)
    return path
