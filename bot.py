import asyncio
import requests
import os
import base64
from xml.dom import minidom
from xml.etree import ElementTree as ET
from datetime import datetime
import pytz
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
# GITHUB API FUNCTIONS (بدون git commands)
# ============================================

def github_api_request(endpoint, method='GET', data=None):
    """Send request to GitHub API"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/{endpoint}"
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    if method == 'GET':
        response = requests.get(url, headers=headers)
    elif method == 'PUT':
        response = requests.put(url, headers=headers, json=data)
    elif method == 'POST':
        response = requests.post(url, headers=headers, json=data)
    
    response.raise_for_status()
    return response.json()

def get_file_content(path):
    """Get file content from GitHub"""
    try:
        response = github_api_request(f"contents/{path}")
        content = base64.b64decode(response['content']).decode('utf-8')
        return content, response['sha']
    except:
        return None, None

def update_file(path, content, commit_msg, sha=None):
    """Update or create file on GitHub"""
    encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    
    data = {
        'message': commit_msg,
        'content': encoded_content,
        'branch': GITHUB_BRANCH
    }
    
    if sha:
        data['sha'] = sha
    
    try:
        github_api_request(f"contents/{path}", 'PUT', data)
        return True
    except Exception as e:
        print(f"❌ Failed to update {path}: {e}")
        return False

def upload_video(video_path, filename):
    """Upload video file to GitHub"""
    try:
        with open(video_path, 'rb') as f:
            content = base64.b64encode(f.read()).decode('utf-8')
        
        data = {
            'message': f'Add video {filename}',
            'content': content,
            'branch': GITHUB_BRANCH
        }
        
        # Check if file already exists
        try:
            existing = github_api_request(f"contents/Videos/{filename}")
            data['sha'] = existing['sha']
        except:
            pass
        
        github_api_request(f"contents/Videos/{filename}", 'PUT', data)
        return True
    except Exception as e:
        print(f"❌ Failed to upload video: {e}")
        return False

# ============================================
# UTILITY FUNCTIONS
# ============================================

def get_last_post_number():
    """Get last post number from GitHub"""
    content, _ = get_file_content("lastURL.txt")
    if content:
        try:
            return int(content.strip())
        except:
            return 0
    return 0

def save_last_post_number(number):
    """Save last post number to GitHub"""
    content = str(number)
    _, sha = get_file_content("lastURL.txt")
    return update_file("lastURL.txt", content, f"Update last post to {number}", sha)

def extract_post_number(link):
    try:
        return int(link.split('/')[-1])
    except:
        return 0

def get_algeria_time():
    tz = pytz.timezone('Africa/Algiers')
    return datetime.now(tz).strftime('%a, %d %b %Y %H:%M:%S +0100')

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
    """Get existing RSS items from GitHub"""
    content, _ = get_file_content("rss.xml")
    items = []
    
    if not content:
        return items
    
    try:
        root = ET.fromstring(content)
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
    except Exception as e:
        print(f"⚠️ Error parsing RSS: {e}")
    
    return items

def update_rss(title, video_url, video_filename):
    """Update RSS and save to GitHub"""
    # استخدام العنوان الأصلي بدون أي تعديل
    items = get_existing_rss_items()
    
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/Videos/{video_filename}"
    
    new_item = {
        'title': title,  # العنوان الأصلي كما هو
        'link': raw_url,
        'enclosure_url': raw_url,
        'pub_date': get_algeria_time()
    }
    
    items.append(new_item)
    
    if len(items) > MAX_RSS_ITEMS:
        items.pop(0)
        print(f"🗑️ Removed oldest")
    
    # Create RSS XML
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
    rss_content = '\n'.join(xml_lines)
    
    # Save to GitHub
    _, sha = get_file_content("rss.xml")
    return update_file("rss.xml", rss_content, f"Update RSS with {video_filename}", sha)

# ============================================
# MAIN PROCESSING
# ============================================

def get_new_videos_from_telegram():
    last_number = get_last_post_number()
    print(f"📌 Last number from GitHub: {last_number}")
    
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

def process_video(post):
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
    
    # Upload video to GitHub
    if not upload_video(video_path, filename):
        return False
    
    # Update RSS
    if not update_rss(title, post_link, filename):
        return False
    
    # Update last post number
    if not save_last_post_number(post_number):
        return False
    
    # Clean up local file
    os.remove(video_path)
    
    print(f"✅ Done: #{post_number}")
    return True

async def main():
    print("🚀 Bot started")
    print(f"📦 Repo: {GITHUB_REPO}")
    print(f"📡 Telegram: {TELEGRAM_URL}")
    
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN not set")
        return
    
    new_videos = get_new_videos_from_telegram()
    
    if not new_videos:
        print("🏁 No new videos, exiting")
        return
    
    # Process all videos
    processed_numbers = []
    for post in new_videos:
        success = process_video(post)
        if success:
            processed_numbers.append(post['number'])
    
    if processed_numbers:
        print(f"\n✅ Successfully processed {len(processed_numbers)} videos: {processed_numbers}")
    else:
        print("😴 No videos processed successfully")

if __name__ == "__main__":
    asyncio.run(main())
