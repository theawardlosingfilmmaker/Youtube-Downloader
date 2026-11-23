let currentVideoInfo = null;
let currentSearchResults = [];
let activeDownloads = new Set();
let downloadInterval = null;
let currentPage = 1;
let isLoadingMore = false;
let isFeedExhausted = false;
let isSidebarCollapsed = false;

// ============================
// SIDEBAR TOGGLE
// ============================
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('collapsed');
    isSidebarCollapsed = !isSidebarCollapsed;
}

// Initial Load
window.onload = function () {
    loadHomeFeed();
    checkForUpdates(); // Auto-update check
    startGlobalPolling();

    // Infinite Scroll Listener
    const mainContent = document.querySelector('.main-content');
    if (mainContent) {
        mainContent.addEventListener('scroll', () => {
            if (isLoadingMore || isFeedExhausted) return;

            // Check if we are near bottom (within 200px)
            if (mainContent.scrollTop + mainContent.clientHeight >= mainContent.scrollHeight - 200) {
                // Only trigger if we are in Grid mode (not watch mode)
                if (!document.getElementById('resultsGrid').classList.contains('hidden')) {
                    loadNextPage();
                }
            }
        });
    }
};

async function loadNextPage() {
    isLoadingMore = true;
    currentPage++;
    console.log("Loading page " + currentPage);

    // Show a small spinner or indicator? 
    // For now, just simplistic

    try {
        const res = await fetch(`/api/feed?page=${currentPage}`);
        const data = await res.json();

        if (data.status === 'authenticated' && data.videos && data.videos.length > 0) {
            // Append videos
            currentSearchResults = currentSearchResults.concat(data.videos);
            renderGrid(data.videos, true); // true = append
        } else {
            console.log("Page empty. Looping back to random feed for endless scroll effect.");
            // Fallback: Just fetch page 1 again or trending to simulate endless
            // To make it look "endless", we can shuffle or just append.
            const retryRes = await fetch(`/api/feed?page=1`);
            const retryData = await retryRes.json();
            if (retryData.videos && retryData.videos.length > 0) {
                // Shuffle slightly to fake variety?
                let shuffled = retryData.videos.sort(() => 0.5 - Math.random());
                currentSearchResults = currentSearchResults.concat(shuffled);
                renderGrid(shuffled, true);
            } else {
                isFeedExhausted = true;
            }
        }
    } catch (e) {
        console.error(e);
        // Don't retry immediately
    } finally {
        isLoadingMore = false;
    }
}

async function loadHomeFeed() {
    currentPage = 1;
    isFeedExhausted = false;
    showLoading(true);
    // Reset UI
    document.getElementById('watchSection').classList.add('hidden');
    document.getElementById('resultsGrid').classList.remove('hidden');
    document.querySelector('.categories').classList.remove('hidden');

    try {
        const res = await fetch('/api/feed?page=1');
        const data = await res.json();

        if (data.status === 'guest') {
            // No cookies -> Show generic trending
            performSearch('trending youtube 4k');
            // Optionally show a "Connect Account" banner in grid?
        } else if (data.status === 'authenticated') {
            // Cookies found -> Show personal feed
            if (!data.videos || data.videos.length === 0) {
                console.warn("Empty feed, fallback.");
                throw new Error("Empty feed");
            }
            currentSearchResults = data.videos;
            renderGrid(data.videos, false);
        } else if (data.status === 'error') {
            throw new Error("Server error: " + data.message);
        }
    } catch (e) {
        console.error("Feed load failed:", e);
        performSearch('trending youtube 4k'); // Fallback to generic search
    } finally {
        showLoading(false);
    }
}

function openConnectModal() {
    document.getElementById('connectModalOverlay').classList.remove('hidden');
}
function closeConnectModal(e) {
    if (e.target.id === 'connectModalOverlay') document.getElementById('connectModalOverlay').classList.add('hidden');
}
function closeConnectModalForce() {
    document.getElementById('connectModalOverlay').classList.add('hidden');
}

document.getElementById('searchInput').addEventListener('keypress', function (e) {
    if (e.key === 'Enter') handleSearch();
});

// ============================
// SEARCH & NAV
// ============================
async function handleSearch() {
    const query = document.getElementById('searchInput').value.trim();
    if (!query) return;
    if (isValidUrl(query)) fetchInfoAndShow(query);
    else performSearch(query);
}

function isValidUrl(string) {
    try { new URL(string); return true; } catch (_) { return false; }
}

