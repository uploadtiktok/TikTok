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
os.makedirs(VIDEOS_DIR, exist_ok=True)

MAX_RSS_ITEMS = 15  # عدد العناصر التي سيتم الاحتفاظ بها في الخلاصة
MAX_VIDEOS_CHECK = 20

# ============================================
# GITHUB API FUNCTIONS
# ============================================

def github_api_request(endpoint, method='GET', data=None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/{endpoint}"
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    if method == 'GET':
        response = requests.get(url, headers=headers)
    elif method == 'PUT':
        response = requests.put(url, headers=headers, json=data)
    
    response.raise_for_status()
    return response.json()

def get_file_content(path):
    try:
        response = github_api_request(f"contents/{path}")
        content = base64.b64decode(response['content']).decode('utf-8')
        return content, response['sha']
    except:
        return None, None

def update_file(path, content, commit_msg, sha=None):
    encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    data = {'message': commit_msg, 'content': encoded_content, 'branch': GITHUB_BRANCH}
    if sha: data['sha'] = sha
    try:
        github_api_request(f"contents/{path}", 'PUT', data)
        return True
    except:
        return False

def upload_video(video_path, filename):
    try:
        with open(video_path, 'rb') as f:
            content = base64.b64encode(f.read()).decode('utf-8')
        data = {'message': f'Add video {filename}', 'content': content, 'branch': GITHUB_BRANCH}
        try:
            existing = github_api_request(f"contents/Videos/{filename}")
            data['sha'] = existing['sha']
        except: pass
        github_api_request(f"contents/Videos/{filename}", 'PUT', data)
        return True
    except:
        return False

# ============================================
# UTILITY FUNCTIONS
# ============================================

def get_last_post_number():
    content, _ = get_file_content("lastURL.txt")
    try: return int(content.strip()) if content else 0
    except: return 0

def save_last_post_number(number):
    content = str(number)
    _, sha = get_file_content("lastURL.txt")
    return update_file("lastURL.txt", content, f"Update last post to {number}", sha)

def get_algeria_time():
    tz = pytz.timezone('Africa/Algiers')
    return datetime.now(tz).strftime('%a, %d %b %Y %H:%M:%S +0100')

# ============================================
# RSS LOGIC (FIXED & STRICT)
# ============================================

def get_existing_rss_items():
    """قراءة العناصر الحالية مع تصحيح المسارات بناءً على الدومين"""
    content, _ = get_file_content("rss.xml")
    items = []
    if not content: return items
    
    try:
        root = ET.fromstring(content)
        for item in root.findall('.//item'):
            # جلب القيم الموجودة فعلياً في الملف
            raw_link = item.find('link').text if item.find('link') is not None else ''
            raw_enc = item.find('enclosure').get('url') if item.find('enclosure') is not None else ''
            raw_guid = item.find('guid').text if item.find('guid') is not None else ''
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ''
            title = item.find('title').text if item.find('title') is not None else ''

            # منطق الفرز: التأكد من أن رابط GitHub هو الـ Link ورابط Telegram هو الـ Enclosure
            # حتى لو كان الملف القديم يحتوي على قيم معكوسة، سيتم تصحيحها هنا
            final_github_link = ""
            final_telegram_link = ""

            # فحص الروابط بناءً على المحتوى (github vs t.me)
            all_possible_links = [raw_link, raw_enc, raw_guid]
            for l in all_possible_links:
                if "raw.githubusercontent.com" in l:
                    final_github_link = l
                elif "t.me" in l:
                    final_telegram_link = l

            if final_github_link and final_telegram_link:
                items.append({
                    'title': title,
                    'github_link': final_github_link,
                    'telegram_link': final_telegram_link,
                    'pub_date': pub_date
                })
    except Exception as e:
        print(f"⚠️ Warning parsing RSS: {e}")
    
    return items

def update_rss(title, telegram_post_url, video_filename):
    """إنشاء ملف RSS جديد مع توزيع القيم بدقة"""
    existing_items = get_existing_rss_items()
    
    # بناء رابط GitHub Raw المباشر للفيديو الجديد
    new_github_raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/Videos/{video_filename}"
    
    # العنصر الجديد
    new_item = {
        'title': title,
        'github_link': new_github_raw_url,
        'telegram_link': telegram_post_url,
        'pub_date': get_algeria_time()
    }
    
    existing_items.append(new_item)
    # الحفاظ على ترتيب العناصر (الأحدث في الأسفل أو حسب رغبتك)
    if len(existing_items) > MAX_RSS_ITEMS:
        existing_items.pop(0)

    # بناء هيكل الـ XML
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    
    ET.SubElement(channel, 'title').text = 'مقاطع بجاد الأثري - Shorts'
    ET.SubElement(channel, 'link').text = f'https://github.com/{GITHUB_REPO}'
    ET.SubElement(channel, 'description').text = 'آخر مقاطع الـ Shorts للشيخ محمد بن شمس الدين'
    ET.SubElement(channel, 'language').text = 'ar-sa'
    ET.SubElement(channel, 'lastBuildDate').text = get_algeria_time()
    
    for item in existing_items:
        item_node = ET.SubElement(channel, 'item')
        ET.SubElement(item_node, 'title').text = item['title']
        
        # التوزيع الدقيق للقيم:
        # 1. رابط الـ Link يشير دائماً لـ GitHub
        ET.SubElement(item_node, 'link').text = item['github_link']
        
        ET.SubElement(item_node, 'pubDate').text = item['pub_date']
        
        # 2. رابط الـ Enclosure يشير دائماً لـ Telegram
        ET.SubElement(item_node, 'enclosure', url=item['telegram_link'], type='video/mp4')
        
        # 3. الـ GUID يشير دائماً لـ Telegram (كمعرف فريد ثابت)
        ET.SubElement(item_node, 'guid', isPermaLink='false').text = item['telegram_link']
    
    # تحويل إلى نص ومنسق
    xml_str = minidom.parseString(ET.tostring(rss, encoding='utf-8')).toprettyxml(indent="  ")
    # إزالة الأسطر الفارغة الناتجة عن التنسيق
    rss_content = "\n".join([line for line in xml_str.split('\n') if line.strip()])
    
    _, sha = get_file_content("rss.xml")
    return update_file("rss.xml", rss_content, f"Update RSS: {video_filename}", sha)

# ============================================
# MAIN SCRAPER & PROCESSOR
# ============================================

def fetch_latest_posts(url):
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(response.text, 'html.parser')
    messages = soup.find_all('div', class_='tgme_widget_message_wrap')
    posts = []
    for msg in messages:
        link_tag = msg.find('a', class_='tgme_widget_message_date')
        if not link_tag: continue
        
        full_link = link_tag.get('href')
        if not full_link.startswith('https://'): full_link = 'https://t.me' + full_link
        
        post_id = int(full_link.split('/')[-1])
        video_tag = msg.find('video')
        if not video_tag: continue
        
        text_tag = msg.find('div', class_='tgme_widget_message_text')
        title = text_tag.get_text()[:120] if text_tag else f"فيديو رقم {post_id}"
        
        posts.append({
            'link': full_link,
            'number': post_id,
            'video_url': video_tag.get('src'),
            'title': title
        })
    return posts

async def main():
    print("🚀 Starting Sync Process...")
    if not GITHUB_TOKEN:
        print("❌ Error: GITHUB_TOKEN is missing")
        return

    last_processed = get_last_post_number()
    all_posts = fetch_latest_posts(TELEGRAM_URL)
    
    # جلب المنشورات الجديدة فقط وترتيبها من الأقدم للأحدث
    new_posts = sorted([p for p in all_posts if p['number'] > last_processed], key=lambda x: x['number'])
    
    if not new_posts:
        print("😴 No new videos found.")
        return

    for post in new_posts:
        print(f"📦 Processing: {post['number']}")
        filename = f"{post['number']}.mp4"
        temp_path = os.path.join(VIDEOS_DIR, filename)
        
        # تحميل الملف محلياً
        try:
            r = requests.get(post['video_url'], stream=True)
            with open(temp_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024*1024): f.write(chunk)
            
            # الرفع لـ GitHub
            if upload_video(temp_path, filename):
                # تحديث الخلاصة (GitHub Link في الـ Link، و Telegram في الـ Enclosure)
                if update_rss(post['title'], post['link'], filename):
                    save_last_post_number(post['number'])
                    print(f"✅ Finished: {filename}")
            
            if os.path.exists(temp_path): os.remove(temp_path)
        except Exception as e:
            print(f"❌ Failed to process {post['number']}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
