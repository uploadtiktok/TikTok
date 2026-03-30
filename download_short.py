import os
import subprocess

def download_video(url):
    output_dir = "shorts"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # yt-dlp command with JS Runtime explicit configuration
    command = [
        "yt-dlp",
        "--js-runtime", "node", # إجبار الأداة على استخدام Node.js لفك التشفير
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "--no-check-certificates",
        "--geo-bypass",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "-o", f"{output_dir}/%(title)s.%(ext)s",
        url
    ]

    try:
        print(f"Starting download for: {url}")
        subprocess.run(command, check=True)
        print("Successfully downloaded!")
    except subprocess.CalledProcessError as e:
        print(f"Error occurred: {e}")
        exit(1)

if __name__ == "__main__":
    target_url = "https://youtube.com/shorts/evdWG0GRlfs?si=DmZ9aa5O6CMURlry"
    download_video(target_url)