async function performSearch(query) {
    showLoading(true);
    document.getElementById('watchSection').classList.add('hidden');
    document.getElementById('resultsGrid').classList.remove('hidden');
    document.querySelector('.categories').classList.remove('hidden');

    try {
        const res = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query })
        });
        const results = await res.json();
        currentSearchResults = results;
        renderGrid(results);
    } catch (e) {
        console.error("Feed load failed", e);
    } finally {
        showLoading(false);
    }
}

function renderGrid(videos, append = false) {
    const grid = document.getElementById('resultsGrid');
    if (!append) grid.innerHTML = '';
    // If appending, remove placeholder if exists (though usually cleared)
    if (append) {
        const ph = grid.querySelector('.placeholder-msg');
        if (ph) ph.remove();
    } else {
        // Should we add a placeholder if empty? handled dynamically
    }

    videos.forEach(v => {
        if (!v.title) return;
        const card = document.createElement('div');
        card.className = 'video-card';
        let targetUrl = v.url || `https://www.youtube.com/watch?v=${v.id}`;
        card.onclick = () => fetchInfoAndShow(targetUrl);

        const thumb = v.thumbnail || `https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`;
        // Use channel thumbnail if available (from feed) or letter
        let avatarContent = v.uploader ? v.uploader[0].toUpperCase() : 'Y';
        // Note: feed usually doesn't have channel_thumbnail, but if we updated app.py to try, we could use it
        // For now, letter is safer for performance in feed

        card.innerHTML = `
            <div class="thumb-wrapper">
                <img src="${thumb}" alt="thumb" loading="lazy">
                <div class="duration-badge">${formatDuration(v.duration)}</div>
            </div>
            <div class="card-info">
                <div class="card-avatar">${avatarContent}</div>
                <div class="card-text">
                    <h3>${v.title}</h3>
                    <p>${v.uploader || 'Unknown Channel'}</p>
                    <p>${v.view_count ? formatViews(v.view_count) : 'Views hidden'} • ${v.upload_date ? timeAgo(v.upload_date) : 'Recently'}</p>
                </div>
            </div>
        `;
        grid.appendChild(card);
    });
}

