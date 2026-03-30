import os
import subprocess

def download_short(url):
    output_folder = "shorts"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        # Create a hidden .keep file so git recognizes the folder even if empty
        with open(os.path.join(output_folder, ".keep"), "w") as f:
            pass

    command = [
        "yt-dlp",
        "--proxy", "socks5://127.0.0.1:9050",
        "-o", f"{output_folder}/%(title)s.%(ext)s",
        url
    ]

    try:
        print(f"Downloading: {url}")
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print("Download finished.")
        
        # List files to verify
        files = os.listdir(output_folder)
        print(f"Files in {output_folder}: {files}")
        
    except subprocess.CalledProcessError as e:
        print(f"Error: {e.stderr}")
        exit(1)

if __name__ == "__main__":
    video_url = "https://youtube.com/shorts/evdWG0GRlfs?si=DmZ9aa5O6CMURlry"
    download_short(video_url)
