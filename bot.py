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

def clean_title(filename):
    """
    تنظيف عنوان المقطع من الأرقام والعلامات غير المرغوب فيها
    مثال: 72_ما_حكم_من_ينكر_خلافة_علي_بن_أبي_طالب_merged_cleaned.mp4
    يصبح: ما حكم من ينكر خلافة علي بن أبي طالب
    """
    # إزالة الامتداد .mp4
    title = filename.replace('.mp4', '')
    
    # إزالة _merged_cleaned بالكامل (بأي شكل من الأشكال)
    title = re.sub(r'_merged_cleaned$', '', title)
    title = re.sub(r'_merged_cleaned_', '_', title)
    title = re.sub(r'_merged$', '', title)
    title = re.sub(r'_cleaned$', '', title)
    
    # إزالة أي كلمات مكررة مثل _merged أو _cleaned في أي مكان
    title = re.sub(r'_(?:merged|cleaned|final|edit|v\d+)+', '', title)
    
    # إزالة الأرقام في البداية (مثل 72_)
    title = re.sub(r'^\d+_', '', title)
    
    # استبدال الشرطات السفلية المتبقية بمسافات
    title = title.replace('_', ' ')
    
    # إزالة المسافات الزائدة
    title = re.sub(r'\s+', ' ', title).strip()
    
    # إزالة أي كلمة "merged" أو "cleaned" متبقية
    title = re.sub(r'\bmerged\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\bcleaned\b', '', title, flags=re.IGNORECASE)
    
    # إزالة المسافات الزائدة مرة أخرى بعد الحذف
    title = re.sub(r'\s+', ' ', title).strip()
    
    # جعل أول حرف كبير
    if title:
        title = title[0].upper() + title[1:] if len(title) > 1 else title.upper()
    
    return title if title else filename

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
def get_current_rss_filenames():
    """استخراج أسماء الملفات من RSS الحالي"""
    content, _ = get_gh_file("rss.xml")
    if not content:
        return []
    
    filenames = []
    try:
        root = ET.fromstring(content)
        for item in root.findall('.//item'):
            link = item.find('link').text if item.find('link') is not None else ""
            enc_node = item.find('enclosure')
            enc_url = enc_node.get('url') if enc_node is not None else ""
            video_url = link if link else enc_url
            if video_url:
                filename = video_url.split('/')[-1]
                filenames.append(filename)
    except Exception as e:
        print(f"⚠️ Error parsing RSS: {e}")
    
    return filenames

def create_empty_rss():
    """إنشاء ملف RSS فارغ (بدون عناصر)"""
    # بناء XML فارغ
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = 'مقاطع الفيديو - Shorts'
    ET.SubElement(channel, 'link').text = f"https://github.com/{REPO}"
    ET.SubElement(channel, 'language').text = 'ar-sa'
    ET.SubElement(channel, 'lastBuildDate').text = datetime.now(pytz.timezone('Africa/Algiers')).strftime('%a, %d %b %Y %H:%M:%S +0100')
    ET.SubElement(channel, 'description').text = 'لا توجد مقاطع حالياً'

    xml_str = ET.tostring(rss, encoding='utf-8')
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent="  ")
    clean_xml = "\n".join(line for line in pretty_xml.split('\n') if line.strip())

    _, sha = get_gh_file("rss.xml")
    save_gh_file("rss.xml", clean_xml, "إفراغ RSS (لا توجد مقاطع)", sha)
    print("✅ RSS emptied (no videos available)")

def create_new_rss(videos_to_add):
    """إنشاء ملف RSS جديد يحتوي على المقاطع المحددة مع عناوين نظيفة"""
    items = []
    for filename in videos_to_add:
        # تنظيف العنوان
        clean_title_text = clean_title(filename)
        raw_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/Videos/{filename}"
        pub_date = datetime.now(pytz.timezone('Africa/Algiers')).strftime('%a, %d %b %Y %H:%M:%S +0100')
        items.append({
            'title': clean_title_text,
            'video_url': raw_url,
            'pub_date': pub_date,
            'original_filename': filename
        })

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
    save_gh_file("rss.xml", clean_xml, f"تحديث RSS - {len(videos_to_add)} مقاطع", sha)
    print(f"✅ RSS created/updated with {len(videos_to_add)} items")
    
    # عرض العناوين النظيفة للتوضيح
    print("   تنظيف العناوين:")
    for item in items:
        print(f"      📝 {item['original_filename']}")
        print(f"         → {item['title']}")

# ============================================
# MAIN
# ============================================
async def main():
    if not TOKEN:
        print("❌ خطأ: TOKEN غير موجود.")
        return

    print("🚀 Starting video processing...")
    print(f"Repository: {REPO}, Branch: {BRANCH}")

    # 1. جلب قائمة الفيديوهات من المستودع
    all_videos = list_videos_in_repo()
    if not all_videos:
        print("⚠️ لا توجد مقاطع فيديو في مجلد Videos.")
        # إذا كان المجلد فارغاً، قم بإفراغ RSS
        create_empty_rss()
        return
    print(f"📹 Found {len(all_videos)} videos in repo")

    # 2. قراءة RSS الحالي
    current_rss_filenames = get_current_rss_filenames()
    print(f"📡 Current RSS contains: {len(current_rss_filenames)} items")

    # 3. حذف المقاطع الموجودة في RSS من مجلد Videos
    deleted_count = 0
    if current_rss_filenames:
        to_delete = [f for f in current_rss_filenames if f in all_videos]
        
        if to_delete:
            print(f"🗑️ سيتم حذف {len(to_delete)} مقطع من مجلد Videos (الموجودة في RSS):")
            for filename in to_delete:
                try:
                    file_info = gh_api(f"contents/Videos/{filename}")
                    if file_info and 'sha' in file_info:
                        delete_gh_file(f"Videos/{filename}", file_info['sha'], f"حذف {filename} (خرج من RSS)")
                        print(f"   🗑️ تم حذف {filename}")
                        deleted_count += 1
                except Exception as e:
                    print(f"   ❌ فشل حذف {filename}: {e}")
            
            # تحديث قائمة الفيديوهات بعد الحذف
            all_videos = list_videos_in_repo()
            print(f"📹 Updated: {len(all_videos)} videos remaining")
        else:
            print("✅ لا توجد مقاطع في RSS للحذف")
    else:
        print("📡 RSS غير موجود أو فارغ")

    # 4. إضافة مقاطع جديدة إلى RSS (أول 3 مقاطع متبقية)
    added_count = 0
    if all_videos:
        videos_to_add = all_videos[:VIDEOS_PER_DAY]
        print(f"\n📌 سيتم إضافة {len(videos_to_add)} مقاطع جديدة إلى RSS")
        create_new_rss(videos_to_add)
        added_count = len(videos_to_add)
    else:
        # إذا لم يتبق أي مقاطع، قم بإفراغ RSS
        print("\n📡 لا توجد مقاطع متبقية، سيتم إفراغ RSS")
        create_empty_rss()

    # 5. إحصائيات نهائية
    remaining_videos = list_videos_in_repo()
    print(f"\n📊 ملخص:")
    print(f"   - مقاطع تم حذفها من المجلد: {deleted_count}")
    print(f"   - مقاطع تمت إضافتها إلى RSS: {added_count}")
    print(f"   - المقاطع المتبقية في مجلد Videos: {len(remaining_videos)}")

    if remaining_videos:
        print(f"   - المقاطع المتبقية: {', '.join(remaining_videos[:5])}...")
    else:
        print("   🎉 جميع المقاطع تمت معالجتها! RSS فارغ.")

if __name__ == "__main__":
    asyncio.run(main())