async function fetchInfoAndShow(url) {
    showLoading(true);
    try {
        const res = await fetch('/api/info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        loadWatchPage(data, url);
    } catch (e) {
        alert("Could not load video: " + e.message);
    } finally {
        showLoading(false);
    }
}

function loadWatchPage(data, url) {
    document.getElementById('resultsGrid').classList.add('hidden');
    document.querySelector('.categories').classList.add('hidden');
    document.getElementById('watchSection').classList.remove('hidden');

    document.querySelector('.main-content').scrollTop = 0;

    currentVideoInfo = data;
    currentVideoInfo.url = url;

    // Save to watch history
    addToHistory(data, url);

    // Populate Info
    document.getElementById('videoTitle').textContent = data.title;
    document.getElementById('ownerName').textContent = data.uploader || 'Unknown';

    // Handle Avatar
    const avatarContainer = document.getElementById('ownerAvatar');
    avatarContainer.innerHTML = ''; // Clear previous
    if (data.channel_thumbnail) {
        const img = document.createElement('img');
        img.src = data.channel_thumbnail;
        img.style.width = '100%';
        img.style.height = '100%';
        img.style.objectFit = 'cover';
        img.style.borderRadius = '50%';
        avatarContainer.appendChild(img);
        avatarContainer.style.background = 'transparent';
    } else {
        avatarContainer.textContent = (data.uploader || 'U')[0].toUpperCase();
        avatarContainer.style.background = '#7e57c2'; // Reset color
    }

    document.getElementById('ownerSubs').textContent = '1.2M subscribers'; // Fake for now as getting subs requires more API

    document.getElementById('descViews').textContent = data.view_count ? formatViews(data.view_count) + ' views' : 'Views hidden';
    document.getElementById('descDate').textContent = data.upload_date ? timeAgo(data.upload_date) : '';
    document.getElementById('descText').textContent = data.description || '';

    // If channel avatar url is available (sometimes yt-dlp provides thumbnail, sometimes not channel avatar)
    // We can try to use a generic one or extracted one if available

    let videoId = '';
    try {
        if (url.includes('v=')) videoId = url.split('v=')[1].split('&')[0];
        else if (url.includes('youtu.be/')) videoId = url.split('youtu.be/')[1];
    } catch (e) { }
    if (videoId) {
        document.getElementById('previewPlayer').src = `https://www.youtube.com/embed/${videoId}?autoplay=1`;
        // Recommendations
        const recContainer = document.getElementById('recommendations');
        console.log("Processing Recommendations:", data.recommendations);
        if (data.recommendations && data.recommendations.length > 0) {
            renderSuggestions(data.recommendations, recContainer);
        } else {
            console.warn("No recommendations found/returned from API");
            recContainer.innerHTML = '<p style="color: #aaa; padding: 10px;">No recommendations available</p>';
        }

        // Check download status in case we already downloaded this
        // We can do a quick check or just rely on the global poller
    }
}

function renderSuggestions(videos, container) {
    container.innerHTML = '<h3>Up Next</h3>';

    videos.forEach(v => {
        if (!v.title) return;
        const card = document.createElement('div');
        card.className = 'suggestion-card';
        let targetUrl = v.url || `https://www.youtube.com/watch?v=${v.id}`;
        card.onclick = () => fetchInfoAndShow(targetUrl);

        const thumb = v.thumbnail || `https://i.ytimg.com/vi/${v.id}/mqdefault.jpg`;

        card.innerHTML = `
            <div class="sugg-thumb">
                <img src="${thumb}" alt="thumb">
                <span class="sugg-duration">${formatDuration(v.duration)}</span>
            </div>
            <div class="sugg-info">
                <h4 title="${v.title}">${v.title}</h4>
                <p class="sugg-channel">${v.uploader || 'Unknown'}</p>
                <p class="sugg-meta">${v.view_count ? formatViews(v.view_count) : ''} • ${v.upload_date ? timeAgo(v.upload_date) : ''}</p>
            </div>
        `;
        container.appendChild(card);
    });
}

// ==========================================
// MODAL LOGIC (Format Selection)
// ==========================================

function openDownloadModal() {
    if (!currentVideoInfo) return;
    const modal = document.getElementById('downloadModalOverlay');
    modal.classList.remove('hidden');

    document.getElementById('quickActionsGrid').innerHTML = '';
    const formats = currentVideoInfo.formats;

    // Helper: get numeric height from format object
    const getHeight = (f) => f.height || parseInt((f.resolution || '').replace('p', '')) || 0;

    // Clip (optional): only download from Start to End, e.g. 1:42:10 to 1:42:25
    const grid = document.getElementById('quickActionsGrid');
    const clipRow = document.createElement('div');
    clipRow.className = 'clip-row';
    clipRow.style.cssText = 'grid-column:1/-1;display:flex;gap:8px;align-items:center;margin-bottom:6px;font-size:13px;color:#aaa';
    clipRow.innerHTML = `Clip <input id="clipStart" placeholder="start  0:00" style="flex:1;min-width:0;padding:7px;border-radius:8px;border:1px solid #444;background:#121212;color:#fff">
        <input id="clipEnd" placeholder="end  (blank = whole video)" style="flex:1.4;min-width:0;padding:7px;border-radius:8px;border:1px solid #444;background:#121212;color:#fff">`;
    grid.appendChild(clipRow);

    // Quick buttons: only qualities this video actually has
    const maxH = Math.max(0, ...formats.map(getHeight));
    if (maxH >= 1400) createQuickBtn('4K', 'MP4', 'mp4', '4k');
    if (maxH >= 1000) createQuickBtn('2K', 'MP4', 'mp4', '2k');
    if (maxH >= 700) createQuickBtn('Full HD', 'MP4', 'mp4', '1080p');
    createQuickBtn('720p', 'MP4', 'mp4', '720p');
    createQuickBtn('Music', 'MP3 320', 'mp3', null);
    createQuickBtn('Music', 'WAV', 'wav', null);

    // Full List
    const fullList = document.getElementById('fullFormatList');
    fullList.innerHTML = '';
    const sorted = [...formats].sort((a, b) => getHeight(b) - getHeight(a));

    sorted.forEach(f => {
        const item = document.createElement('div');
        item.className = 'list-item';
        const size = f.filesize ? (f.filesize / 1024 / 1024).toFixed(1) + 'MB' : '';
        item.innerHTML = `
            <span class="list-item-text">${f.resolution || 'Unknown'} (${f.ext.toUpperCase()})</span>
            <span class="list-item-size">${size}</span>
        `;
        item.onclick = () => triggerDownload('mp4', null, getHeight(f));
        fullList.appendChild(item);
    });
}

function createQuickBtn(label, sub, kind, quality) {
    const btn = document.createElement('button');
    btn.className = 'quick-btn';
    btn.innerHTML = `<span class="quality-tag">${label}</span><span class="format-tag">${sub}</span>`;
    btn.onclick = () => triggerDownload(kind, quality);
    document.getElementById('quickActionsGrid').appendChild(btn);
}

function closeDownloadModal(e) {
    if (e.target.id === 'downloadModalOverlay') {
        document.getElementById('downloadModalOverlay').classList.add('hidden');
    }
}
function closeDownloadModalForce() {
    document.getElementById('downloadModalOverlay').classList.add('hidden');
}

// ==========================================
// DOWNLOAD MANAGER LOGIC
// ==========================================

async function triggerDownload(kind, quality, height) {
    const start = (document.getElementById('clipStart') || {}).value || '';
    const end = (document.getElementById('clipEnd') || {}).value || '';
    closeDownloadModalForce();
    showToast(); // Show "Download Started" toast

    try {
        const res = await fetch('/api/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: currentVideoInfo.url,
                kind: kind,
                quality: quality,
                height: height || 0,
                start: start.trim() || null,
                end: end.trim() || null
            })
        });
        const d = await res.json();
        if (d.download_id) {
            activeDownloads.add(d.download_id);
            updateDownloadsDropdown(); // Init entry
        }
    } catch (e) {
        alert("Download start failed");
    }
}

