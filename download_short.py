import os
import subprocess

def download_short(url):
    # Create the target directory
    output_folder = "shorts"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # yt-dlp command with Tor proxy (SOCKS5)
    # The proxy is hosted locally by the Tor service on port 9050
    command = [
        "yt-dlp",
        "--proxy", "socks5://127.0.0.1:9050",
        "-o", f"{output_folder}/%(title)s.%(ext)s",
        url
    ]

    try:
        print(f"Starting download from: {url} via Tor...")
        subprocess.run(command, check=True)
        print("Download completed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    video_url = "https://youtube.com/shorts/evdWG0GRlfs?si=DmZ9aa5O6CMURlry"
    download_short(video_url)
