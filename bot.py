import asyncio
import requests
import os
import base64
import re
from xml.dom import minidom
from xml.etree import ElementTree as ET
from datetime import datetime
import pytz
import subprocess
from bs4 import BeautifulSoup

# ============================================
# CONFIGURATION
# ============================================

# GitHub Settings
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'uploadtiktok/TikTok')
GITHUB_BRANCH = os.environ.get('GITHUB_BRANCH', 'main')

# Telegram Settings
TELEGRAM_URL = "https://t.me/s/zapiershorts"

# File Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEOS_DIR = os.path.join(BASE_DIR, "Videos")
RSS_FILE = os.path.join(BASE_DIR, "rss.xml")
PROCESSED_LOG = os.path.join(BASE_DIR, "lastURL.txt")

# Create Videos directory if not exists
os.makedirs(VIDEOS_DIR, exist_ok=True)

# Settings
MAX_RSS_ITEMS = 3
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
# TELEGRAM FUNCTIONS
# ============================================

def fetch_telegram_posts(url, count=50, since_link=None):
    """Fetch latest posts from Telegram channel"""
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    messages = soup.find_all('div', class_='tgme_widget_message_wrap')
    
    posts = []
    for msg in messages:
        # Get message link
        link_tag = msg.find('a', class_='tgme_widget_message_date')
        if not link_tag:
            continue
        link = link_tag.get('href')
        if not link.startswith('https://'):
            link = 'https://t.me' + link
        
        # Stop if we reached last processed post
        if since_link and link == since_link:
            break
        
        # Find video element directly
        video_elem = msg.find('video')
        if not video_elem:
            continue
        
        # Get video src URL
        video_url = video_elem.get('src')
        if not video_url:
            continue
        
        # Get text content
        text_div = msg.find('div', class_='tgme_widget_message_text')
        text = text_div.get_text() if text_div else ''
        
        # Extract video ID from link (e.g., /zapiershorts/26)
        video_id = link.split('/')[-1] if link else str(len(posts) + 1)
        
        posts.append({
            'link': link,
            'video_url': video_url,
            'video_id': video_id,
            'title': text[:100] if text else f'Video {video_id}'
        })
        
        if len(posts) >= count:
            break
    
    return posts

# ============================================
# VIDEO DOWNLOAD FUNCTIONS
# ============================================

def download_telegram_video(video_url, output_path):
    """Download video directly from Telegram CDN"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(video_url, headers=headers, stream=True)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return os.path.exists(output_path)
    except Exception as e:
        print(f"⚠️ Download failed: {e}")
        return False

def download_video(video_url, filename):
    """Download video to Videos folder"""
    video_path = os.path.join(VIDEOS_DIR, filename)
    
    if download_telegram_video(video_url, video_path):
        return video_path
    
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

def get_new_videos_from_telegram():
    """Get new videos from Telegram channel"""
    last_url = get_last_url()
    posts = fetch_telegram_posts(TELEGRAM_URL, MAX_VIDEOS_CHECK, since_link=last_url)
    
    if not posts:
        print("😴 No new videos from Telegram")
        return []
    
    print(f"🆕 Found: {len(posts)} new videos")
    return posts

async def process_video(post):
    """Process single video from Telegram post"""
    video_url = post['video_url']
    video_id = post['video_id']
    title = post['title']
    post_link = post['link']
    
    print(f"\n🔍 {title[:50]}...")
    print(f"   🎬 Video ID: {video_id}")
    
    # Download video
    filename = f"{video_id}.mp4"
    video_path = download_video(video_url, filename)
    
    if not video_path:
        print("❌ Download failed")
        return False
    
    print(f"✅ Downloaded: {filename}")
    
    # Update RSS
    update_rss(title, post_link, filename)
    
    # Save last processed URL (Telegram post link)
    save_last_url(post_link)
    
    # Commit all changes to GitHub
    git_commit(VIDEOS_DIR, f"Add video: {title[:50]}")
    git_commit(RSS_FILE, "Update RSS feed")
    git_commit(PROCESSED_LOG, "Update last URL")
    
    print(f"✅ Done: {video_id}")
    return True

async def main():
    print("🚀 Bot started (Telegram Source)")
    print(f"📦 Repo: {GITHUB_REPO}")
    print(f"📁 Videos dir: {VIDEOS_DIR}")
    print(f"📡 Telegram: {TELEGRAM_URL}")
    print(f"📄 RSS: {RSS_FILE}")
    print(f"📝 Last URL: {PROCESSED_LOG}")
    
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN not set")
        return
    
    new_videos = get_new_videos_from_telegram()
    
    if not new_videos:
        print("😴 No new videos")
        return
    
    # Process videos from oldest to newest
    for post in reversed(new_videos):
        await process_video(post)
    
    print("\n🏁 Finished")

if __name__ == "__main__":
    asyncio.run(main())
