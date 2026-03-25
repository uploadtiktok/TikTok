import asyncio
import os
import base64
import requests
from xml.dom import minidom
from xml.etree import ElementTree as ET
from datetime import datetime
import pytz
from pathlib import Path

# ============================================
# CONFIGURATION
# ============================================
TOKEN = os.environ.get('GITHUB_TOKEN', os.environ.get('PAT_TOKEN', ''))  # دعم كلا المتغيرين
REPO = os.environ.get('GITHUB_REPO', 'uploadtiktok/TikTok')
BRANCH = os.environ.get('GITHUB_BRANCH', 'main')

BASE_DIR = Path(__file__).parent
VIDEOS_DIR = BASE_DIR / "Videos"
VIDEOS_DIR.mkdir(exist_ok=True)

MAX_ITEMS = 3
VIDEOS_PER_DAY = 3

# ============================================
# GITHUB API FUNCTIONS
# ============================================
def gh_api(endpoint, method='GET', data=None):
    url = f"https://api.github.com/repos/{REPO}/{endpoint}"
    headers = {
        'Authorization': f'token {TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    try:
        if method == 'GET':
            r = requests.get(url, headers=headers)
        else:
            r = requests.put(url, headers=headers, json=data)
        
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        print(f"❌ GitHub API Error: {e}")
        print(f"Status Code: {r.status_code if 'r' in locals() else 'Unknown'}")
        print(f"Response: {r.text if 'r' in locals() else 'No response'}")
        raise

def get_gh_file(path):
    try:
        res = gh_api(f"contents/{path}")
        if not res:
            return None, None
        content = base64.b64decode(res['content']).decode('utf-8')
        return content, res['sha']
    except Exception as e:
        print(f"⚠️ Could not read {path}: {e}")
        return None, None

def save_gh_file(path, content, msg, sha=None):
    encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    data = {'message': msg, 'content': encoded, 'branch': BRANCH}
    if sha:
        data['sha'] = sha
    result = gh_api(f"contents/{path}", 'PUT', data)
    print(f"✅ Saved {path}")
    return result

def delete_gh_file(path, sha, msg):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    headers = {
        'Authorization': f'token {TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    data = {
        'message': msg,
        'sha': sha,
        'branch': BRANCH
    }
    r = requests.delete(url, headers=headers, json=data)
    r.raise_for_status()
    print(f"🗑️ Deleted {path}")
    return r.json()

# ============================================
# RSS UPDATE
# ============================================
def update_rss(new_items):
    old_content, _ = get_gh_file("rss.xml")
    items = []

    if old_content:
        try:
            root = ET.fromstring(old_content)
            for item in root.findall('.//item'):
                link = item.find('link').text if item.find('link') is not None else ""
                enc_node = item.find('enclosure')
                enc_url = enc_node.get('url') if enc_node is not None else ""
                video_url = link if link else enc_url
                if video_url:
                    items.append({
                        'title': item.find('title').text,
                        'video_url': video_url,
                        'pub_date': item.find('pubDate').text if item.find('pubDate') is not None else ""
                    })
        except Exception as e:
            print(f"⚠️ Error parsing RSS: {e}")

    items.extend(new_items)

    if len(items) > MAX_ITEMS:
        items = items[-MAX_ITEMS:]

    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = 'مقاطع الفيديو - Shorts'
    ET.SubElement(channel, 'link').text = f"https://github.com/{REPO}"
    ET.SubElement(channel, 'language').text = 'ar-sa'
    ET.SubElement(channel, 'lastBuildDate').text = datetime.now(pytz.timezone('Africa/Algiers')).strftime('%a, %d %b %Y %H:%M:%S +0100')

    for item in items:
        node = ET.SubElement(channel, 'item')
        ET.SubElement(node, 'title').text = item['title']
        ET.SubElement(node, 'link').text = item['video_url']
        ET.SubElement(node, 'pubDate').text = item['pub_date']
        ET.SubElement(node, 'enclosure', url=item['video_url'], type='video/mp4')
        ET.SubElement(node, 'guid', isPermaLink='false').text = item['video_url']

    xml_str = ET.tostring(rss, encoding='utf-8')
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent="  ")
    clean_xml = "\n".join(line for line in pretty_xml.split('\n') if line.strip())

    _, sha = get_gh_file("rss.xml")
    save_gh_file("rss.xml", clean_xml, f"إضافة {len(new_items)} مقاطع", sha)

# ============================================
# TRACKER
# ============================================
def get_processed_videos():
    content, _ = get_gh_file("processed_videos.txt")
    if content:
        return set(line.strip() for line in content.splitlines() if line.strip())
    return set()

def update_processed_videos(new_files):
    existing = get_processed_videos()
    existing.update(new_files)
    new_content = "\n".join(sorted(existing)) + ("\n" if existing else "")
    _, sha = get_gh_file("processed_videos.txt")
    save_gh_file("processed_videos.txt", new_content, "تحديث قائمة المقاطع المعالجة", sha)

# ============================================
# MAIN
# ============================================
def get_local_videos():
    video_files = list(VIDEOS_DIR.glob("*.mp4"))
    video_files.sort(key=lambda p: p.name)
    return [f.name for f in video_files]

async def main():
    if not TOKEN:
        print("❌ خطأ: GITHUB_TOKEN أو PAT_TOKEN غير موجود.")
        print("تأكد من تعيين المتغير في GitHub Secrets")
        return

    print(f"🚀 Starting video processing...")
    print(f"Repository: {REPO}")
    print(f"Branch: {BRANCH}")
    
    all_videos = get_local_videos()
    if not all_videos:
        print("⚠️ لا توجد مقاطع فيديو في مجلد Videos.")
        return

    print(f"📹 Found {len(all_videos)} videos: {', '.join(all_videos)}")
    
    processed = get_processed_videos()
    print(f"📝 Previously processed: {len(processed)} videos")
    
    pending = [v for v in all_videos if v not in processed]
    
    if not pending:
        print("✅ جميع المقاطع تمت معالجتها مسبقاً.")
        return

    today_videos = pending[:VIDEOS_PER_DAY]
    print(f"📌 سيتم معالجة {len(today_videos)} مقطع اليوم: {', '.join(today_videos)}")

    new_rss_items = []
    for filename in today_videos:
        title = Path(filename).stem
        raw_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/Videos/{filename}"
        pub_date = datetime.now(pytz.timezone('Africa/Algiers')).strftime('%a, %d %b %Y %H:%M:%S +0100')
        new_rss_items.append({
            'title': title,
            'video_url': raw_url,
            'pub_date': pub_date
        })

    print("📡 Updating RSS...")
    update_rss(new_rss_items)

    print("🗑️ Deleting processed videos...")
    for filename in today_videos:
        try:
            _, sha = get_gh_file(f"Videos/{filename}")
            if sha:
                delete_gh_file(f"Videos/{filename}", sha, f"حذف {filename} بعد الإضافة")
            else:
                print(f"⚠️ لم يتم العثور على {filename} على GitHub.")
        except Exception as e:
            print(f"❌ فشل حذف {filename} من GitHub: {e}")

        local_path = VIDEOS_DIR / filename
        if local_path.exists():
            local_path.unlink()
            print(f"🗑️ تم حذف {filename} من المجلد المحلي.")

    update_processed_videos(today_videos)

    remaining = len(pending) - len(today_videos)
    print(f"✅ تمت معالجة {len(today_videos)} مقاطع. المتبقي: {remaining}")

if __name__ == "__main__":
    asyncio.run(main())
