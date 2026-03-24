import asyncio
import requests
import os
import base64
from xml.dom import minidom
from xml.etree import ElementTree as ET
from datetime import datetime
import pytz
import subprocess
from bs4 import BeautifulSoup

# ============================================
# CONFIGURATION
# ============================================

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'uploadtiktok/TikTok')
GITHUB_BRANCH = os.environ.get('GITHUB_BRANCH', 'main')

TELEGRAM_URL = "https://t.me/s/zapiershorts"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEOS_DIR = os.path.join(BASE_DIR, "Videos")
RSS_FILE = os.path.join(BASE_DIR, "rss.xml")
PROCESSED_LOG = os.path.join(BASE_DIR, "lastURL.txt")

os.makedirs(VIDEOS_DIR, exist_ok=True)

MAX_RSS_ITEMS = 3
MAX_VIDEOS_CHECK = 20

# ============================================
# UTILITY FUNCTIONS
# ============================================

def get_last_post_number():
    if not os.path.exists(PROCESSED_LOG):
        return 0
    try:
        with open(PROCESSED_LOG, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return int(content) if content else 0
    except:
        return 0

def save_last_post_number(number):
    with open(PROCESSED_LOG, "w", encoding="utf-8") as f:
        f.write(str(number))

def extract_post_number(link):
    try:
        return int(link.split('/')[-1])
    except:
        return 0

def get_algeria_time():
    tz = pytz.timezone('Africa/Algiers')
    return datetime.now(tz).strftime('%a, %d %b %Y %H:%M:%S +0100')

def git_commit_all(commit_msg):
    """Commit all changes at once and push"""
    try:
        subprocess.run(['git', 'config', '--global', 'user.email', 'action@github.com'], check=True, capture_output=True)
        subprocess.run(['git', 'config', '--global', 'user.name', 'GitHub Action'], check=True, capture_output=True)
        
        # Add all changed files
        subprocess.run(['git', 'add', VIDEOS_DIR, RSS_FILE, PROCESSED_LOG], check=True, capture_output=True)
        
        # Check if there are changes to commit
        result = subprocess.run(['git', 'diff', '--cached', '--quiet'], capture_output=True)
        if result.returncode == 0:
            print("📝 No changes to commit")
            return True
        
        # Commit
        subprocess.run(['git', 'commit', '-m', commit_msg], check=True, capture_output=True)
        
        # Pull with rebase to avoid conflicts
        subprocess.run(['git', 'pull', '--rebase', 'origin', GITHUB_BRANCH], check=True, capture_output=True)
        
        # Push
        subprocess.run(['git', 'push', 'origin', GITHUB_BRANCH], check=True, capture_output=True)
        
        print(f"✅ Committed and pushed: {commit_msg}")
        return True
    except Exception as e:
        print(f"❌ Git failed: {e}")
        return False

# ============================================
# TELEGRAM FUNCTIONS
# ============================================

def fetch_latest_posts(url, count=50):
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    messages = soup.find_all('div', class_='tgme_widget_message_wrap')
    
    posts = []
    for msg in messages:
        link_tag = msg.find('a', class_='tgme_widget_message_date')
        if not link_tag:
            continue
        link = link_tag.get('href')
        if not link.startswith('https://'):
            link = 'https://t.me' + link
        
        post_number = extract_post_number(link)
        
        video_elem = msg.find('video')
        if not video_elem:
            continue
        
        video_url = video_elem.get('src')
        if not video_url:
            continue
        
        text_div = msg.find('div', class_='tgme_widget_message_text')
        text = text_div.get_text() if text_div else ''
        
        posts.append({
            'link': link,
            'number': post_number,
            'video_url': video_url,
            'title': text[:100] if text else f'Video {post_number}'
        })
        
        if len(posts) >= count:
            break
    
    return posts

# ============================================
# VIDEO DOWNLOAD FUNCTIONS
# ============================================

def download_telegram_video(video_url, output_path):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
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
    title_with_hash = f"{title} #محمد_بن_شمس_الدين"
    items = get_existing_rss_items()
    
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
    last_number = get_last_post_number()
    print(f"📌 Last number: {last_number}")
    
    all_posts = fetch_latest_posts(TELEGRAM_URL, MAX_VIDEOS_CHECK)
    
    if not all_posts:
        print("😴 No posts found")
        return []
    
    if last_number == 0:
        newest = [all_posts[0]]
        print(f"🆕 First run, taking latest post: #{newest[0]['number']}")
        return newest
    
    new_posts = [p for p in all_posts if p['number'] > last_number]
    
    if not new_posts:
        print(f"😴 No new posts (last: {last_number})")
        return []
    
    print(f"🆕 Found {len(new_posts)} new post(s): {[p['number'] for p in new_posts]}")
    new_posts.sort(key=lambda x: x['number'])
    
    return new_posts

async def process_video(post):
    video_url = post['video_url']
    post_number = post['number']
    title = post['title']
    post_link = post['link']
    
    print(f"\n🎬 Post #{post_number}: {title[:50]}...")
    
    filename = f"{post_number}.mp4"
    video_path = download_video(video_url, filename)
    
    if not video_path:
        print(f"❌ Download failed for #{post_number}, skipping")
        return False
    
    print(f"✅ Downloaded: {filename}")
    update_rss(title, post_link, filename)
    save_last_post_number(post_number)
    
    print(f"✅ Done: #{post_number}")
    return True

async def main():
    print("🚀 Bot started")
    print(f"📦 Repo: {GITHUB_REPO}")
    print(f"📁 Videos dir: {VIDEOS_DIR}")
    print(f"📡 Telegram: {TELEGRAM_URL}")
    
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN not set")
        return
    
    new_videos = get_new_videos_from_telegram()
    
    if not new_videos:
        print("🏁 No new videos, exiting")
        return
    
    # Process all videos first
    for post in new_videos:
        await process_video(post)
    
    # Then commit everything at once
    if new_videos:
        numbers = [p['number'] for p in new_videos]
        commit_msg = f"Add videos #{min(numbers)}-{max(numbers)}"
        git_commit_all(commit_msg)
    
    print("\n🏁 Finished")

if __name__ == "__main__":
    asyncio.run(main())
