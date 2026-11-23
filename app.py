import os
import secrets
import threading
import logging
from flask import Flask, render_template, request, jsonify
import yt_dlp
import subprocess

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('santube.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

DOWNLOAD_FOLDER = r'C:\Users\admin\Downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# In-memory storage for download progress
# Structure: { 'download_id': { 'status': 'downloading'|'finished'|'error', 'progress': 0, 'eta': ..., 'filename': ... } }
download_progress = {}

# --- HEARTBEAT ---
# SanTube now keeps running quietly in the background so downloads (yours and
# Claude's) never stop when a browser tab is closed or put to sleep. The page
# still pings, which is harmless.
import time
import santube_core as core

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    return jsonify({'status': 'alive'})

# Update yt-dlp and ffmpeg in the background at start-up (at most daily / weekly).
threading.Thread(target=lambda: logger.info(f"Auto-update: {core.update_all(log=logger.info)}"), daemon=True).start()


def get_video_info(url):
    ydl_opts = {**core.base_opts(), 'noplaylist': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            return None

import re

# ...

def progress_hook(d, download_id):
    if d['status'] == 'downloading':
        # Remove ANSI color codes for cleaner parsing
        clean_percent = re.sub(r'\x1b\[[0-9;]*m', '', d.get('_percent_str', '0%'))
        clean_speed = re.sub(r'\x1b\[[0-9;]*m', '', d.get('_speed_str', 'N/A'))
        clean_eta = re.sub(r'\x1b\[[0-9;]*m', '', d.get('_eta_str', 'N/A'))
        
        try:
            p = clean_percent.replace('%','')
            progress = float(p)
        except:
            progress = 0
            
        download_progress[download_id]['progress'] = progress
        download_progress[download_id]['status'] = 'downloading'
        download_progress[download_id]['speed'] = clean_speed.strip()
        download_progress[download_id]['eta'] = clean_eta.strip()
        
    elif d['status'] == 'finished':
        # This is yt-dlp's finished, meaning download done. Now conversion starts.
        download_progress[download_id]['progress'] = 100
        download_progress[download_id]['status'] = 'processing'
        download_progress[download_id]['filename'] = d.get('filename', 'Unknown')

def download_video_thread(url, kind, quality, start, end, download_id):
    download_progress[download_id] = {'status': 'starting', 'progress': 0}
    try:
        path = core.download(url, kind=kind, quality=quality, start=start, end=end,
                             out_dir=DOWNLOAD_FOLDER, progress=lambda d: progress_hook(d, download_id),
                             log=logger.info, auto_update=False)
        download_progress[download_id]['status'] = 'finished'
        if path:
            download_progress[download_id]['filename'] = path
    except Exception as e:
        logger.error(f"Download failed for {url}: {str(e)}")
        download_progress[download_id]['status'] = 'error'
        download_progress[download_id]['error'] = str(e)

@app.route('/api/search', methods=['POST'])
def api_search():
    data = request.json
    query = data.get('query')
    if not query:
        return jsonify({'error': 'No query provided'}), 400

    # formatting search query for yt-dlp "ytsearchN:query"
    # extract_flat: True is faster but sometimes minimal.
    ydl_opts = {'quiet': True, 'extract_flat': True, **{k: v for k, v in core.base_opts().items() if k in ('js_runtimes', 'remote_components', 'ffmpeg_location')}} 
    
    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Fetch 12 results
            search_query = f"ytsearch12:{query}"
            info = ydl.extract_info(search_query, download=False)
            if 'entries' in info:
                for entry in info['entries']:
                    # Ensure we have a valid ID or URL
                    if not entry.get('id') and not entry.get('url'):
                        continue
                        
                    # Fix thumbnails if missing
                    if not entry.get('thumbnail'):
                        entry['thumbnail'] = f"https://i.ytimg.com/vi/{entry['id']}/hqdefault.jpg"
                    
                    results.append(entry)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify(results)

@app.route('/api/show_folder', methods=['POST'])
def show_folder():
    data = request.json
    filename = data.get('filename')
    if not filename:
        return jsonify({'error': 'No filename provided'}), 400
        
    try:
        path = os.path.join(DOWNLOAD_FOLDER, filename)
        path = os.path.normpath(path)
        
        if not os.path.exists(path):
            return jsonify({'error': 'File not found'}), 404
            
        # Use subprocess run with shell=True to ensure arguments like /select are parsed correctly by Explorer
        # Quote the path to handle spaces
        cmd = f'explorer /select,"{path}"'
        subprocess.run(cmd, shell=True)
        return jsonify({'status': 'opened'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/open_downloads_folder', methods=['POST'])
def open_downloads_folder():
    try:
        path = os.path.normpath(DOWNLOAD_FOLDER)
        if not os.path.exists(path):
            return jsonify({'error': 'Folder not found'}), 404
            
        # os.startfile is best for opening folders on Windows
        os.startfile(path)
        return jsonify({'status': 'opened'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/info', methods=['POST'])
def api_info():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    info = get_video_info(url)
    if not info:
        return jsonify({'error': 'Could not fetch video info'}), 400
    
    # Process formats to easier frontend consumption
    formats = []
    
    # Group by resolution ("720p", "1080p") and find the BEST codec (avc1 > vp9 > others)
    # Map: resolution -> list of formats
    res_map = {}
    
    for f in info.get('formats', []):
        if f.get('vcodec') != 'none' and f.get('height'): # Premiere fix: we already transcode to mp4 later, no need to block webm here
            h = f['height']
            resid = f"{h}p"
            if resid not in res_map:
                res_map[resid] = []
            res_map[resid].append(f)
    
    # For each resolution, pick the best format
    for resid, f_list in res_map.items():
        # Priority: vcodec starts with avc1 > mp4 container > others
        # We sort f_list by preference
        def format_score(fmt):
            score = 0
            if fmt.get('vcodec', '').startswith('avc1'): score += 10
            if fmt.get('ext') == 'mp4': score += 5
            return score
        
        f_list.sort(key=format_score, reverse=True)
        best_f = f_list[0]
        
        formats.append({
            'format_id': best_f['format_id'],
            'resolution': resid,
            'height': int(resid.replace('p', '')),
            'ext': 'MP4', # We force output to MP4 anyway
            'filesize': best_f.get('filesize_approx', 0)
        })
    
    # Sort formats by resolution (height)
    formats.sort(key=lambda x: int(x['resolution'].replace('p','')), reverse=True)

    # Attempt to find channel thumbnail if top-level is missing
    channel_thumb = info.get('channel_thumbnail')
    if not channel_thumb:
        # Check in thumbnails list for typical avatar dimensions or keys (yt-dlp sometimes label them)
        # But often they are just mixed in. We can't easily distinguish without dimensions.
        # Alternatively, use uploader_id to construct valid potential URLs?
        # For now, we accept it might be None.
        pass
    
    # 2024 Fix: yt-dlp might behave better with specific user-agent or cookies
    # We proceed with what we have.

    # Fetch "Up Next" recommendations
    # Since yt-dlp single video extraction often skips related videos, 
    # we'll fetch the Trending feed as a high-quality fallback for "Up Next"
    # to ensure the UI is always populated.
    # ---------------------------------------------------------
    # "UP NEXT" Logic - Guaranteed Content Strategy
    # ---------------------------------------------------------
    rec_results = []
    
    # helper to fetch
    def fetch_recs(query, limit=10):
        try:
            r_opts = {
                'quiet': True, 
                'extract_flat': True, 
                'ignoreerrors': True,
                'playlist_items': f'1:{limit}',
                **{k: v for k, v in core.base_opts().items() if k in ('js_runtimes', 'remote_components', 'ffmpeg_location')},
            }
            with yt_dlp.YoutubeDL(r_opts) as ydl_r:
                r_res = ydl_r.extract_info(f"ytsearch{limit}:{query}", download=False)
                return r_res.get('entries', [])
        except:
            return []

    try:
        # Strategy 1: Search by Title (Most Relevant)
        safe_title = "".join([c for c in info.get('title', 'trending') if c.isalnum() or c.isspace()])
        entries = fetch_recs(safe_title, 15)
        
        # Strategy 2: If Title failed/low results, Search "Trending Music" (Fallback)
        if not entries or len(entries) < 3:
            print("Low recs from title, fetching trending...")
            entries = fetch_recs("trending perhap popular music", 15)
            
        # Process Results
        for r in entries:
             # Skip self
             if r and r.get('id') != info.get('id'):
                  # Ensure thumbnail
                  if not r.get('thumbnail'):
                        if r.get('thumbnails') and len(r['thumbnails']) > 0:
                                r['thumbnail'] = r['thumbnails'][0].get('url')
                        else:
                                r['thumbnail'] = f"https://i.ytimg.com/vi/{r['id']}/hqdefault.jpg"
                  rec_results.append(r)
                  
    except Exception as e:
        print(f"Critical Recs Error: {e}")

    # Strategy 3: Hardcoded Last Resort (If everything fails, e.g. IP ban)
    # Prevents "Loading..." forever or empty UI
    if not rec_results:
        rec_results = [
            {'id': 'kJQP7kiw5Fk', 'title': 'Luis Fonsi - Despacito', 'uploader': 'LuisFonsiVEVO', 'duration': 282, 'thumbnail': 'https://i.ytimg.com/vi/kJQP7kiw5Fk/hqdefault.jpg'},
            {'id': 'JGwWNGJdvx8', 'title': 'Ed Sheeran - Shape of You', 'uploader': 'Ed Sheeran', 'duration': 263, 'thumbnail': 'https://i.ytimg.com/vi/JGwWNGJdvx8/hqdefault.jpg'}
        ]

    # Channel Thumbnail Fallback
    # If channel_thumbnail is None, check the thumbnails list of the MAIN video info for 'avatar'
    if not info.get('channel_thumbnail'):
        # Sometimes keys like 'avatar_uncropped' exist in thumbnails list
        # This is a best-effort check
        pass

    video_data = {
        'title': info.get('title'),
        'thumbnail': info.get('thumbnail'),
        'duration': info.get('duration'),
        'uploader': info.get('uploader'),
        'channel_url': info.get('channel_url'),
        'channel_thumbnail': info.get('channel_thumbnail'), # URL to avatar
        'channel_follower_count': info.get('channel_follower_count'), # Integer
        'view_count': info.get('view_count'),
        'upload_date': info.get('upload_date'),
        'description': info.get('description'),
        'formats': formats,
        'recommendations': rec_results
    }
    return jsonify(video_data)

@app.route('/api/feed', methods=['GET'])
def api_feed():
    # Check for cookies file (User preference: cookiesforSantube.txt)
    # We check the specific Santube file first
    cookies_file = 'cookiesforSantube.txt'
    cookies_path = os.path.join(os.getcwd(), cookies_file)
    
    # Fallback to standard cookies.txt if not found (optional, but good UX)
    if not os.path.exists(cookies_path):
         cookies_path = os.path.join(os.getcwd(), 'cookies.txt')
    
    # if not has_cookies:
    #     return jsonify({'status': 'guest', 'message': 'No cookies found'})
    # JUST PROCEED to generic trending if no cookies


    # Pagination: Get page number from query params, default to 1
    try:
        page = int(request.args.get('page', 1))
    except:
        page = 1
    
    videos_per_page = 20
    start_index = (page - 1) * videos_per_page + 1
    end_index = start_index + videos_per_page - 1
    playlist_range = f"{start_index}:{end_index}"

    # If cookies exist, fetch homepage
    ydl_opts = {
        'quiet': True, 
        'extract_flat': 'in_playlist', # Just get metadata, don't download
        'cookiefile': cookies_path,
        'playlist_items': playlist_range, # Dynamic range
        'ignoreerrors': True,
        **{k: v for k, v in core.base_opts().items() if k in ('js_runtimes', 'remote_components', 'ffmpeg_location')},
    }
    
    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 1. Try Homepage
            # Note: For homepage, indices might shift between requests, but it's the best we can do without session tokens
            try:
                info = ydl.extract_info("https://www.youtube.com/", download=False)
            except:
                info = {}

            if 'entries' not in info or not info['entries']:
                # 2. Fallback: Try ytsearch for trending
                if page == 1:
                     print("Homepage empty, trying Trending Search...")
                     info = ydl.extract_info("ytsearch20:trending worldwide", download=False)
            
            if 'entries' in info:
                for entry in info['entries']:
                    if not entry: continue
                    if not entry.get('id') and not entry.get('url'): continue
                    
                    # Fix thumbnails
                    if not entry.get('thumbnail'):
                         entry['thumbnail'] = f"https://i.ytimg.com/vi/{entry['id']}/hqdefault.jpg"
                    
                    # Use channel thumbnail if available, or placeholder
                    if not entry.get('channel_thumbnail'):
                         # Try to construct or leave empty
                         pass

                    results.append(entry)
                    
        return jsonify({'status': 'authenticated', 'videos': results, 'page': page})
    except Exception as e:
        print(f"Feed Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.json or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    kind = (data.get('kind') or ('mp3' if data.get('is_audio') else 'mp4')).lower()
    quality = data.get('quality')
    if not quality:  # older pages send a format_id + height
        h = int(data.get('height') or 0)
        quality = '4k' if h >= 1800 else '2k' if h >= 1300 else '1080p' if h >= 800 else '720p' if h >= 500 else 'best'
    download_id = secrets.token_hex(8)
    threading.Thread(target=download_video_thread,
                     args=(url, kind, quality, data.get('start'), data.get('end'), download_id),
                     daemon=True).start()
    return jsonify({'download_id': download_id})

@app.route('/api/progress/<download_id>', methods=['GET'])
def api_progress(download_id):
    prog = download_progress.get(download_id)
    if not prog:
        return jsonify({'error': 'Download ID not found'}), 404
    return jsonify(prog)

@app.route('/api/check_update', methods=['GET'])
def check_update():
    try:
        # Check if it's a git repo
        if not os.path.exists('.git'):
            return jsonify({'update_available': False, 'message': 'Not a git repository'})

        # Fetch latest
        subprocess.run(['git', 'remote', 'update'], check=True, capture_output=True)
        
        # Check status
        result = subprocess.run(['git', 'status', '-uno'], check=True, capture_output=True, text=True)
        
        if 'Your branch is behind' in result.stdout:
            return jsonify({'update_available': True, 'message': 'New version available'})
        else:
            return jsonify({'update_available': False, 'message': 'You are up to date'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/update', methods=['POST'])
def perform_update():
    try:
        # 1. Git Pull
        pull_res = subprocess.run(['git', 'pull'], check=True, capture_output=True, text=True)
        
        # 2. Pip Install (Upgrade dependencies)
        # We use sys.executable to ensure we use the same python interpreter
        import sys
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', '-r', 'requirements.txt'], check=True)
        core.update_all(force=True)
        
        return jsonify({'success': True, 'message': 'Update successful. Restarting server...'})
    except subprocess.CalledProcessError as e:
        return jsonify({'success': False, 'message': f"Update failed: {e.stderr if hasattr(e, 'stderr') else str(e)}"}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    # Only this PC can open SanTube (no access from other devices on the network)
    # debug=False prevents the reloader from spawning a child process which might show a window
    app.run(debug=False, host='127.0.0.1', port=5000, threaded=True)
