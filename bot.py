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
# الإعدادات الأساسية
# ============================================
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'uploadtiktok/TikTok')
GITHUB_BRANCH = os.environ.get('GITHUB_BRANCH', 'main')

TELEGRAM_URL = "https://t.me/s/zapiershorts"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEOS_DIR = os.path.join(BASE_DIR, "Videos")
os.makedirs(VIDEOS_DIR, exist_ok=True)

MAX_RSS_ITEMS = 15

# ============================================
# دوال GitHub API
# ============================================
def github_api_request(endpoint, method='GET', data=None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/{endpoint}"
    headers = {'Authorization': f'token {GITHUB_TOKEN}', 'Accept': 'application/vnd.github.v3+json'}
    if method == 'GET': response = requests.get(url, headers=headers)
    elif method == 'PUT': response = requests.put(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()

def get_file_content(path):
    try:
        res = github_api_request(f"contents/{path}")
        return base64.b64decode(res['content']).decode('utf-8'), res['sha']
    except: return None, None

def update_file(path, content, msg, sha=None):
    encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    data = {'message': msg, 'content': encoded, 'branch': GITHUB_BRANCH}
    if sha: data['sha'] = sha
    try: github_api_request(f"contents/{path}", 'PUT', data); return True
    except: return False

# ============================================
# منطق الـ RSS الصارم (GitHub Link Only)
# ============================================
def get_existing_items():
    """قراءة العناصر السابقة واستخراج رابط GitHub فقط"""
    content, _ = get_file_content("rss.xml")
    items = []
    if not content: return items
    try:
        root = ET.fromstring(content)
        for item in root.findall('.//item'):
            title = item.find('title').text if item.find('title') is not None else "Video"
            
            # هنا يكمن الحل: نبحث في كل الوسوم عن الرابط الذي يحتوي على githubusercontent
            # لضمان عدم سحب رابط تيليجرام بالخطأ من الملف القديم
            raw_github_url = ""
            candidates = [
                item.find('link').text if item.find('link') is not None else "",
                item.find('enclosure').get('url') if item.find('enclosure') is not None else "" if item.find('enclosure') is not None else ""
            ]
            for c in candidates:
                if "githubusercontent" in c:
                    raw_github_url = c
                    break
            
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
            
            if raw_github_url: # لا نضيف العنصر إلا إذا وجدنا رابط جيت هاب
                items.append({'title': title, 'link': raw_github_url, 'pub_date': pub_date})
    except: pass
    return items

def update_rss(title, video_filename):
    """توليد ملف RSS بهيكل نظيف جداً"""
    items = get_existing_items()
    
    # بناء رابط GitHub المباشر (Raw)
    github_raw_link = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/Videos/{video_filename}"
    
    tz = pytz.timezone('Africa/Algiers')
    now = datetime.now(tz).strftime('%a, %d %b %Y %H:%M:%S +0100')

    # إضافة العنصر الجديد مع رابط GitHub حصراً
    items.append({'title': title, 'link': github_raw_link, 'pub_date': now})
    
    # حذف العناصر القديمة الزائدة
    if len(items) > MAX_RSS_ITEMS: items.pop(0)

    # بناء XML من الصفر بهيكل بسيط جداً
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = 'مقاطع بجاد الأثري - Shorts'
    ET.SubElement(channel, 'link').text = f"https://github.com/{GITHUB_REPO}"
    ET.SubElement(channel, 'description').text = 'آخر مقاطع الـ Shorts'
    ET.SubElement(channel, 'language').text = 'ar-sa'

    for item in items:
        entry = ET.SubElement(channel, 'item')
        ET.SubElement(entry, 'title').text = item['title']
        ET.SubElement(entry, 'link').text = item['link'] # الرابط هو GitHub حصراً
        ET.SubElement(entry, 'pubDate').text = item['pub_date']
        # ملاحظة: تم حذف enclosure و guid تماماً بناءً على طلبك

    # تحويل إلى نص منسق
    xml_data = ET.tostring(rss, encoding='utf-8')
    pretty_xml = minidom.parseString(xml_data).toprettyxml(indent="  ")
    # تنظيف الأسطر الفارغة
    final_rss = "\n".join([line for line in pretty_xml.split('\n') if line.strip()])

    _, sha = get_file_content("rss.xml")
    return update_file("rss.xml", final_rss, f"New Video: {video_filename}", sha)

# ============================================
# المعالجة الرئيسية
# ============================================
async def main():
    if not GITHUB_TOKEN: 
        print("❌ Token Missing"); return

    # جلب آخر رقم معالج من ملف النص
    last_content, _ = get_file_content("lastURL.txt")
    last_processed_num = int(last_content.strip()) if last_content else 0

    # جلب المنشورات من تيليجرام
    res = requests.get(TELEGRAM_URL, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    
    new_posts = []
    for msg in soup.find_all('div', class_='tgme_widget_message_wrap'):
        date_link = msg.find('a', class_='tgme_widget_message_date')
        if not date_link: continue
        
        post_url = date_link.get('href')
        post_num = int(post_url.split('/')[-1])
        
        video_tag = msg.find('video')
        if not video_tag or post_num <= last_processed_num: continue
        
        text_tag = msg.find('div', class_='tgme_widget_message_text')
        title = text_tag.get_text()[:100] if text_tag else f"فيديو رقم {post_num}"
        
        new_posts.append({'num': post_num, 'vid_url': video_tag.get('src'), 'title': title})

    # معالجة المنشورات الجديدة (من الأقدم للأحدث)
    for p in sorted(new_posts, key=lambda x: x['num']):
        filename = f"{p['num']}.mp4"
        local_path = os.path.join(VIDEOS_DIR, filename)
        
        # 1. تحميل الفيديو
        with open(local_path, 'wb') as f:
            f.write(requests.get(p['vid_url']).content)
            
        # 2. رفع الفيديو إلى GitHub
        with open(local_path, 'rb') as f:
            content_encoded = base64.b64encode(f.read()).decode('utf-8')
        
        v_sha = None
        try: v_sha = github_api_request(f"contents/Videos/{filename}")['sha']
        except: pass
        
        github_api_request(f"contents/Videos/{filename}", 'PUT', {
            'message': f'Upload Video {p["num"]}', 
            'content': content_encoded, 
            'sha': v_sha, 
            'branch': GITHUB_BRANCH
        })

        # 3. تحديث ملف الـ RSS (هنا يتم وضع رابط GitHub في خانة link)
        if update_rss(p['title'], filename):
            # 4. تحديث رقم آخر منشور
            _, l_sha = get_file_content("lastURL.txt")
            update_file("lastURL.txt", str(p['num']), f"Update last processed to {p['num']}", l_sha)
            print(f"✅ Successfully processed video #{p['num']}")
        
        if os.path.exists(local_path): os.remove(local_path)

if __name__ == "__main__":
    asyncio.run(main())
