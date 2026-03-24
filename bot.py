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
TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO = os.environ.get('GITHUB_REPO', 'uploadtiktok/TikTok')
BRANCH = os.environ.get('GITHUB_BRANCH', 'main')

TELEGRAM_URL = "https://t.me/s/zapiershorts"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEOS_DIR = os.path.join(BASE_DIR, "Videos")
os.makedirs(VIDEOS_DIR, exist_ok=True)

MAX_ITEMS = 15

# ============================================
# GITHUB API FUNCTIONS
# ============================================
def gh_api(endpoint, method='GET', data=None):
    url = f"https://api.github.com/repos/{REPO}/{endpoint}"
    headers = {
        'Authorization': f'token {TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    if method == 'GET':
        r = requests.get(url, headers=headers)
    else:
        r = requests.put(url, headers=headers, json=data)
    r.raise_for_status()
    return r.json()

def get_gh_file(path):
    try:
        res = gh_api(f"contents/{path}")
        content = base64.b64decode(res['content']).decode('utf-8')
        return content, res['sha']
    except:
        return None, None

def save_gh_file(path, content, msg, sha=None):
    encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    data = {'message': msg, 'content': encoded, 'branch': BRANCH}
    if sha:
        data['sha'] = sha
    return gh_api(f"contents/{path}", 'PUT', data)

# ============================================
# RSS LOGIC (FIXED & FULL STRUCTURE)
# ============================================
def update_rss_full(title, telegram_link, video_filename):
    """تحديث ملف RSS مع توزيع الروابط بدقة: جيت هاب للرابط وتيليجرام للمرفقات"""
    old_content, _ = get_gh_file("rss.xml")
    items = []
    
    if old_content:
        try:
            root = ET.fromstring(old_content)
            for item in root.findall('.//item'):
                c_link = item.find('link').text if item.find('link') is not None else ""
                enc_node = item.find('enclosure')
                c_enc = enc_node.get('url') if enc_node is not None else ""
                
                # فرز الروابط لاسترجاع البيانات القديمة بشكل صحيح
                g_link = c_link if "githubusercontent" in c_link else c_enc
                t_link = c_enc if "t.me" in c_enc else c_link
                
                if g_link:  # نضمن وجود رابط جيت هاب على الأقل
                    items.append({
                        'title': item.find('title').text,
                        'github_url': g_link,
                        'telegram_url': t_link,
                        'pub_date': item.find('pubDate').text if item.find('pubDate') is not None else ""
                    })
        except:
            pass

    # إنشاء رابط GitHub Raw المباشر للفيديو الجديد
    new_github_raw_url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/Videos/{video_filename}"
    
    # إضافة العنصر الجديد مع التأكد من استخدام المتغير الصحيح
    items.append({
        'title': title,
        'github_url': new_github_raw_url,
        'telegram_url': telegram_link,
        'pub_date': datetime.now(pytz.timezone('Africa/Algiers')).strftime('%a, %d %b %Y %H:%M:%S +0100')
    })
    
    if len(items) > MAX_ITEMS:
        items.pop(0)

    # بناء الهيكل النهائي للـ XML
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = 'مقاطع بجاد الأثري - Shorts'
    ET.SubElement(channel, 'link').text = f"https://github.com/{REPO}"
    ET.SubElement(channel, 'language').text = 'ar-sa'

    for i in items:
        node = ET.SubElement(channel, 'item')
        ET.SubElement(node, 'title').text = i['title']
        ET.SubElement(node, 'link').text = i['github_url']  # الرابط المباشر
        ET.SubElement(node, 'pubDate').text = i['pub_date']
        ET.SubElement(node, 'enclosure', url=i['telegram_url'], type='video/mp4') # تيليجرام
        ET.SubElement(node, 'guid', isPermaLink='false').text = i['telegram_url'] # تيليجرام

    # تنسيق الـ XML
    xml_out = minidom.parseString(ET.tostring(rss, encoding='utf-8')).toprettyxml(indent="  ")
    final_xml = "\n".join([line for line in xml_out.split('\n') if line.strip()])
    
    _, sha = get_gh_file("rss.xml")
    save_gh_file("rss.xml", final_xml, f"Add {video_filename}", sha)

# ============================================
# MAIN EXECUTION
# ============================================
async def main():
    if not TOKEN:
        print("❌ Error: GITHUB_TOKEN is missing"); return
    
    # جلب آخر رقم معالج
    last_val, _ = get_gh_file("lastURL.txt")
    last_id = int(last_val.strip()) if last_val else 0

    # سحب بيانات تيليجرام
    try:
        r = requests.get(TELEGRAM_URL, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(r.text, 'html.parser')
    except Exception as e:
        print(f"❌ Scraper error: {e}"); return

    new_posts = []
    for msg in soup.find_all('div', class_='tgme_widget_message_wrap'):
        a_tag = msg.find('a', class_='tgme_widget_message_date')
        if not a_tag: continue
        
        post_link = a_tag.get('href')
        num = int(post_link.split('/')[-1])
        vid = msg.find('video')
        
        if vid and num > last_id:
            txt = msg.find('div', class_='tgme_widget_message_text')
            new_posts.append({
                'id': num, 
                'v_src': vid.get('src'), 
                't_link': post_link,
                'title': txt.get_text()[:100] if txt else f"Video {num}"
            })

    # معالجة الفيديوهات
    for p in sorted(new_posts, key=lambda x: x['id']):
        fname = f"{p['id']}.mp4"
        fpath = os.path.join(VIDEOS_DIR, fname)
        
        print(f"🎬 Processing Video #{p['id']}...")
        
        # تحميل محلي مؤقت
        with open(fpath, 'wb') as f:
            f.write(requests.get(p['v_src']).content)
        
        # رفع الفيديو لـ GitHub
        with open(fpath, 'rb') as f:
            v_encoded = base64.b64encode(f.read()).decode('utf-8')
        
        v_sha = None
        try:
            v_sha = gh_api(f"contents/Videos/{fname}")['sha']
        except:
            pass
        
        gh_api(f"contents/Videos/{fname}", 'PUT', {
            'message': f'Upload Vid {p["id"]}', 
            'content': v_encoded, 
            'sha': v_sha, 
            'branch': BRANCH
        })

        # تحديث RSS
        update_rss_full(p['title'], p['t_link'], fname)
        
        # تحديث رقم التعقب
        _, l_sha = get_gh_file("lastURL.txt")
        save_gh_file("lastURL.txt", str(p['id']), f"Update last to {p['id']}", l_sha)
        
        if os.path.exists(fpath):
            os.remove(fpath)
            
        print(f"✅ Successfully finished video {p['id']}")

if __name__ == "__main__":
    asyncio.run(main())
