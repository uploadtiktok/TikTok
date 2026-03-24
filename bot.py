import asyncio
import requests
import os
import base64
import feedparser
import yt_dlp
from xml.dom import minidom
from xml.etree import ElementTree as ET
from datetime import datetime
import pytz
import subprocess

# ============================================
# CONFIGURATION
# ============================================

# GitHub Settings
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'uploadtiktok/TikTok')
GITHUB_BRANCH = os.environ.get('GITHUB_BRANCH', 'main')

# YouTube Settings
YOUTUBE_RSS_URL = os.environ.get('YOUTUBE_RSS_URL', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCLSEQ0cuNz_vJ_H3uXB1R7w')

# File Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEOS_DIR = os.path.join(BASE_DIR, "Videos")
RSS_FILE = os.path.join(BASE_DIR, "rss.xml")
PROCESSED_LOG = os.path.join(BASE_DIR, "processed_urls.txt")
COOKIES_FILE = os.path.join(BASE_DIR, "cookies.txt")

# Create Videos directory if not exists
os.makedirs(VIDEOS_DIR, exist_ok=True)

# Settings
MAX_RSS_ITEMS = 3
MIN_DURATION = 20
MAX_VIDEOS_CHECK = 20

# ============================================
# UTILITY FUNCTIONS
# ============================================

def get_last_url():
    if not os.path.exists(PROCESSED_LOG):
        return None
    try:
        with open(PROCESSED_LOG, "r", encoding="utf-8") as f:
            return f.read().strip()
    except:
        return None

def save_last_url(url):
    with open(PROCESSED_LOG, "w", encoding="utf-8") as f:
        f.write(url)

def get_algeria_time():
    tz = pytz.timezone('Africa/Algiers')
    return datetime.now(tz).strftime('%a, %d %b %Y %H:%M:%S +0100')

def git_commit(file_path, commit_msg):
    """Commit file to git"""
    try:
        subprocess.run(['git', 'config', '--global', 'user.email', 'action@github.com'], check=True, capture_output=True)
        subprocess.run(['git', 'config', '--global', 'user.name', 'GitHub Action'], check=True, capture_output=True)
        subprocess.run(['git', 'add', file_path], check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', commit_msg, '--allow-empty'], check=True, capture_output=True)
        subprocess.run(['git', 'push'], check=True, capture_output=True)
        print(f"✅ Committed: {file_path}")
        return True
    except Exception as e:
        print(f"❌ Commit failed: {e}")
        return False

# ============================================
# YOUTUBE FUNCTIONS
# ============================================

def get_video_duration(url):
    """Get video duration with anti-bot measures"""
    try:
        opts = {
            'quiet': True,
            'no_warnings': True,
            'extractor_args': {'youtube': {'skip': ['dash', 'hls']}},
            'sleep_interval': 3,
        }
        
        # Add cookies if file exists
        if os.path.exists(COOKIES_FILE):
            opts['cookiefile'] = COOKIES_FILE
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('duration', 0)
    except Exception as e:
        print(f"⚠️ Duration error: {e}")
        return None

def download_video_to_repo(url, filename):
    """Download video directly to Videos folder"""
    video_path = os.path.join(VIDEOS_DIR, filename)
    
    opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': video_path,
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'youtube': {'skip': ['dash', 'hls']}},
        'throttledratelimit': 1000000,
        'sleep_interval': 5,
        'max_sleep_interval': 10,
        'sleep_interval_requests': 2,
    }
    
    # Add cookies if file exists
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
    
    try:
        if os.path.exists(video_path):
            os.remove(video_path)
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        
        if os.path.exists(video_path):
            return video_path
        return None
    except Exception as e:
        print(f"⚠️ DL failed: {e}")
        return None

# ============================================
# RSS FUNCTIONS
# ============================================

def get_existing_rss_items():
    items = []
    if not os.path.exists(RSS_FILE):
        return items
    
    try:
        tree = ET.parse(RSS_FILE)
        root = tree.getroot()
        channel = root.find('channel')
        
        for item in channel.findall('item'):
            title = item.find('title').text if item.find('title') is not None else ''
            link = item.find('link').text if item.find('link') is not None else ''
            enclosure = item.find('enclosure')
            enc_url = enclosure.get('url') if enclosure is not None else ''
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ''
            
            items.append({
                'title': title,
                'link': link,
                'enclosure_url': enc_url,
                'pub_date': pub_date
            })
    except:
        pass
    
    return items

