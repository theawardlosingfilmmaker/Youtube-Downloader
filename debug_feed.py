import yt_dlp
import os
import json

cookies_file = 'cookiesforSantube.txt'
cookies_path = os.path.join(os.getcwd(), cookies_file)

print(f"Testing cookies from: {cookies_path}")
print(f"Exists: {os.path.exists(cookies_path)}")

ydl_opts = {
    'quiet': False,
    'extract_flat': 'in_playlist',
    'cookiefile': cookies_path,
    # 'playlist_items': '1:20', # Commented out to test
    'verbose': True
}

try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print("\n--- TEST 1: Homepage (no limit) ---")
        info = ydl.extract_info("https://www.youtube.com/", download=False)
        if 'entries' in info:
            print(f"Found {len(info['entries'])} entries.")
        else:
             print("No entries.")

        print("\n--- TEST 2: Subscriptions Feed ---")
        info = ydl.extract_info("https://www.youtube.com/feed/subscriptions", download=False)
        if 'entries' in info:
            print(f"Found {len(info['entries'])} entries.")
        else:
             print("No entries.")
except Exception as e:
    print(f"Error: {e}")
