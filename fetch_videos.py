#!/usr/bin/env python3
import asyncio
import os
import json
import base64
import re
import requests
from pathlib import Path
from datetime import datetime
from xml.dom import minidom
from xml.etree import ElementTree as ET
from telethon import TelegramClient
from telethon.sessions import StringSession

# ========== CONFIGURATION ==========
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
STRING_SESSION = os.environ.get("STRING_SESSION", "")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "zapiershorts")
TOKEN = os.environ.get('PAT_TOKEN', os.environ.get('GITHUB_TOKEN', ''))
REPO = os.environ.get('GITHUB_REPO', 'uploadtiktok/TikTok')
BRANCH = os.environ.get('GITHUB_BRANCH', 'main')

batch_size_str = os.environ.get("BATCH_SIZE", "3")
try:
    BATCH_SIZE = int(batch_size_str) if batch_size_str.strip() else 3
except ValueError:
    BATCH_SIZE = 3

VIDEO_FOLDER = "Videos"
LAST_ID_FILE = "last_message_id.json"
MAX_RSS_ITEMS = 3  # 3 عناصر فقط في الخلاصة
# ====================================

# ========== RSS HELPER FUNCTIONS ==========
def extract_number(filename):
    match = re.search(r'(\d+)', filename)
    if match:
        return int(match.group(1))
    return float('inf')

def clean_title(filename):
    """تنظيف عنوان المقطع"""
    title = filename.replace('.mp4', '')
    pattern = r'^\d+_\d{8}_\d{6}_\d+_'
    title = re.sub(pattern, '', title)
    title = re.sub(r'^\d+_', '', title)
    title = re.sub(r'_merged_cleaned$', '', title)
    title = re.sub(r'_(?:merged|cleaned|final|edit|v\d+)+', '', title)
    title = title.replace('_', ' ')
    title = re.sub(r'\s+', ' ', title).strip()
    title = re.sub(r'\bmerged\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bcleaned\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title).strip()
    
    if title:
        title = title[0].upper() + title[1:] if len(title) > 1 else title.upper()
    
    if not title:
        title = filename.replace('.mp4', '').replace('_', ' ')
        title = re.sub(r'\d+', '', title).strip()
    
    return title if title else filename

def gh_api(endpoint, method='GET', data=None):
    url = f"https://api.github.com/repos/{REPO}/{endpoint}"
    headers = {'Authorization': f'token {TOKEN}', 'Accept': 'application/vnd.github.v3+json'}
    try:
        if method == 'GET':
            r = requests.get(url, headers=headers)
        elif method == 'DELETE':
            r = requests.delete(url, headers=headers, json=data)
        else:
            r = requests.put(url, headers=headers, json=data)
        
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        print(f"❌ GitHub API Error: {e}")
        return None

def get_gh_file(path):
    res = gh_api(f"contents/{path}")
    if not res:
        return None, None
    content = base64.b64decode(res['content']).decode('utf-8')
    return content, res['sha']

def save_gh_file(path, content, msg, sha=None):
    encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    data = {'message': msg, 'content': encoded, 'branch': BRANCH}
    if sha:
        data['sha'] = sha
    return gh_api(f"contents/{path}", 'PUT', data)

def get_current_rss_items():
    content, _ = get_gh_file("rss.xml")
    if not content:
        return []
    
    items = []
    try:
        root = ET.fromstring(content)
        for item in root.findall('.//item'):
            title = item.find('title').text if item.find('title') is not None else ""
            link = item.find('link').text if item.find('link') is not None else ""
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
            if link:
                filename = link.split('/')[-1]
                items.append({
                    'title': title,
                    'filename': filename,
                    'link': link,
                    'pub_date': pub_date
                })
    except Exception as e:
        print(f"⚠️ Error parsing RSS: {e}")
    
    return items

def update_rss_with_new_videos(new_videos_filenames):
    """تحديث RSS بإضافة مقاطع جديدة مع الحفاظ على آخر 3 عناصر"""
    print("\n📡 Updating RSS feed...")
    
    # الحصول على العناصر الحالية
    current_items = get_current_rss_items()
    print(f"   Current RSS items: {len(current_items)}")
    
    # إنشاء عناصر جديدة للمقاطع الجديدة
    new_items = []
    for filename in new_videos_filenames:
        clean_title_text = clean_title(filename)
        video_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/Videos/{filename}"
        pub_date = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
        new_items.append({
            'title': clean_title_text,
            'filename': filename,
            'link': video_url,
            'pub_date': pub_date
        })
    
    # دمج العناصر: العناصر الجديدة في البداية + العناصر القديمة
    all_items = new_items + current_items
    
    # الحفاظ على آخر 3 عناصر فقط
    if len(all_items) > MAX_RSS_ITEMS:
        removed = len(all_items) - MAX_RSS_ITEMS
        all_items = all_items[:MAX_RSS_ITEMS]
        print(f"   Removed {removed} old items (keeping last {MAX_RSS_ITEMS})")
    
    # بناء XML جديد
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = 'مقاطع الفيديو - Zapier Shorts'
    ET.SubElement(channel, 'link').text = f"https://github.com/{REPO}"
    ET.SubElement(channel, 'language').text = 'ar-sa'
    ET.SubElement(channel, 'lastBuildDate').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
    ET.SubElement(channel, 'description').text = 'أحدث مقاطع الفيديو من قناة Zapier'
    
    for item in all_items:
        node = ET.SubElement(channel, 'item')
        ET.SubElement(node, 'title').text = item['title']
        ET.SubElement(node, 'link').text = item['link']
        ET.SubElement(node, 'pubDate').text = item['pub_date']
        ET.SubElement(node, 'enclosure', url=item['link'], type='video/mp4')
        ET.SubElement(node, 'guid', isPermaLink='false').text = item['link']
    
    xml_str = ET.tostring(rss, encoding='utf-8')
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent="  ")
    clean_xml = "\n".join(line for line in pretty_xml.split('\n') if line.strip())
    
    _, sha = get_gh_file("rss.xml")
    save_gh_file("rss.xml", clean_xml, f"Update RSS: +{len(new_videos_filenames)} new videos", sha)
    print(f"   ✅ RSS updated with {len(new_items)} new items, total: {len(all_items)}")

