#!/usr/bin/env python3
import asyncio
import os
import json
from pathlib import Path
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession

# ========== CONFIGURATION ==========
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
STRING_SESSION = os.environ.get("STRING_SESSION", "")
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "zapiershorts")

batch_size_str = os.environ.get("BATCH_SIZE", "3")
try:
    BATCH_SIZE = int(batch_size_str) if batch_size_str.strip() else 3
except ValueError:
    BATCH_SIZE = 3

VIDEO_FOLDER = "Videos"
INDEX_FILE = "last_index.json"          # بدلاً من last_message_id
# ====================================

def setup_folders():
    Path(VIDEO_FOLDER).mkdir(parents=True, exist_ok=True)

def load_last_index():
    """تحميل آخر مؤشر تم تحميله (index في القائمة من الأقدم للأحدث)"""
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE) as f:
            data = json.load(f)
            return data.get("last_index", -1)
    return -1   # -1 يعني لم يسبق تحميل أي شيء

def save_last_index(index):
    with open(INDEX_FILE, "w") as f:
        json.dump({"last_index": index}, f)

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

async def fetch_videos():
    print("🎬 Telegram Video Fetcher (Index-based)")
    print(f"📦 Batch size: {BATCH_SIZE}")
    print("-" * 40)

    if not (API_ID and API_HASH and STRING_SESSION and CHANNEL_USERNAME):
        print("❌ Missing secrets")
        return

    setup_folders()
    last_idx = load_last_index()
    print(f"📍 Last downloaded index: {last_idx} ({'no downloads yet' if last_idx == -1 else 'next index = ' + str(last_idx+1)})")

    client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
    try:
        await client.start()
        print("✅ Connected")

        channel = await client.get_entity(CHANNEL_USERNAME)
        print(f"📢 Channel: {channel.title}")

        # جلب جميع مقاطع الفيديو من الأقدم إلى الأحدث
        print("🔍 Fetching video messages (oldest → newest)...")
        all_videos = []
        async for msg in client.iter_messages(channel, reverse=True):
            if msg.video or (msg.document and is_video_file(msg.document)):
                all_videos.append(msg)

        total = len(all_videos)
        print(f"🎬 Total videos in channel: {total}")

        if total == 0:
            print("📭 No videos found.")
            return

        # تحديد المقاطع الجديدة بناءً على آخر مؤشر
        start = last_idx + 1
        if start >= total:
            print("📭 No new videos to download (all videos have been downloaded).")
            return

        end = min(start + BATCH_SIZE, total)
        videos_to_download = all_videos[start:end]

        print(f"📥 Downloading {len(videos_to_download)} new video(s) (positions {start+1} to {end})...")
        print("-" * 40)

        downloaded_count = 0
        new_last_idx = last_idx

        for i, msg in enumerate(videos_to_download, 1):
            original_name = get_file_name(msg.document) if msg.document else f"video_{msg.id}.mp4"
            if not original_name:
                original_name = f"video_{msg.id}.mp4"

            timestamp = msg.date.strftime("%Y%m%d_%H%M%S")
            safe_name = f"{msg.id}_{timestamp}_{original_name}"
            safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._- ")
            file_path = Path(VIDEO_FOLDER) / safe_name

            print(f"📥 ({i}/{len(videos_to_download)}) Downloading: {original_name} (ID: {msg.id})")
            try:
                if msg.video:
                    await client.download_media(msg.video, str(file_path))
                else:
                    await client.download_media(msg.document, str(file_path))

                if file_path.exists() and file_path.stat().st_size > 0:
                    size_mb = file_path.stat().st_size / (1024 * 1024)
                    print(f"✅ Downloaded: {original_name} ({size_mb:.2f} MB)")
                    downloaded_count += 1
                    # تحديث آخر مؤشر ناجح
                    new_last_idx = start + i - 1
                else:
                    print(f"❌ Download failed: {original_name}")
                    if file_path.exists():
                        file_path.unlink()
                    break  # توقف عن التحميل إذا فشل أحدها
            except Exception as e:
                print(f"⚠️ Error downloading {original_name}: {e}")
                break

        if downloaded_count > 0:
            save_last_index(new_last_idx)
            print(f"📍 Updated last index to: {new_last_idx}")

        print("\n" + "="*50)
        print(f"📈 SUMMARY:")
        print(f"   ✅ Downloaded: {downloaded_count}")
        print(f"   📁 New videos added to '{VIDEO_FOLDER}/'")
        print(f"   📍 Last index: {load_last_index()} (total downloaded: {load_last_index()+1})")
        print("="*50)

    except Exception as e:
        print(f"❌ Error: {e}")
        raise
    finally:
        await client.disconnect()
        print("👋 Disconnected")

if __name__ == "__main__":
    asyncio.run(fetch_videos())
