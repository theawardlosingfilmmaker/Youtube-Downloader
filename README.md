# San's YouTube Intruder

A premium, locally hosted YouTube Downloader built with Flask and Vanilla JS. Designed to mimic the authentic YouTube UI while offering powerful download capabilities compatible with Adobe Premiere Pro.

## Features

-   **Authentic UI**: A pixel-perfect recreation of the YouTube interface (Dark Mode).
-   **Search & Watch**: Built-in search and video player to preview content before downloading.
-   **Download Manager**: Chrome-style global download manager in the header.
-   **Format Control**: 
    -   **4K / 2K / 1080p** Video Downloads (H.264 MP4).
    -   **MP3** Audio Extraction.
    -   **Smart Detection**: Only shows quality options actually available for the video.
-   **Premiere Pro Ready**: Videos are automatically transcoded to compatible codecs (AAC Audio, H.264 Video) to prevent editing software errors.
-   **One-Click Folder Access**: Open the file location instantly from the download manager.

## Installation

1.  **Prerequisites**:
    -   Python 3.8+
    -   [FFmpeg](https://ffmpeg.org/download.html) (Ensure it's added to your System PATH).

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

### Running the App
Double-click `start.bat` or run:
```bash
python app.py
```
The application will open in your default browser at `http://127.0.0.1:5000`.

### Downloading Videos
1.  **Search** for a video using the top search bar OR paste a YouTube URL.
2.  Open the video to view the Watch Page.
3.  Click the **Download** button (next to the channel name).
4.  Select your desired quality from the **Quick Actions** modal (e.g., 4K, 1080p, Audio).
5.  Track progress in the top-right **Downloads Dropdown**.
6.  Once finished, click the **Folder Icon** in the dropdown to find your file.

## Configuration
-   Downloads are saved to: `C:\Users\admin\Downloads` (Default)
-   To change this, edit the `DOWNLOAD_FOLDER` variable in `app.py`.

## Troubleshooting
-   **"File not found"**: Ensure the video finished processing (Converting...) before trying to open it.
-   **Download Fails**: Check your internet connection or if the video is region-locked.
