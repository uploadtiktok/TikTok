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

MAX_RSS_ITEMS = 15 

# ============================================
# GITHUB API
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
    data = {'message': msg, 'content': base64.b64encode(content.encode('utf-8')).decode('utf-8'), 'branch': GITHUB_BRANCH}
    if sha: data['sha'] = sha
    try: github_api_request(f"contents/{path}", 'PUT', data); return True
    except: return False

# ============================================
# RSS LOGIC (العنوان + رابط GitHub فقط)
# ============================================

def get_existing_items():
    """جلب العناصر القديمة مع استخلاص رابط جيت هاب حصراً"""
    content, _ = get_file_content("rss.xml")
    items = []
    if not content: return items
    try:
        root = ET.fromstring(content)
        for item in root.findall('.//item'):
            title = item.find('title').text
            # نبحث عن الرابط الذي يحتوي على github سواء كان في link أو enclosure سابقاً
            link_candidates = [
                item.find('link').text if item.find('link') is not None else '',
                item.find('enclosure').get('url') if item.find('enclosure') is not None else ''
            ]
            
            github_link = next((l for l in link_candidates if "githubusercontent" in l), "")
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
            
            if github_link:
                items.append({'title': title, 'link': github_link, 'pub_date': pub_date})
    except: pass
    return items

def update_rss(title, video_filename):
    items = get_existing_items()
    # إنشاء رابط GitHub Raw المباشر
    github_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/Videos/{video_filename}"
    
    tz = pytz.timezone('Africa/Algiers')
    now = datetime.now(tz).strftime('%a, %d %b %Y %H:%M:%S +0100')

    # إضافة العنصر الجديد
    items.append({'title': title, 'link': github_url, 'pub_date': now})
    if len(items) > MAX_RSS_ITEMS: items.pop(0)

    # بناء الـ XML بالهيكل المختصر المطلوب
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = 'مقاطع بجاد الأثري - Shorts'
    ET.SubElement(channel, 'link').text = f"https://github.com/{GITHUB_REPO}"
    ET.SubElement(channel, 'language').text = 'ar-sa'

    for item in items:
        entry = ET.SubElement(channel, 'item')
        ET.SubElement(entry, 'title').text = item['title']
        ET.SubElement(entry, 'link').text = item['link'] # هنا رابط جيت هاب حصراً
        ET.SubElement(entry, 'pubDate').text = item['pub_date']

    # تحويل النص وتنسيقه
    raw_xml = ET.tostring(rss, encoding='utf-8')
    pretty_xml = minidom.parseString(raw_xml).toprettyxml(indent="  ")
    clean_xml = "\n".join([l for l in pretty_xml.split('\n') if l.strip()])

    _, sha = get_file_content("rss.xml")
    return update_file("rss.xml", clean_xml, f"Add {video_filename}", sha)

# ============================================
# PROCESSOR
# ============================================

async def main():
    if not GITHUB_TOKEN: return
    
    # 1. جلب آخر رقم معالج
    last_content, _ = get_file_content("lastURL.txt")
    last_num = int(last_content.strip()) if last_content else 0

    # 2. جلب منشورات تيليجرام
    res = requests.get(TELEGRAM_URL)
    soup = BeautifulSoup(res.text, 'html.parser')
    posts = []
    for msg in soup.find_all('div', class_='tgme_widget_message_wrap'):
        date_tag = msg.find('a', class_='tgme_widget_message_date')
        if not date_tag: continue
        link = date_tag.get('href')
        num = int(link.split('/')[-1])
        vid = msg.find('video')
        if not vid or num <= last_num: continue
        
        txt = msg.find('div', class_='tgme_widget_message_text')
        posts.append({
            'num': num, 
            'url': vid.get('src'), 
            'title': txt.get_text()[:100] if txt else f"Video {num}"
        })

    # 3. المعالجة والرفع (من الأقدم للأحدث)
    for p in sorted(posts, key=lambda x: x['num']):
        fname = f"{p['num']}.mp4"
        path = os.path.join(VIDEOS_DIR, fname)
        
        # تحميل
        with open(path, 'wb') as f:
            f.write(requests.get(p['url']).content)
            
        # رفع الفيديو
        with open(path, 'rb') as f:
            v_data = base64.b64encode(f.read()).decode('utf-8')
        
        v_sha = None
        try: v_sha = github_api_request(f"contents/Videos/{fname}")['sha']
        except: pass
        
        github_api_request(f"contents/Videos/{fname}", 'PUT', {
            'message': f'Upload {fname}', 'content': v_data, 'sha': v_sha, 'branch': GITHUB_BRANCH
        })

        # تحديث RSS (بناءً على رابط GitHub)
        if update_rss(p['title'], fname):
            _, l_sha = get_file_content("lastURL.txt")
            update_file("lastURL.txt", str(p['num']), f"Update last {p['num']}", l_sha)
            print(f"✅ Processed {fname}")
        
        if os.path.exists(path): os.remove(path)

if __name__ == "__main__":
    asyncio.run(main())
