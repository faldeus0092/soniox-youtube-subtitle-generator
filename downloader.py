from pytubefix import YouTube
from pytubefix.cli import on_progress

def download_yt_from_url(url: str) -> str:
    yt = YouTube(url, on_progress_callback=on_progress)
    print(yt.title)

    ys = yt.streams.get_audio_only()
    ys.download()
    return (f"{yt.title}.m4a")

file = download_yt_from_url("https://youtube.com/shorts/dIpXe4C_tSk?si=hFZr32ZbEovR2LN-")
print(file)