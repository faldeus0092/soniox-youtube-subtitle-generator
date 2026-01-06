# YouTube Subtitle Generator for ASBPlayer

This project is used to generate subtitles (SRT files) for YouTube videos or local audio files. Inspired by Mr. Beangate's [repository](https://github.com/bpwhelan/ASB-Auto-Subs/tree/main), creator of GameSentenceMiner. Re-doing his project with additional soniox support for fun. Supports two models: [Soniox](https://soniox.com/) and [Stable-TS](https://github.com/jianfch/stable-ts) (stable-ts will run locally on your system). Takes a youtube url and output an srt file.

From my experience, soniox has better WER but worse timing. Stable-TS has high WER, albeit less than soniox, and more stable timing. Generating subtitle on Stable-TS may be slow depending on your CPU/GPU

## Prerequisites

*   `ffmpeg` installed and accessible in your system's PATH. You can download it from [ffmpeg.org](https://ffmpeg.org/download.html).
*   Soniox API Key

## Installation

Install from source by cloning. Recommended to create a virtual environment.

1. Clone the repository:
   ```bash
   git clone https://github.com/faldeus0092/soniox-youtube-subtitle-generator
   cd soniox-youtube-subtitle-generator
   ```

2. **Create a virtual environment** (optional but recommended):
   - Using `venv`:
     ```bash
     python -m venv venv
     ```
   - Activate the virtual environment:
     - On Windows:
       ```bash
       venv\Scripts\activate
       ```
     - On macOS/Linux:
       ```bash
       source venv/bin/activate
       ```

3. Install the requirements:
   ```bash
   pip install -r requirements.txt
   ```

## Config

You have to create ```.env``` file containing various settings:
```env
SONIOX_API_KEY = <your-api-key-here>
SONIOX_TEMP_KEY_URL="https://soniox.com/api/speech-to-text"
SONIOX_SRT_MIN_DURATION = 1000 #determines minimal duration for each subtitle lines (soniox)
SONIOX_SRT_MAX_DURATION = 3500 #vice versa
SONIOX_SRT_MAX_CHARS = 20 #limit max chars per line to avoid too much text on a single subtitle lines
OUTPUT_DIR = "./output" #output subtitle (.srt) folder
TARGET_LANGUAGE = ja,en #array of target language. Stable-ts only supports one language, so will prioritize first element in array. see https://soniox.com/docs/stt/concepts/supported-languages
```

## Running the Script
run using `app.py [-h] --model {soniox,stable-ts} -u youtube_URL`
```
options:
  -h, --help            show this help message and exit
  --model {soniox,stable-ts}, -m {soniox,stable-ts}
                        Specify the model (choose from soniox, stable-ts)
  -u URL, --url URL     youtube URL
```
example `python start_whisper.py -u https://youtube.com/shorts/RrHW94gVWeQ?si=Kdr2z43nf1WI_mg7 -m stable-ts`