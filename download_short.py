import os
import subprocess

def download_video(url):
    output_dir = "shorts"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    command = [
        "yt-dlp",
        # لا نستخدم بروكسي هنا
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "--no-check-certificates",
        "--geo-bypass",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "-o", f"{output_dir}/%(title)s.%(ext)s",
        url
    ]

    try:
        print(f"Direct download attempt for: {url}")
        subprocess.run(command, check=True)
        print("Success!")
    except subprocess.CalledProcessError:
        print("Download failed again. YouTube is strictly blocking GitHub IP ranges.")
        exit(1)

if __name__ == "__main__":
    download_video("https://youtube.com/shorts/evdWG0GRlfs?si=DmZ9aa5O6CMURlry")