// Global Polling for Active Downloads
function startGlobalPolling() {
    setInterval(async () => {
        if (activeDownloads.size === 0) return;

        for (let id of activeDownloads) {
            try {
                const res = await fetch(`/api/progress/${id}`);
                const p = await res.json();
                updateDownloadItemHTML(id, p);

                if (p.status === 'finished' || p.status === 'error') {
                    activeDownloads.delete(id); // Stop polling custom logic, rely on UI
                    // Maybe we keep it in UI but stop fetching? 
                    // For now, we update one last time then leave it.
                }
            } catch (e) {
                console.log("Poll error", e);
            }
        }
        updateBadge();
    }, 1000);
}

// Manages the Dropdown UI
let downloadStateCache = {}; // id -> data

function updateDownloadItemHTML(id, p) {
    downloadStateCache[id] = p;
    updateDownloadsDropdown();
}

function updateDownloadsDropdown() {
    const list = document.getElementById('downloadsList');
    // Simple render loop (can be optimized but fine for <10 items)
    // In real app, we wouldn't redraw all every second.

    const ids = Object.keys(downloadStateCache).reverse(); // Newest first
    if (ids.length === 0) {
        list.innerHTML = '<div class="empty-state">No downloads yet</div>';
        return;
    }

    list.innerHTML = '';
    ids.forEach(id => {
        const d = downloadStateCache[id];
        const el = document.createElement('div');
        el.className = 'dd-item';

        let icon = '<i class="fa-solid fa-file-video"></i>';
        if (d.filename && d.filename.endsWith('.mp3')) icon = '<i class="fa-solid fa-file-audio"></i>';

        // Status String
        let statusStr = '';
        if (d.status === 'downloading') statusStr = `${d.speed || ''} • ${d.eta || ''} left`;
        else if (d.status === 'processing') statusStr = 'Converting...';
        else if (d.status === 'finished') statusStr = 'Completed';
        else if (d.status === 'error') statusStr = 'Error';

        // Progress Bar Width
        let pct = d.progress || 0;
        let showFolder = (d.status === 'finished') ? `<button class="folder-btn" onclick="showInFolder('${d.filename.replace(/'/g, "\\'")}')" title="Show in Folder"><i class="fa-regular fa-folder-open"></i></button>` : '';

        el.innerHTML = `
            <div class="file-icon">${icon}</div>
            <div class="dd-info">
                <div class="dd-filename">${d.filename || 'Initializing...'}</div>
                <div class="dd-progress-bg">
                    <div class="dd-progress-fill" style="width: ${pct}%"></div>
                </div>
                <div class="dd-status">${statusStr}</div>
            </div>
            <div class="dd-actions">
                ${showFolder}
            </div>
        `;
        list.appendChild(el);
    });
}

function toggleDownloadsDropdown() {
    const d = document.getElementById('downloadsDropdown');
    d.classList.toggle('hidden');
}