def create_empty_rss():
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = 'مقاطع الفيديو - Zapier Shorts'
    ET.SubElement(channel, 'link').text = f"https://github.com/{REPO}"
    ET.SubElement(channel, 'language').text = 'ar-sa'
    ET.SubElement(channel, 'lastBuildDate').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
    ET.SubElement(channel, 'description').text = 'لا توجد مقاطع حالياً'
    
    xml_str = ET.tostring(rss, encoding='utf-8')
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent="  ")
    clean_xml = "\n".join(line for line in pretty_xml.split('\n') if line.strip())
    
    _, sha = get_gh_file("rss.xml")
    save_gh_file("rss.xml", clean_xml, "Empty RSS (no videos)", sha)
    print("✅ RSS emptied")

# ========== TELEGRAM HELPER FUNCTIONS ==========
def setup_folders():
    Path(VIDEO_FOLDER).mkdir(parents=True, exist_ok=True)

def load_last_id():
    if os.path.exists(LAST_ID_FILE):
        try:
            with open(LAST_ID_FILE, 'r') as f:
                data = json.load(f)
                return data.get("last_message_id", None)
        except:
            return None
    return None

def save_last_id(message_id):
    with open(LAST_ID_FILE, 'w') as f:
        json.dump({"last_message_id": message_id}, f)

def is_video_file(document):
    if not document:
        return False
    if document.mime_type and document.mime_type.startswith("video/"):
        return True
    if document.attributes:
        for attr in document.attributes:
            if hasattr(attr, "file_name") and attr.file_name:
                ext = attr.file_name.lower().split(".")[-1]
                if ext in ("mp4", "avi", "mov", "mkv", "webm", "flv", "wmv", "m4v"):
                    return True
    return False

def get_file_name(document):
    if document.attributes:
        for attr in document.attributes:
            if hasattr(attr, "file_name") and attr.file_name:
                return attr.file_name
    return None

