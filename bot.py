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

# ============================================
# TRACKER - يحتوي فقط على آخر 3 مقاطع
# ============================================
def get_processed_videos():
    """قراءة آخر 3 مقاطع تمت معالجتها"""
    content, _ = get_gh_file("processed_videos.txt")
    if content:
        return [line.strip() for line in content.splitlines() if line.strip()]
    return []

def update_processed_videos(new_files):
    """تحديث tracker ليحتوي فقط على آخر 3 مقاطع"""
    existing = get_processed_videos()
    
    # إضافة الملفات الجديدة
    all_files = existing + new_files
    
    # الاحتفاظ بآخر 3 فقط (الأحدث)
    if len(all_files) > MAX_ITEMS:
        all_files = all_files[-MAX_ITEMS:]
    
    new_content = "\n".join(all_files) + ("\n" if all_files else "")
    _, sha = get_gh_file("processed_videos.txt")
    save_gh_file("processed_videos.txt", new_content, "تحديث قائمة المقاطع المعالجة", sha)
    print(f"📝 Tracker updated with {len(all_files)} files: {', '.join(all_files)}")

def remove_from_processed_videos(files_to_remove):
    """إزالة ملفات معينة من tracker"""
    existing = get_processed_videos()
    remaining = [f for f in existing if f not in files_to_remove]
    new_content = "\n".join(remaining) + ("\n" if remaining else "")
    _, sha = get_gh_file("processed_videos.txt")
    save_gh_file("processed_videos.txt", new_content, "إزالة المقاطع القديمة من tracker", sha)
    print(f"📝 Removed from tracker: {', '.join(files_to_remove)}")

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
    print(f"📹 Found {len(all_videos)} videos locally.")

    # 2. المقاطع التي تمت معالجتها (آخر 3)
    processed = get_processed_videos()
    print(f"📝 Currently tracked (last {MAX_ITEMS}): {processed}")

    # 3. تحديد المقاطع الجديدة (غير الموجودة في tracker)
    pending = [v for v in all_videos if v not in processed]
    
    if not pending:
        print("✅ لا توجد مقاطع جديدة للمعالجة.")
    else:
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
        update_rss(new_rss_items)

        # تحديث tracker (يضيف الجديد ويحتفظ بآخر 3 فقط)
        update_processed_videos(today_videos)

    # 4. بعد تحديث RSS، تحديد وحذف الملفات التي خرجت من RSS
    current_rss_urls = get_current_rss_urls()
    current_filenames_in_rss = {extract_filename_from_url(url) for url in current_rss_urls}
    print(f"📡 Current RSS contains: {current_filenames_in_rss}")

    # الملفات التي يجب حذفها = الملفات الموجودة محلياً والموجودة في tracker
    # ولكنها ليست في RSS الجديد
    processed_set = set(get_processed_videos())
    to_delete = [f for f in all_videos if f in processed_set and f not in current_filenames_in_rss]

    if to_delete:
        print(f"🗑️ سيتم حذف {len(to_delete)} مقطع قديم: {', '.join(to_delete)}")
        for filename in to_delete:
            try:
                # حذف من GitHub
                _, sha = get_gh_file(f"Videos/{filename}")
                if sha:
                    delete_gh_file(f"Videos/{filename}", sha, f"حذف قديم {filename}")
                # حذف محلي
                local_path = VIDEOS_DIR / filename
                if local_path.exists():
                    local_path.unlink()
                print(f"🗑️ تم حذف {filename}")
            except Exception as e:
                print(f"❌ فشل حذف {filename}: {e}")
        
        # إزالة الملفات المحذوفة من tracker
        remove_from_processed_videos(to_delete)
    else:
        print("✅ لا توجد ملفات قديمة للحذف.")

    # إحصائيات نهائية
    remaining = len([v for v in all_videos if v not in set(get_processed_videos())])
    print(f"📊 المتبقي من المقاطع غير المعالجة: {remaining}")
    print(f"📝 Tracker now contains: {get_processed_videos()}")

if __name__ == "__main__":
    asyncio.run(main())