async function showInFolder(filename) {
    if (!filename) return;
    await fetch('/api/show_folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: filename })
    });
}

function updateBadge() {
    const count = activeDownloads.size;
    const badge = document.getElementById('dlBadge');
    badge.innerText = count;
    if (count > 0) badge.classList.remove('hidden');
    else badge.classList.add('hidden');
}

function showToast() {
    const t = document.getElementById('downloadToast');
    t.classList.remove('hidden');
    setTimeout(() => { t.classList.add('hidden'); }, 3000);
}

function clearAllDownloads() {
    downloadStateCache = {};
    activeDownloads.clear();
    updateDownloadsDropdown();
}

async function openDownloadsFolder() {
    try {
        await fetch('/api/open_downloads_folder', { method: 'POST' });
    } catch (e) {
        console.error(e);
    }
}

// Helpers
function formatDuration(seconds) {
    if (!seconds) return '0:00';
    const min = Math.floor(seconds / 60);
    const sec = Math.floor(seconds % 60);
    return `${min}:${sec.toString().padStart(2, '0')}`;
}
function formatViews(views) {
    if (!views) return '';
    if (views > 1000000) return (views / 1000000).toFixed(1) + 'M views';
    if (views > 1000) return (views / 1000).toFixed(1) + 'K views';
    return views + ' views';
}
function timeAgo(dateStr) {
    if (!dateStr || dateStr.length !== 8) return 'Recently';
    const year = dateStr.slice(0, 4);
    const month = dateStr.slice(4, 6);
    const day = dateStr.slice(6, 8);
    return `${day}/${month}/${year}`;
}
function showLoading(show) {
    const el = document.getElementById('loadingOverlay');
    if (show) el.classList.remove('hidden'); else el.classList.add('hidden');
}

// --- Category Filter ---
function filterCategory(category) {
    // Update active pill UI
    document.querySelectorAll('.category-pill').forEach(btn => {
        if (btn.textContent === category) btn.classList.add('active');
        else btn.classList.remove('active');
    });

    currentPage = 1; // Reset pagination
    isFeedExhausted = false;

    if (category === 'All') {
        loadHomeFeed();
    } else {
        performSearch(category);
    }
}

// --- Debounce Helper ---
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// --- Debounced Search (for live typing) ---
const debouncedSearch = debounce((query) => {
    if (query.length >= 3) performSearch(query);
}, 400);

// Enable live search as user types (optional - can be triggered from input event)
// document.getElementById('searchInput').addEventListener('input', (e) => debouncedSearch(e.target.value));

// ==========================================
// THEATER MODE & MINI PLAYER
// ==========================================
let isTheaterMode = false;
let isMiniPlayerActive = false;

function toggleTheaterMode() {
    const watchSection = document.getElementById('watchSection');
    watchSection.classList.toggle('theater-mode');
    isTheaterMode = !isTheaterMode;
}

function toggleMiniPlayer() {
    const miniPlayer = document.getElementById('miniPlayerContainer');
    const mainPlayer = document.getElementById('previewPlayer');
    const miniFrame = document.getElementById('miniPlayerFrame');

    if (!isMiniPlayerActive) {
        miniFrame.src = mainPlayer.src;
        miniPlayer.classList.add('active');
        isMiniPlayerActive = true;
        // Scroll to top to show grid
        document.querySelector('.main-content').scrollTop = 0;
    } else {
        closeMiniPlayer();
    }
}

function closeMiniPlayer() {
    const miniPlayer = document.getElementById('miniPlayerContainer');
    const miniFrame = document.getElementById('miniPlayerFrame');
    miniFrame.src = '';
    miniPlayer.classList.remove('active');
    isMiniPlayerActive = false;
}

function toggleFullscreen() {
    const player = document.getElementById('playerContainer');
    if (document.fullscreenElement) {
        document.exitFullscreen();
    } else {
        player.requestFullscreen();
    }
}

// ==========================================
// LIKE / DISLIKE / SUBSCRIBE
// ==========================================
let isLiked = false;
let isDisliked = false;
let isSubscribed = false;