# ========== MAIN FUNCTION ==========
async def fetch_videos():
    print("🎬 Telegram Video Fetcher with RSS Integration")
    print(f"📦 Batch size: {BATCH_SIZE}")
    print(f"📡 Max RSS items: {MAX_RSS_ITEMS}")
    print("-" * 40)

    if not (API_ID and API_HASH and STRING_SESSION and CHANNEL_USERNAME):
        print("❌ Missing Telegram secrets")
        return
    
    if not TOKEN:
        print("❌ Missing PAT_TOKEN for GitHub API")
        return

    setup_folders()
    last_id = load_last_id()
    
    if last_id:
        print(f"📍 Last downloaded message ID: {last_id}")
        print(f"🔍 Searching for videos with ID > {last_id}")
    else:
        print("📍 First run - fetching oldest videos first")

    client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
    try:
        await client.start()
        print("✅ Connected to Telegram")

        channel = await client.get_entity(CHANNEL_USERNAME)
        print(f"📢 Channel: {channel.title}")

        print("🔍 Scanning for video messages...")
        all_videos = []
        async for msg in client.iter_messages(channel, reverse=True):
            if msg.video or (msg.document and is_video_file(msg.document)):
                all_videos.append(msg)

        total = len(all_videos)
        print(f"🎬 Total videos in channel: {total}")

        if total == 0:
            print("📭 No videos found in channel.")
            return

        # تحديد المقاطع الجديدة
        if last_id is None:
            videos_to_download = all_videos[:BATCH_SIZE]
            print(f"📥 First run: downloading oldest {len(videos_to_download)} videos")
        else:
            videos_to_download = [v for v in all_videos if v.id > last_id]
            
            if not videos_to_download:
                print("\n" + "="*50)
                print("📭 NO NEW VIDEOS TO DOWNLOAD")
                print(f"   Last downloaded ID: {last_id}")
                ids_list = [v.id for v in all_videos]
                print(f"   Latest video ID in channel: {max(ids_list)}")
                print("="*50)
                return
            
            videos_to_download = videos_to_download[:BATCH_SIZE]
            print(f"📥 Found {len(videos_to_download)} new video(s) with ID > {last_id}")

        print("-" * 40)

        downloaded_ids = []
        downloaded_filenames = []
        
        for i, msg in enumerate(videos_to_download, 1):
            if msg.video:
                original_name = f"video_{msg.id}.mp4"
            else:
                original_name = get_file_name(msg.document) or f"video_{msg.id}.mp4"

            timestamp = msg.date.strftime("%Y%m%d_%H%M%S")
            safe_name = f"{msg.id}_{timestamp}_{original_name}"
            safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._- ")
            file_path = Path(VIDEO_FOLDER) / safe_name

            print(f"📥 ({i}/{len(videos_to_download)}) Downloading: {original_name} (ID: {msg.id})")
            try:
                if msg.video:
                    await client.download_media(msg.video, str(file_path))
                else:
                    await client.download_media(msg.document, str(file_path))

                if file_path.exists() and file_path.stat().st_size > 0:
                    size_mb = file_path.stat().st_size / (1024 * 1024)
                    print(f"✅ Downloaded: {original_name} ({size_mb:.2f} MB)")
                    downloaded_ids.append(msg.id)
                    downloaded_filenames.append(safe_name)
                else:
                    print(f"❌ Download failed: {original_name}")
                    if file_path.exists():
                        file_path.unlink()
                    break
            except Exception as e:
                print(f"⚠️ Error: {e}")
                break

        # تحديث آخر ID
        if downloaded_ids:
            new_last_id = max(downloaded_ids)
            save_last_id(new_last_id)
            print(f"\n📍 Updated last message ID to: {new_last_id}")
            
            # تحديث RSS
            if downloaded_filenames:
                update_rss_with_new_videos(downloaded_filenames)

        print("\n" + "="*50)
        print(f"📈 SUMMARY:")
        print(f"   ✅ Downloaded: {len(downloaded_ids)}")
        print(f"   📁 Saved in: {VIDEO_FOLDER}/")
        print(f"   📍 Last message ID: {load_last_id()}")
        print("="*50)

    except Exception as e:
        print(f"❌ Error: {e}")
        raise
    finally:
        await client.disconnect()
        print("👋 Disconnected")

if __name__ == "__main__":
    asyncio.run(fetch_videos())
