# SanTube

San's own YouTube downloader. Two ways to use it:

1. **The SanTube page** (for San): open **SanTube** from the Desktop or Start Menu. Search or paste a link, open the video, press **Download**, and pick:
   - **4K / 2K / Full HD / 720p MP4** (always H.264 + AAC, ready for Premiere Pro and Resolve)
   - **Music: MP3 320** or **WAV**
   - optional **Clip** start and end (e.g. `1:42:10` to `1:42:25`) to download only that part
2. **Headless** (for Claude and scripts, nothing appears on screen):
   ```
   python santube_cli.py URL --mp4 --quality 1080p --start 1:42:10 --end 1:42:25 --out clips --name sholay_freeze
   python santube_cli.py URL --mp3 --start 0:30 --end 1:10
   python santube_cli.py URL --info
   python santube_cli.py --update
   ```
   It prints one JSON line: `{"ok": true, "file": "...", "bytes": ...}`.

## Stays working by itself

- yt-dlp (+ its YouTube helper and the deno JS runtime) is updated automatically, at most once a day.
- ffmpeg/ffprobe are updated automatically every week (Windows). If an update fails, the old copy keeps working.
- The server starts quietly when Windows starts and keeps running in the background. Closing the browser tab no longer stops it. Only this PC can open it (127.0.0.1).

## Install or repair

Double-click `install_santube.bat`. It creates/updates the Python environment, installs everything, updates ffmpeg, and creates the Desktop, Start Menu and start-with-Windows shortcuts.

Downloads from the page go to `C:\Users\admin\Downloads`.

## Never commit

`cookies*.txt` (your YouTube sign-in), `ffmpeg.exe`/`ffprobe.exe` (too big for GitHub; downloaded automatically) and `venv/`. They are in `.gitignore`.