function toggleLike() {
    const likeBtn = document.getElementById('likeBtn');
    const dislikeBtn = document.getElementById('dislikeBtn');

    if (isLiked) {
        likeBtn.classList.remove('active');
        likeBtn.querySelector('i').classList.replace('fa-solid', 'fa-regular');
        isLiked = false;
    } else {
        likeBtn.classList.add('active', 'animating');
        likeBtn.querySelector('i').classList.replace('fa-regular', 'fa-solid');
        isLiked = true;
        // Remove dislike if active
        if (isDisliked) {
            dislikeBtn.classList.remove('active');
            dislikeBtn.querySelector('i').classList.replace('fa-solid', 'fa-regular');
            isDisliked = false;
        }
        // Remove animation class after animation
        setTimeout(() => likeBtn.classList.remove('animating'), 300);
    }
}

function toggleDislike() {
    const likeBtn = document.getElementById('likeBtn');
    const dislikeBtn = document.getElementById('dislikeBtn');

    if (isDisliked) {
        dislikeBtn.classList.remove('active');
        dislikeBtn.querySelector('i').classList.replace('fa-solid', 'fa-regular');
        isDisliked = false;
    } else {
        dislikeBtn.classList.add('active');
        dislikeBtn.querySelector('i').classList.replace('fa-regular', 'fa-solid');
        isDisliked = true;
        // Remove like if active
        if (isLiked) {
            likeBtn.classList.remove('active');
            likeBtn.querySelector('i').classList.replace('fa-solid', 'fa-regular');
            isLiked = false;
        }
    }
}

function toggleSubscribe() {
    const btn = document.getElementById('subscribeBtn');
    if (isSubscribed) {
        btn.textContent = 'Subscribe';
        btn.classList.remove('subscribed');
        isSubscribed = false;
    } else {
        btn.textContent = 'Subscribed';
        btn.classList.add('subscribed');
        isSubscribed = true;
    }
}

// ==========================================
// SHARE MODAL
// ==========================================
function openShareModal() {
    const overlay = document.getElementById('shareModalOverlay');
    const input = document.getElementById('shareLinkInput');
    if (currentVideoInfo && currentVideoInfo.url) {
        input.value = currentVideoInfo.url;
    }
    overlay.classList.add('active');
}

function closeShareModal(e) {
    if (e.target.id === 'shareModalOverlay') {
        document.getElementById('shareModalOverlay').classList.remove('active');
    }
}

function closeShareModalForce() {
    document.getElementById('shareModalOverlay').classList.remove('active');
}

function copyShareLink() {
    const input = document.getElementById('shareLinkInput');
    input.select();
    document.execCommand('copy');
    alert('Link copied!');
}

function shareToWhatsApp() {
    window.open(`https://wa.me/?text=${encodeURIComponent(currentVideoInfo?.url || '')}`, '_blank');
}

function shareToFacebook() {
    window.open(`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(currentVideoInfo?.url || '')}`, '_blank');
}

function shareToTwitter() {
    window.open(`https://twitter.com/intent/tweet?url=${encodeURIComponent(currentVideoInfo?.url || '')}`, '_blank');
}

function shareToEmail() {
    window.location.href = `mailto:?subject=Check out this video&body=${encodeURIComponent(currentVideoInfo?.url || '')}`;
}

function shareToEmbed() {
    const url = currentVideoInfo?.url || '';
    let videoId = '';
    if (url.includes('v=')) videoId = url.split('v=')[1].split('&')[0];
    const embedCode = `<iframe width="560" height="315" src="https://www.youtube.com/embed/${videoId}" frameborder="0" allowfullscreen></iframe>`;
    navigator.clipboard.writeText(embedCode);
    alert('Embed code copied!');
}

// ==========================================
// WATCH LATER / SAVE
// ==========================================
function saveToWatchLater() {
    if (!currentVideoInfo) return;
    let watchLater = JSON.parse(localStorage.getItem('watchLater') || '[]');
    const exists = watchLater.find(v => v.url === currentVideoInfo.url);
    if (!exists) {
        watchLater.push({
            title: currentVideoInfo.title,
            url: currentVideoInfo.url,
            thumbnail: currentVideoInfo.thumbnail
        });
        localStorage.setItem('watchLater', JSON.stringify(watchLater));
        alert('Saved to Watch Later!');
    } else {
        alert('Already in Watch Later');
    }
}

// ==========================================
// EXPANDABLE DESCRIPTION
// ==========================================
document.addEventListener('click', (e) => {
    const descBox = document.getElementById('descriptionBox');
    if (descBox && descBox.contains(e.target)) {
        descBox.classList.toggle('expanded');
    }
});

