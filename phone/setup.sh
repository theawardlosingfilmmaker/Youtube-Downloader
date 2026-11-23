#!/data/data/com.termux/files/usr/bin/bash
# One-time setup of SanTube on the phone. Run in Termux with:
#   bash <(curl -fsSL https://raw.githubusercontent.com/theawardlosingfilmmaker/Youtube-Downloader/main/phone/setup.sh)
set -e
echo "== Installing tools (a few minutes) =="
pkg update -y >/dev/null
pkg install -y python ffmpeg rclone nodejs cronie termux-services util-linux >/dev/null
pip install -q -U "yt-dlp[default]"
mkdir -p "$HOME/181"
curl -fsSL https://raw.githubusercontent.com/theawardlosingfilmmaker/Youtube-Downloader/main/phone/run.sh -o "$HOME/181/run.sh"
chmod +x "$HOME/181/run.sh"

if ! rclone listremotes | grep -q '^gdrive:'; then
  echo
  echo "== Google Drive sign-in =="
  echo "A link will appear. Open it in your phone's browser, choose your account and press Allow."
  echo "This gives access ONLY to files this tool creates (the 'The 181st Degree / Production Dependencies' folder). Your password is never stored."
  rclone config create gdrive drive scope=drive.file config_is_local=true
fi
rclone mkdir "gdrive:The 181st Degree/Production Dependencies"
rclone lsf "gdrive:The 181st Degree/Production Dependencies/requests.txt" >/dev/null 2>&1 || printf '# id | reel folder | youtube link | start | end | mp4/mp3/wav | quality\n' | rclone rcat "gdrive:The 181st Degree/Production Dependencies/requests.txt"
rclone lsf "gdrive:The 181st Degree/Production Dependencies/done.txt" >/dev/null 2>&1 || printf '' | rclone rcat "gdrive:The 181st Degree/Production Dependencies/done.txt"

echo "== Scheduling: checks for new clips every hour =="
( crontab -l 2>/dev/null | grep -v '181/run.sh'; echo "7 * * * * $HOME/181/run.sh" ) | crontab -
sv-enable crond 2>/dev/null || true
termux-wake-lock 2>/dev/null || true
echo
echo "Done. Last step: Android Settings > Apps > Termux > Battery > Unrestricted (so it keeps running)."
echo "To fetch right now: ~/181/run.sh     To see what happened: tail ~/181/run.log"
