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

def get_video_info(url):
    ydl_opts = {'quiet': True}
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

def download_video_thread(url, format_id, download_id, is_audio_only):
    # If audio only, we want best audio and convert to mp3
    if is_audio_only:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'progress_hooks': [lambda d: progress_hook(d, download_id)],
            'noplaylist': True,
        }
    else:
        # Premiere Pro prefers H.264 (avc1) video and AAC audio in MP4
        # We try to use the selected format_id (which we now select carefully to be avc1 if possible)
        # We also force audio conversion to AAC to avoid Opus issues
        
        # If format_id is 'best', we try to get best avc1
        fmt = format_id if format_id != 'best' else "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[ext=mp4]/best"
        
        # If the user selected a specific format, we still need to merge audio. 
        # Usually format_id from UI is just video stream. We need to add audio.
        if format_id != 'best' and '+' not in format_id:
            fmt = f"{format_id}+bestaudio[acodec^=mp4a]/bestaudio/best"

        ydl_opts = {
            'format': fmt,
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            'progress_hooks': [lambda d: progress_hook(d, download_id)],
            'noplaylist': True,
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            # CRITICAL FOR PREMIERE PRO:
            # YouTube 4K is usually VP9/AV1 which Premiere dislikes.
            # We MUST transcode to H.264 (libx264) and AAC.
            # This is CPU intensive but ensures compatibility.
            'postprocessor_args': {
                'ffmpeg': [
                    '-c:v', 'libx264', 
                    '-preset', 'fast', 
                    '-crf', '23',
                    '-c:a', 'aac', 
                    '-b:a', '192k',
                    '-movflags', '+faststart'
                ]
            },
        }

    download_progress[download_id] = {'status': 'starting', 'progress': 0}
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        # Only set finished AFTER download() returns (post-processing done)
        download_progress[download_id]['status'] = 'finished'
    except Exception as e:
        import logging
        logging.error(f"Download failed for {url}: {str(e)}")
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
    ydl_opts = {'quiet': True, 'extract_flat': True} 
    
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
        if f.get('vcodec') != 'none' and f.get('height') and f.get('ext') != 'webm': # Avoid webm for premiere if possible, though we merge to mp4
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
            'ext': 'MP4', # We force output to MP4 anyway
            'filesize': best_f.get('filesize_approx', 0)
        })
    
    # Sort formats by resolution (height)
    formats.sort(key=lambda x: int(x['resolution'].replace('p','')), reverse=True)

    # Fetch "Up Next" recommendations
    # Since yt-dlp single video extraction often skips related videos, 
    # we'll fetch the Trending feed as a high-quality fallback for "Up Next"
    # to ensure the UI is always populated.
    rec_results = []
    try:
        # Check if we have cookies for better recs, else generic
        cookies_path = os.path.join(os.getcwd(), 'cookiesforSantube.txt')
        if not os.path.exists(cookies_path): cookies_path = os.path.join(os.getcwd(), 'cookies.txt')
        
        rec_opts = {
            'quiet': True, 
            'extract_flat': 'in_playlist',
            'playlist_items': '1:10',
            'ignoreerrors': True
        }
        if os.path.exists(cookies_path): rec_opts['cookiefile'] = cookies_path

        with yt_dlp.YoutubeDL(rec_opts) as ydl_rec:
            # Try to search for related based on title? Or just trending?
            # Trending is safer and faster than searching
            res = ydl_rec.extract_info("https://www.youtube.com/feed/trending", download=False)
            if 'entries' in res:
                for r in res['entries']:
                     if r and r.get('title'):
                          if not r.get('thumbnail'): r['thumbnail'] = f"https://i.ytimg.com/vi/{r['id']}/hqdefault.jpg"
                          rec_results.append(r)
    except:
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
    
    if not has_cookies:
        return jsonify({'status': 'guest', 'message': 'No cookies found'})

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
        'ignoreerrors': True
    }
    
    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 1. Try Homepage
            # Note: For homepage, indices might shift between requests, but it's the best we can do without session tokens
            info = ydl.extract_info("https://www.youtube.com/", download=False)
            
            if 'entries' not in info or not info['entries']:
                # 2. Fallback: Try Trending (Only if page 1, or try scrolling trending too)
                # Trending is usually consistent enough for indexing
                if page == 1:
                     print("Homepage empty, trying Trending...")
                     info = ydl.extract_info("https://www.youtube.com/feed/trending", download=False)
            
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
    data = request.json
    url = data.get('url')
    format_id = data.get('format_id', 'best')
    is_audio = data.get('is_audio', False)
    
    download_id = secrets.token_hex(8)
    
    thread = threading.Thread(target=download_video_thread, args=(url, format_id, download_id, is_audio))
    thread.start()
    
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
        
        return jsonify({'success': True, 'message': 'Update successful. Restarting server...'})
    except subprocess.CalledProcessError as e:
        return jsonify({'success': False, 'message': f"Update failed: {e.stderr if hasattr(e, 'stderr') else str(e)}"}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