// ==========================================
// KEYBOARD SHORTCUTS
// ==========================================
document.addEventListener('keydown', (e) => {
    // Ignore if typing in input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    const watchVisible = !document.getElementById('watchSection').classList.contains('hidden');

    switch (e.key.toLowerCase()) {
        case ' ':
            // Space to pause/play (iframe doesn't support this easily, but we can try)
            e.preventDefault();
            break;
        case 'f':
            if (watchVisible) toggleFullscreen();
            break;
        case 't':
            if (watchVisible) toggleTheaterMode();
            break;
        case 'i':
            if (watchVisible) toggleMiniPlayer();
            break;
        case 'escape':
            closeShareModalForce();
            closeDownloadModalForce();
            closeMiniPlayer();
            break;
    }
});

// ==========================================
// AUTO UPDATE LOGIC
// ==========================================
async function checkForUpdates() {
    const lastCheck = localStorage.getItem('lastUpdateCheck');
    const now = Date.now();
    const oneWeek = 7 * 24 * 60 * 60 * 1000;

    // Check if it's been a week or never checked (or for testing, we can force it)
    if (!lastCheck || (now - parseInt(lastCheck)) > oneWeek) {
        console.log('Checking for updates...');
        try {
            const res = await fetch('/api/check_update');
            const data = await res.json();

            if (data.update_available) {
                const btn = document.getElementById('updateBtn');
                if (btn) btn.classList.remove('hidden');
                // We update the timestamp only if we successfully checked
                localStorage.setItem('lastUpdateCheck', now.toString());
            } else {
                // Also update timestamp if checked and no update
                localStorage.setItem('lastUpdateCheck', now.toString());
            }
        } catch (e) {
            console.error('Update check failed:', e);
        }
    } else {
        console.log('Skipping update check (checked recently)');
    }
}

async function performUpdate() {
    if (!confirm("Update SanTube to the latest version? Server will restart.")) return;

    showLoading(true);
    try {
        const res = await fetch('/api/update', { method: 'POST' });
        const data = await res.json();

        if (data.success) {
            alert(data.message);
            // Reload page to reflect changes (and potentially reconnect to restarted server)
            setTimeout(() => location.reload(), 2000);
        } else {
            alert('Update Failed: ' + data.message);
            showLoading(false);
        }
    } catch (e) {
        alert('Update Request Failed: ' + e.message);
        showLoading(false);
    }
}

// ==========================================
// MORE OPTIONS MENU (placeholder)
// ==========================================
function toggleMoreOptions(e) {
    e.stopPropagation();
    alert('More options coming soon: Report, Transcript, Clip');
}

// ==========================================
// THEME TOGGLE (DARK/LIGHT)
// ==========================================
function toggleTheme() {
    const html = document.documentElement;
    const icon = document.getElementById('themeIcon');
    const currentTheme = html.getAttribute('data-theme');

    if (currentTheme === 'light') {
        html.removeAttribute('data-theme');
        icon.classList.replace('fa-sun', 'fa-moon');
        localStorage.setItem('theme', 'dark');
    } else {
        html.setAttribute('data-theme', 'light');
        icon.classList.replace('fa-moon', 'fa-sun');
        localStorage.setItem('theme', 'light');
    }
}

// Initialize theme from localStorage
(function initTheme() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
        const icon = document.getElementById('themeIcon');
        if (icon) icon.classList.replace('fa-moon', 'fa-sun');
    }
})();

// ==========================================
// WATCH HISTORY (localStorage)
// ==========================================
function addToHistory(data, url) {
    let history = JSON.parse(localStorage.getItem('watchHistory') || '[]');

    // Remove if already exists (move to front)
    history = history.filter(v => v.url !== url);

    // Add to front
    history.unshift({
        title: data.title,
        url: url,
        thumbnail: data.thumbnail,
        uploader: data.uploader,
        timestamp: Date.now()
    });

    // Keep only last 50
    history = history.slice(0, 50);

    localStorage.setItem('watchHistory', JSON.stringify(history));
}

function getWatchHistory() {
    return JSON.parse(localStorage.getItem('watchHistory') || '[]');
}

function clearWatchHistory() {
    localStorage.removeItem('watchHistory');
    alert('Watch history cleared!');
}

// ==========================================
// AUTO-SHUTDOWN HEARTBEAT
// ==========================================
setInterval(() => {
    fetch('/api/heartbeat', { method: 'POST' }).catch(e => {
        // console.log("Heartbeat failed (server closed?)");
    });
}, 2000); // Ping every 2 seconds
