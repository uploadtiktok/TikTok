import asyncio
import os
import base64
import requests
from xml.dom import minidom
from xml.etree import ElementTree as ET
from datetime import datetime
import pytz
import re

# ============================================
# CONFIGURATION
# ============================================
TOKEN = os.environ.get('GITHUB_TOKEN', os.environ.get('PAT_TOKEN', ''))
REPO = os.environ.get('GITHUB_REPO', 'uploadtiktok/TikTok')
BRANCH = os.environ.get('GITHUB_BRANCH', 'main')

MAX_ITEMS = 3
VIDEOS_PER_DAY = 3

# ============================================
# HELPER FUNCTIONS
# ============================================
def extract_number(filename):
    """استخراج الرقم من اسم الملف إذا كان موجوداً"""
    match = re.search(r'(\d+)', filename)
    if match:
        return int(match.group(1))
    return float('inf')

def get_numeric_value(filename):
    """استخراج القيمة الرقمية للمقارنة"""
    try:
        return int(filename.split('.')[0])
    except:
        return extract_number(filename)

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
        if 'r' in locals():
            print(f"Response: {r.text}")
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
    data = {'message': msg, 'sha': sha, 'branch': BRANCH}
    return gh_api(f"contents/{path}", 'DELETE', data)

def list_videos_in_repo():
    """جلب قائمة جميع ملفات الفيديو من مجلد Videos في المستودع وترتيبها تصاعدياً"""
    try:
        res = gh_api("contents/Videos")
        if not res:
            return []
        # تصفية ملفات mp4 فقط
        videos = [item['name'] for item in res if item['name'].endswith('.mp4')]
        
        # ترتيب آمن: استخراج الأرقام من الأسماء
        try:
            videos.sort(key=lambda x: (extract_number(x), x))
        except Exception as e:
            print(f"⚠️ Sorting error: {e}, using simple sort")
            videos.sort()
        
        return videos
    except Exception as e:
        print(f"❌ Failed to list videos: {e}")
        return []

# ============================================
# RSS FUNCTIONS
# ============================================
def get_current_rss_items():
    """استخراج عناصر RSS الحالية (القائمة كاملة)"""
    content, _ = get_gh_file("rss.xml")
    if not content:
        return []
    items = []
    try:
        root = ET.fromstring(content)
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
    return items

def update_rss(new_items):
    """إضافة عناصر جديدة إلى RSS والاحتفاظ بآخر 3 عناصر"""
    items = get_current_rss_items()
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
    return items

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
def extract_filename_from_url(url):
    """استخراج اسم الملف من رابط GitHub الخام"""
    return url.split('/')[-1]

async def main():
    if not TOKEN:
        print("❌ خطأ: TOKEN غير موجود.")
        return

    print("🚀 Starting video processing...")
    print(f"Repository: {REPO}, Branch: {BRANCH}")

    # 1. جلب قائمة الفيديوهات من المستودع عبر API
    all_videos = list_videos_in_repo()
    if not all_videos:
        print("⚠️ لا توجد مقاطع فيديو في مجلد Videos.")
        return
    print(f"📹 Found {len(all_videos)} videos in repo: {', '.join(all_videos[:10])}...")

    # 2. قراءة RSS الحالي
    current_rss_items = get_current_rss_items()
    current_filenames_in_rss = {extract_filename_from_url(item['video_url']) for item in current_rss_items}
    print(f"📡 Current RSS contains: {current_filenames_in_rss}")

    # 3. حذف المقاطع القديمة (التي هي أقدم من أقدم مقطع في RSS)
    deleted_files = []
    if current_filenames_in_rss:
        # ترتيب المقاطع في RSS حسب الرقم
        rss_files_sorted = sorted(list(current_filenames_in_rss), key=get_numeric_value)
        oldest_in_rss = rss_files_sorted[0] if rss_files_sorted else None
        
        if oldest_in_rss:
            oldest_num = get_numeric_value(oldest_in_rss)
            # نحذف فقط المقاطع الأصغر من أقدم مقطع في RSS
            to_delete = []
            for video in all_videos:
                video_num = get_numeric_value(video)
                if video_num < oldest_num:
                    to_delete.append(video)
                else:
                    break
            
            if to_delete:
                print(f"🗑️ سيتم حذف {len(to_delete)} مقطع قديم (أقدم من {oldest_in_rss}): {', '.join(to_delete)}")
                for filename in to_delete:
                    try:
                        # الحصول على sha للملف
                        file_info = gh_api(f"contents/Videos/{filename}")
                        if file_info and 'sha' in file_info:
                            delete_gh_file(f"Videos/{filename}", file_info['sha'], f"حذف قديم {filename}")
                            print(f"🗑️ تم حذف {filename} من المستودع")
                            deleted_files.append(filename)
                        else:
                            print(f"⚠️ لم يتم العثور على {filename} في المستودع")
                    except Exception as e:
                        print(f"❌ فشل حذف {filename}: {e}")
                
                # تحديث قائمة الفيديوهات بعد الحذف
                if deleted_files:
                    all_videos = list_videos_in_repo()
                    print(f"📹 Updated video list: {len(all_videos)} videos remaining")
            else:
                print("✅ لا توجد ملفات قديمة للحذف")
        else:
            print("✅ لا توجد ملفات قديمة للحذف")
    else:
        print("📡 RSS فارغ، لا يوجد ملفات قديمة للحذف")

    # 4. معالجة المقاطع الجديدة (من الأقدم)
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

    # معالجة المقاطع الجديدة (أول 3 من القائمة المتبقية)
    today_videos = pending[:VIDEOS_PER_DAY]
    print(f"📌 سيتم معالجة {len(today_videos)} مقطع جديد (الأقدم): {', '.join(today_videos)}")

    # إعداد عناصر RSS الجديدة
    new_rss_items = []
    for filename in today_videos:
        title = filename.split('.')[0]  # اسم الملف بدون امتداد
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
    print(f"🗑️ Total deleted files in this run: {len(deleted_files)}")

if __name__ == "__main__":
    asyncio.run(main())