def update_rss(title, video_url, video_filename):
    """Update RSS with video from Videos folder"""
    title_with_hash = f"{title} #محمد_بن_شمس_الدين"
    items = get_existing_rss_items()
    
    # GitHub raw URL for video
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/Videos/{video_filename}"
    
    new_item = {
        'title': title_with_hash,
        'link': video_url,
        'enclosure_url': raw_url,
        'pub_date': get_algeria_time()
    }
    
    items.append(new_item)
    
    if len(items) > MAX_RSS_ITEMS:
        items.pop(0)
        print(f"🗑️ Removed oldest")
    
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    
    ET.SubElement(channel, 'title').text = 'مقاطع بجاد الأثري - Shorts'
    ET.SubElement(channel, 'link').text = f'https://github.com/{GITHUB_REPO}'
    ET.SubElement(channel, 'description').text = 'آخر مقاطع الـ Shorts للشيخ محمد بن شمس الدين'
    ET.SubElement(channel, 'language').text = 'ar-sa'
    ET.SubElement(channel, 'lastBuildDate').text = get_algeria_time()
    
    for item in items:
        elem = ET.SubElement(channel, 'item')
        ET.SubElement(elem, 'title').text = item['title']
        ET.SubElement(elem, 'link').text = item['link']
        ET.SubElement(elem, 'pubDate').text = item['pub_date']
        ET.SubElement(elem, 'enclosure', url=item['enclosure_url'], type='video/mp4')
        ET.SubElement(elem, 'guid', isPermaLink='false').text = item['link']
    
    xml_str = minidom.parseString(ET.tostring(rss)).toprettyxml(indent="  ")
    xml_lines = [line for line in xml_str.split('\n') if line.strip()]
    
    with open(RSS_FILE, "w", encoding="utf-8") as f:
        f.write('\n'.join(xml_lines))
    
    print(f"✅ RSS: {len(items)} items")

# ============================================
# MAIN PROCESSING
# ============================================

def get_new_videos():
    feed = feedparser.parse(YOUTUBE_RSS_URL)
    if not feed.entries:
        print("⚠️ No entries")
        return []
    
    last_url = get_last_url()
    entries = feed.entries[:MAX_VIDEOS_CHECK]
    
    last_idx = -1
    for i, entry in enumerate(entries):
        if entry.link == last_url:
            last_idx = i
            break
    
    if last_idx == -1:
        if last_url:
            print("⚠️ Last URL not found")
        return [entries[0]] if entries else []
    else:
        return entries[:last_idx]

async def process_video(entry):
    url = entry.link
    title = entry.title
    vid = entry.yt_videoid
    
    print(f"\n🔍 {title[:50]}...")
    
    # Check duration
    duration = get_video_duration(url)
    if duration is None:
        return False
    
    print(f"   ⏱️ {duration}s")
    
    if duration < MIN_DURATION:
        print(f"   ⏭️ Skip (<{MIN_DURATION}s)")
        save_last_url(url)
        git_commit(PROCESSED_LOG, f"Update processed URL")
        return False
    
    print(f"🎯 Processing ({duration}s)")
    
    # Download directly to Videos folder
    filename = f"{vid}.mp4"
    video_path = download_video_to_repo(url, filename)
    
    if not video_path:
        print("❌ Download failed")
        return False
    
    print(f"✅ Downloaded: {filename}")
    
    # Update RSS
    update_rss(title, url, filename)
    
    # Save last URL
    save_last_url(url)
    
    # Commit all changes to GitHub
    git_commit(VIDEOS_DIR, f"Add video: {title[:50]}")
    git_commit(RSS_FILE, "Update RSS feed")
    git_commit(PROCESSED_LOG, "Update processed URL")
    
    print(f"✅ Done: {vid}")
    return True

async def main():
    print("🚀 Bot started (GitHub Actions)")
    print(f"📦 Repo: {GITHUB_REPO}")
    print(f"📁 Videos dir: {VIDEOS_DIR}")
    
    # Check cookies file
    if os.path.exists(COOKIES_FILE):
        print(f"🍪 Cookies file found")
    else:
        print(f"⚠️ No cookies file, may fail on YouTube")
    
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN not set")
        return
    
    new_videos = get_new_videos()
    
    if not new_videos:
        print("😴 No new videos")
        return
    
    print(f"🆕 Found: {len(new_videos)}")
    
    # Process videos from oldest to newest
    for entry in reversed(new_videos):
        await process_video(entry)
    
    print("\n🏁 Finished")

if __name__ == "__main__":
    asyncio.run(main())
