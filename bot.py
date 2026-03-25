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
TOKEN = os.environ.get('GITHUB_TOKEN', os.environ.get('PAT_TOKEN', ''))
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
    return gh_api(f"contents/{path}", 'PUT', data)

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
    return r.json()

# ============================================
# RSS FUNCTIONS
# ============================================
def get_current_rss_urls():
    """استخراج روابط الفيديو من RSS الحالي"""
    content, _ = get_gh_file("rss.xml")
    if not content:
        return []
    urls = []
    try:
        root = ET.fromstring(content)
        for item in root.findall('.//item'):
            link = item.find('link').text if item.find('link') is not None else ""
            enc_node = item.find('enclosure')
            enc_url = enc_node.get('url') if enc_node is not None else ""
            video_url = link if link else enc_url
            if video_url:
                urls.append(video_url)
    except Exception as e:
        print(f"⚠️ Error parsing RSS: {e}")
    return urls

def update_rss(new_items):
    """إضافة عناصر جديدة إلى RSS والاحتفاظ بآخر 3 عناصر"""
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
            print(f"⚠️ Error parsing old RSS: {e}")

    items.extend(new_items)

    # الاحتفاظ بآخر 3 عناصر فقط
    if len(items) > MAX_ITEMS:
        items = items[-MAX_ITEMS:]

    # بناء XML
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
    print(f"✅ RSS updated with {len(new_items)} items")
    return items  # إرجاع العناصر الجديدة في RSS

# ============================================
# TRACKER - يحتوي فقط على آخر 3 مقاطع
# ============================================
def get_processed_videos():
    """قراءة آخر 3 مقاطع تمت معالجتها"""
    content, _ = get_gh_file("processed_videos.txt")
    if content:
        return [line.strip() for line in content.splitlines() if line.strip()]
    return []

def save_processed_videos(files_list):
    """حفظ قائمة الملفات مباشرة"""
    new_content = "\n".join(files_list) + ("\n" if files_list else "")
    _, sha = get_gh_file("processed_videos.txt")
    save_gh_file("processed_videos.txt", new_content, "تحديث قائمة المقاطع المعالجة", sha)
    print(f"📝 Tracker updated with {len(files_list)} files: {', '.join(files_list)}")

# ============================================
# MAIN
# ============================================
def get_local_videos():
    video_files = list(VIDEOS_DIR.glob("*.mp4"))
    video_files.sort(key=lambda p: p.name)
    return [f.name for f in video_files]

def extract_filename_from_url(url):
    """استخراج اسم الملف من رابط GitHub الخام"""
    return url.split('/')[-1]

async def main():
    if not TOKEN:
        print("❌ خطأ: TOKEN غير موجود.")
        return

    print("🚀 Starting video processing...")
    print(f"Repository: {REPO}, Branch: {BRANCH}")

    # 1. قائمة الملفات المحلية
    all_videos = get_local_videos()
    if not all_videos:
        print("⚠️ لا توجد مقاطع فيديو في مجلد Videos.")
        return
    print(f"📹 Found {len(all_videos)} videos locally: {', '.join(all_videos[:5])}...")

    # 2. قراءة RSS الحالي
    current_rss_urls = get_current_rss_urls()
    current_filenames_in_rss = {extract_filename_from_url(url) for url in current_rss_urls}
    print(f"📡 Current RSS contains: {current_filenames_in_rss}")

    # 3. حذف الملفات القديمة أولاً (الموجودة محلياً ولكنها ليست في RSS)
    # هذه الملفات هي التي خرجت من RSS في التشغيلات السابقة
    if current_filenames_in_rss:
        old_files_to_delete = [f for f in all_videos if f not in current_filenames_in_rss]
        
        if old_files_to_delete:
            print(f"🗑️ سيتم حذف {len(old_files_to_delete)} مقطع قديم (خارج RSS): {', '.join(old_files_to_delete)}")
            for filename in old_files_to_delete:
                try:
                    # حذف من GitHub
                    _, sha = get_gh_file(f"Videos/{filename}")
                    if sha:
                        delete_gh_file(f"Videos/{filename}", sha, f"حذف قديم {filename}")
                        print(f"🗑️ تم حذف {filename} من GitHub")
                    # حذف محلي
                    local_path = VIDEOS_DIR / filename
                    if local_path.exists():
                        local_path.unlink()
                        print(f"🗑️ تم حذف {filename} من المجلد المحلي")
                except Exception as e:
                    print(f"❌ فشل حذف {filename}: {e}")
            
            # تحديث قائمة الملفات المحلية بعد الحذف
            all_videos = get_local_videos()
        else:
            print("✅ لا توجد ملفات قديمة للحذف")
    else:
        print("📡 RSS فارغ، لا يوجد ملفات قديمة للحذف")

    # 4. الآن معالجة المقاطع الجديدة
    processed = get_processed_videos()
    print(f"📝 Currently tracked: {processed}")
    
    # الملفات المتبقية بعد الحذف
    pending = [v for v in all_videos if v not in processed]
    
    if not pending:
        print("✅ لا توجد مقاطع جديدة للمعالجة")
        # تحديث tracker ليطابق RSS
        if current_filenames_in_rss:
            new_tracker = list(current_filenames_in_rss)
            save_processed_videos(new_tracker)
        return

    # معالجة المقاطع الجديدة
    today_videos = pending[:VIDEOS_PER_DAY]
    print(f"📌 سيتم معالجة {len(today_videos)} مقطع جديد: {', '.join(today_videos)}")

    # إعداد عناصر RSS الجديدة
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

    # تحديث RSS
    print("📡 Updating RSS...")
    updated_items = update_rss(new_rss_items)
    
    # استخراج أسماء الملفات من RSS الجديد
    updated_filenames = []
    for item in updated_items:
        filename = extract_filename_from_url(item['video_url'])
        updated_filenames.append(filename)
    
    # تحديث tracker ليطابق RSS الجديد (آخر 3 مقاطع)
    save_processed_videos(updated_filenames)
    
    print(f"✅ تمت معالجة {len(today_videos)} مقاطع جديدة")
    print(f"📝 Tracker now contains: {updated_filenames}")

if __name__ == "__main__":
    asyncio.run(main())
