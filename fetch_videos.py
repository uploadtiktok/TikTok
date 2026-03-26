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
MAX_ITEMS = 3  # عدد المقاطع التي نحتفظ بها في المجلد و RSS
# ====================================

# ========== RSS & GITHUB HELPER FUNCTIONS ==========
def extract_number(filename):
    match = re.search(r'(\d+)', filename)
    if match:
        return int(match.group(1))
    return float('inf')

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

def delete_gh_file(path, sha, msg):
    data = {'message': msg, 'sha': sha, 'branch': BRANCH}
    return gh_api(f"contents/{path}", 'DELETE', data)

def get_videos_in_repo():
    """جلب قائمة جميع مقاطع الفيديو في المستودع"""
    try:
        res = gh_api("contents/Videos")
        if not res:
            return []
        videos = [item['name'] for item in res if item['name'].endswith('.mp4')]
        videos.sort(key=lambda x: (extract_number(x), x))
        return videos
    except Exception as e:
        print(f"❌ Failed to list videos: {e}")
        return []

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

def update_rss_with_new_videos(new_videos_data):
    """
    تحديث RSS بإضافة مقاطع جديدة
    new_videos_data: قائمة تحتوي على (filename, title) لكل مقطع
    """
    print("\n📡 Updating RSS feed...")
    
    current_items = get_current_rss_items()
    print(f"   Current RSS items: {len(current_items)}")
    
    # إنشاء عناصر جديدة
    new_items = []
    for filename, title in new_videos_data:
        video_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/Videos/{filename}"
        pub_date = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
        new_items.append({
            'title': title,
            'filename': filename,
            'link': video_url,
            'pub_date': pub_date
        })
    
    # دمج: الجديدة في البداية + القديمة
    all_items = new_items + current_items
    
    # الاحتفاظ بآخر MAX_ITEMS فقط
    if len(all_items) > MAX_ITEMS:
        removed = len(all_items) - MAX_ITEMS
        all_items = all_items[:MAX_ITEMS]
        print(f"   Removed {removed} old items from RSS (keeping last {MAX_ITEMS})")
    
    # بناء XML
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
    save_gh_file("rss.xml", clean_xml, f"Update RSS: +{len(new_videos_data)} new videos", sha)
    print(f"   ✅ RSS updated with {len(new_items)} new items, total: {len(all_items)}")

def cleanup_old_videos(keep_filenames):
    """
    حذف المقاطع القديمة من مجلد Videos
    keep_filenames: قائمة بأسماء الملفات التي نريد الاحتفاظ بها (آخر 3)
    """
    print("\n🗑️ Cleaning up old videos...")
    
    all_videos = get_videos_in_repo()
    print(f"   Total videos in repo: {len(all_videos)}")
    
    to_delete = [v for v in all_videos if v not in keep_filenames]
    
    if not to_delete:
        print("   No old videos to delete")
        return 0
    
    print(f"   Deleting {len(to_delete)} old video(s)...")
    
    deleted_count = 0
    for filename in to_delete:
        try:
            file_info = gh_api(f"contents/Videos/{filename}")
            if file_info and 'sha' in file_info:
                delete_gh_file(f"Videos/{filename}", file_info['sha'], f"Delete old video: {filename}")
                print(f"   🗑️ Deleted: {filename}")
                deleted_count += 1
            else:
                print(f"   ⚠️ Could not find {filename} in repo")
        except Exception as e:
            print(f"   ❌ Failed to delete {filename}: {e}")
    
    return deleted_count

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
    print("🎬 Telegram Video Fetcher with RSS & Cleanup")
    print(f"📦 Batch size: {BATCH_SIZE}")
    print(f"📁 Keep last: {MAX_ITEMS} videos")
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
        downloaded_data = []  # قائمة تحتوي على (filename, caption)
        
        for i, msg in enumerate(videos_to_download, 1):
            # الحصول على الاسم الأصلي للملف
            if msg.video:
                original_name = f"video_{msg.id}.mp4"
            else:
                original_name = get_file_name(msg.document) or f"video_{msg.id}.mp4"

            # الحصول على caption (العنوان النظيف من التليجرام)
            caption = msg.text or msg.caption or ""
            if caption:
                # إزالة الروابط والعلامات غير المرغوب فيها من caption
                caption = caption.strip()
                # إذا كان caption طويلاً جداً، اختر أول 100 حرف
                if len(caption) > 200:
                    caption = caption[:200] + "..."
            else:
                caption = original_name.replace('.mp4', '').replace('_', ' ')
            
            timestamp = msg.date.strftime("%Y%m%d_%H%M%S")
            safe_name = f"{msg.id}_{timestamp}_{original_name}"
            safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._- ")
            file_path = Path(VIDEO_FOLDER) / safe_name

            print(f"📥 ({i}/{len(videos_to_download)}) Downloading: {original_name} (ID: {msg.id})")
            print(f"   📝 Caption: {caption[:80]}..." if len(caption) > 80 else f"   📝 Caption: {caption}")
            
            try:
                if msg.video:
                    await client.download_media(msg.video, str(file_path))
                else:
                    await client.download_media(msg.document, str(file_path))

                if file_path.exists() and file_path.stat().st_size > 0:
                    size_mb = file_path.stat().st_size / (1024 * 1024)
                    print(f"✅ Downloaded: {original_name} ({size_mb:.2f} MB)")
                    downloaded_ids.append(msg.id)
                    downloaded_data.append((safe_name, caption))
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
            
            # تحديث RSS باستخدام caption كعنوان
            if downloaded_data:
                update_rss_with_new_videos(downloaded_data)
            
            # بعد تحديث RSS، نحصل على قائمة الملفات المراد الاحتفاظ بها
            current_rss_items = get_current_rss_items()
            keep_filenames = [item['filename'] for item in current_rss_items]
            
            # حذف المقاطع القديمة
            deleted_count = cleanup_old_videos(keep_filenames)
            if deleted_count > 0:
                print(f"   ✅ Deleted {deleted_count} old video(s) from repo")

        print("\n" + "="*50)
        print(f"📈 SUMMARY:")
        print(f"   ✅ Downloaded: {len(downloaded_ids)}")
        print(f"   📁 Keeping last {MAX_ITEMS} videos in repo")
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
