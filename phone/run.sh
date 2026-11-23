#!/data/data/com.termux/files/usr/bin/bash
# SanTube on the phone: fetch requested clips one at a time and upload each to Google Drive.
# Requests live in Drive: "The 181st Degree/Production Dependencies/requests.txt", one per line:
#   id | reel folder | youtube link | start | end | mp4/mp3/wav | quality
#   e.g.  mnj-01 | 031-mera-naam-joker | https://youtu.be/xxxx | 1:42:10 | 1:42:25 | mp4 | 1080p
# Results go to "The 181st Degree/Production Dependencies/done.txt":  id | ok/fail | file or error | time
set -u
B="$HOME/181"; R="gdrive:The 181st Degree/Production Dependencies"; PAD=15; MIN_FREE_MB=300
mkdir -p "$B/tmp"; cd "$B" || exit 1
exec 9>"$B/.lock"; flock -n 9 || exit 0          # never run twice at once
log(){ echo "$(date '+%F %T') $*" >> "$B/run.log"; }

# keep yt-dlp current (YouTube changes often), at most once a day
if [ ! -f .updated ] || [ "$(find .updated -mtime +0 2>/dev/null)" ]; then
  pip install -q -U "yt-dlp[default]" >/dev/null 2>&1 && touch .updated
fi

# Requests (data only): the list Claude keeps on GitHub, plus Drive's requests.txt for San's own.
RAW="https://raw.githubusercontent.com/theawardlosingfilmmaker/Youtube-Downloader/main/phone/requests.txt"
: > req.txt
curl -fsSL "$RAW?$(date +%s)" >> req.txt 2>/dev/null; echo >> req.txt
rclone cat "$R/requests.txt" >> req.txt 2>/dev/null
rclone copyto "$R/done.txt" done.txt 2>/dev/null || : > done.txt
secs(){ python3 -c "import sys;p=[float(x) for x in sys.argv[1].split(':')];s=0
for x in p: s=s*60+x
print(s)" "$1"; }
hms(){ python3 -c "import sys;s=max(0.0,float(sys.argv[1]));print('%d:%02d:%06.3f'%(s//3600,s%3600//60,s%60))" "$1"; }
changed=0
while IFS='|' read -r id reel url st en kind q || [ -n "${id:-}" ]; do
  id=$(echo "${id:-}" | xargs); [ -z "$id" ] || [ "${id:0:1}" = "#" ] && continue
  grep -q "^$id | ok |" done.txt && continue                       # already fetched
  [ "$(grep -c "^$id | fail |" done.txt)" -ge 3 ] && continue      # gave up after 3 tries
  reel=$(echo "$reel"|xargs); url=$(echo "$url"|xargs); st=$(echo "$st"|xargs); en=$(echo "$en"|xargs)
  kind=$(echo "${kind:-mp4}"|xargs); q=$(echo "${q:-1080p}"|xargs); [ -z "$kind" ] && kind=mp4
  free=$(python3 -c "import shutil,os;print(shutil.disk_usage(os.path.expanduser('~')).free//1048576)")
  if [ "${free:-0}" -lt $MIN_FREE_MB ]; then log "only ${free} MB free, waiting"; break; fi
  rm -f tmp/*
  args=(--no-playlist --no-progress --js-runtimes node -o "tmp/${id}.%(ext)s")   # YouTube needs a JS runtime; Termux has Node
  if [ -n "$st$en" ]; then
    s=$(secs "${st:-0}"); s=$(python3 -c "print(max(0,$s-$PAD))")
    if [ -n "$en" ]; then e=$(python3 -c "print($(secs "$en")+$PAD)"); sec="*$(hms $s)-$(hms $e)"; else sec="*$(hms $s)-inf"; fi
    args+=(--download-sections "$sec" --force-keyframes-at-cuts)
  fi
  case "$kind" in
    mp3) args+=(-f bestaudio/best -x --audio-format mp3 --audio-quality 0);;
    wav) args+=(-f bestaudio/best -x --audio-format wav);;
    *)  h=${q%p}; case "$q" in 4k) h=2160;; 2k) h=1440;; fullhd) h=1080;; esac; [ "$h" -eq "$h" ] 2>/dev/null || h=1080
        args+=(-f "bv*[height<=$h][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=$h]+ba/b[height<=$h]/b" --merge-output-format mp4);;
  esac
  if yt-dlp "${args[@]}" "$url" >> run.log 2>&1; then
    f=$(ls tmp/ | head -1)
    if [ -n "$f" ] && rclone move "tmp/$f" "$R/$reel/" 2>>run.log; then
      echo "$id | ok | $reel/$f | $(date '+%F %T')" >> done.txt; log "ok $id $f"
    else echo "$id | fail | upload failed | $(date '+%F %T')" >> done.txt; fi
  else
    err=$(grep -i "error" run.log | tail -1 | cut -c1-150 | tr '|' '/')
    echo "$id | fail | ${err:-download failed} | $(date '+%F %T')" >> done.txt; log "fail $id"
  fi
  rm -f tmp/*; changed=1
done < req.txt
[ $changed = 1 ] && rclone copyto done.txt "$R/done.txt"
tail -n 300 run.log > run.tmp && mv run.tmp run.log
