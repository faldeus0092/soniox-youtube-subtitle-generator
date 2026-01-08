import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional
from soniox_utils import soniox_to_srt
import time
import argparse

import requests
import yt_dlp
import torch
from dotenv import load_dotenv

load_dotenv()

SONIOX_API_BASE_URL = "https://api.soniox.com"
SONIOX_TEMP_KEY_URL = os.getenv("SONIOX_TEMP_KEY_URL")
SONIOX_SRT_MIN_DURATION = int(os.getenv("SONIOX_SRT_MIN_DURATION", 1000))
SONIOX_SRT_MAX_DURATION = int(os.getenv("SONIOX_SRT_MAX_DURATION", 3500))
SONIOX_MAX_CHARS = int(os.getenv("SONIOX_MAX_CHARS", 20))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
TARGET_LANGUAGE = os.getenv("TARGET_LANGUAGE").split(",")

class SonioxProcessor:
    """
    Processor to run transcription via soniox api and return srt format directly
    """
    def __init__(self) -> None:
        self.session = requests.Session()
        self.api_key = self.get_api_key()
        self.session.headers["Authorization"] = f"Bearer {self.api_key}"
    
    def get_api_key(self) -> str:
        """
        获取API Key
        1. 先尝试从环境变量 SONIOX_API_KEY 加载
        2. 如果没有，则请求临时key
        """
        # 尝试从环境变量获取
        api_key = os.environ.get("SONIOX_API_KEY")
        
        if api_key:
            print(f"✅ Using API Key from environment variable")
            return api_key
        
        # 如果没有，获取临时key
        print("⏳ API Key not found in environment, fetching temporary key...")
        try:
            response = requests.post(SONIOX_TEMP_KEY_URL, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            temp_key = data.get("apiKey")
            expires_at = data.get("expiresAt")
            
            if temp_key:
                print(f"✅ Successfully obtained temporary API Key")
                print(f"   Key: {temp_key}")
                print(f"   Expires at: {expires_at}")
                return temp_key
            else:
                raise RuntimeError("Invalid temporary key response format")
                
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to fetch temporary API Key: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to parse temporary API Key: {e}")
    
    def get_config(
        self, audio_url: Optional[str], file_id: Optional[str], translation: Optional[str]
    ) -> dict:
        config ={
            "model":"stt-async-v3",
            "file_id":file_id,
            "language_hints":TARGET_LANGUAGE,
            "context":"",
            "enable_speaker_diarization":False,
            "enable_language_identification":False
        }
        return config
    
    def upload_audio(self, audio_path: str) -> str:
        print("Starting file upload...")
        res = self.session.post(
            f"{SONIOX_API_BASE_URL}/v1/files",
            files={"file": open(audio_path, "rb")},
        )
        file_id = res.json()["id"]
        print(f"File ID: {file_id}")
        return file_id

    def create_transcription(self, config) -> str:
        print("Creating transcription...")
        try:
            res = self.session.post(
                f"{SONIOX_API_BASE_URL}/v1/transcriptions",
                json=config,
            )
            res.raise_for_status()
            transcription_id = res.json()["id"]
            print(f"Transcription ID: {transcription_id}")
            return transcription_id
        except Exception as e:
            print("error here:", e)
            
    def wait_until_completed(self, transcription_id: str) -> None:
        print("Waiting for transcription...")
        while True:
            res = self.session.get(f"{SONIOX_API_BASE_URL}/v1/transcriptions/{transcription_id}")
            res.raise_for_status()
            data = res.json()
            if data["status"] == "completed":
                return
            elif data["status"] == "error":
                raise Exception(f"Error: {data.get('error_message', 'Unknown error')}")
            time.sleep(1)

    def get_transcription(self, transcription_id: str) -> dict:
        res = self.session.get(
            f"{SONIOX_API_BASE_URL}/v1/transcriptions/{transcription_id}/transcript"
        )
        res.raise_for_status()
        return res.json()

    def delete_transcription(self, transcription_id: str) -> dict:
        res = self.session.delete(f"{SONIOX_API_BASE_URL}/v1/transcriptions/{transcription_id}")
        res.raise_for_status()
        
    def delete_file(self, file_id: str) -> dict:
        res = self.session.delete(f"{SONIOX_API_BASE_URL}/v1/files/{file_id}")
        res.raise_for_status()
       
    # might be useful for timing adjustment
    def render_tokens(final_tokens: list[dict]) -> str:
        text_parts: list[str] = []
        current_speaker: Optional[str] = None
        current_language: Optional[str] = None

        # Process all tokens in order.
        for token in final_tokens:
            text = token["text"]
            speaker = token.get("speaker")
            language = token.get("language")
            is_translation = token.get("translation_status") == "translation"

            # Speaker changed -> add a speaker tag.
            if speaker is not None and speaker != current_speaker:
                if current_speaker is not None:
                    text_parts.append("\n\n")
                current_speaker = speaker
                current_language = None  # Reset language on speaker changes.
                text_parts.append(f"Speaker {current_speaker}:")

            # Language changed -> add a language or translation tag.
            if language is not None and language != current_language:
                current_language = language
                prefix = "[Translation] " if is_translation else ""
                text_parts.append(f"\n{prefix}[{current_language}] ")
                text = text.lstrip()

            text_parts.append(text)

        return "".join(text_parts)
    
    def transcribe_file(self, audio_path: Optional[str], srt_min_duration: int, srt_max_duration: int, srt_max_chars):
        """
        Run soniox transcription on the given audio file and return SRT formatted segments
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        try:
            file_id = self.upload_audio(audio_path)
            config = self.get_config(audio_url=None, file_id=file_id, translation=None)
            transcription_id = self.create_transcription(config)
            self.wait_until_completed(transcription_id)
            res = self.get_transcription(transcription_id)
        except Exception as e:
            logging.error(f"soniox transcription failed: {e}")
            return None
        
        tokens = res["tokens"]
        self.delete_transcription(transcription_id)
        if file_id is not None: self.delete_file(file_id)
            
        return soniox_to_srt(tokens, srt_min_duration, srt_max_duration, srt_max_chars)

class StableTSProcessor:
    """
    Processor to run stable-ts on a local audio file and return srt format directly
    """

    def __init__(self, model: str="turbo", extra_args=None):
        self.model = model
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.extra_args = extra_args or []
        self.model = "whisper-large-v3-turbo"

        try:
            import stable_whisper
        except ImportError:
            logging.error("stable_whisper (stable-ts) is not installed. Please install it via pip.")
        try:
            self.model = stable_whisper.load_model(model, device=self.device)
        except Exception as e:
            logging.error(f"Failed to load stable-ts model: {e}")

    def get_audio_segments(
        self, audio_path: str, language: str = "ja", word_timestamps: bool = False, vad: bool = True, min_silence_duration_ms: int=250
        ) -> str:
        """
        Run stable-ts (via stable_whisper) on the given audio file and return SRT formatted segments
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Transcribe
        try:
            result = self.model.transcribe(
                audio_path,
                word_timestamps=word_timestamps,
                vad=vad,
                temperature=0.0,
            )
            return result.to_srt_vtt(segment_level=True, word_level=False)
        except Exception as e:
            logging.error(f"stable-ts transcription failed: {e}")
            return None
    
class SubtitleProcessor:
    def __init__(self, soniox_client=None, local_processor=None) -> None:
        self.local_processor = self.soniox_client = None
        if local_processor:
            self.local_processor: StableTSProcessor = local_processor
        elif soniox_client:
            self.soniox_client: SonioxProcessor = soniox_client
        self.video_title = None
        self.temp_audio_file = None
        self.output_srt_path = None
    
    def generate_subtitles(self, language: str = TARGET_LANGUAGE[0], model: str = "small"):
        output_file_path=self.output_srt_path
        input_file_path = self.temp_audio_file
        result = None
        try:
            # both returns srt formatted string
            if self.local_processor:
                result = self.local_processor.get_audio_segments(input_file_path, language=language, word_timestamps=True)
            elif self.soniox_client:
                result = self.soniox_client.transcribe_file(input_file_path, SONIOX_SRT_MIN_DURATION, SONIOX_SRT_MAX_DURATION, SONIOX_MAX_CHARS)
        except Exception as e:
            logging.error(f"Error executing {os.path.basename(input_file_path)}: {e}")
        
        if result is None:
            print("No subtitles were generated.")
            return
        try:
            with open(output_file_path, "w", encoding="utf-8") as f:
                f.write(result)
                logging.info(f"Successfully generated srt file {output_file_path}")
                print(f"Successfully generated srt file at: {os.path.abspath(output_file_path)}")
        except IOError as e:
            logging.error(f"Failed to generate srt file: {e}")
            print(f"Failed to generate srt file: {e}")
        finally:
            self.cleanup_local_temp_files()
    
    def prepare_audio_file(self, url: str):
        """
        Extract audio from a YouTube video and save it temporarily for transcription
        """
        ydl_info_opts = {'verbose':False, 'quiet': True, 'no_warnings': True,}
        try:
            with yt_dlp.YoutubeDL(ydl_info_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                sanitized = ydl.sanitize_info(info)
                self.video_title = sanitized.get('title', 'output')
                filename = f"{(sanitized.get('id', 'youtube-audio'))}.m4a"
                print(f"filename: {filename}")
        except Exception as e:
            print(f'defaulting audio filename')

        ydl_opts = {
            'verbose':False, 
            'quiet': True, 
            'no_warnings': True,
            'progress': True,
            'outtmpl' : filename,
            'no_playlist': True,
            'format': 'm4a/bestaudio/best',
            # ℹ️ See help(yt_dlp.postprocessor) for a list of available Postprocessors and their arguments
            'postprocessors': [{  # Extract audio using ffmpeg
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
            }]
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if os.path.exists(filename):
                    print(f'Successfully downloaded audio: {os.path.abspath(filename)}')
                else:
                    print(f"Error: audio file {filename} not found")
        except yt_dlp.utils.DownloadError as e:
            print(f"yt-dlp download error: {e}")
        except Exception as e:
            print(f"Error during audio download/extraction: {e}", exc_info=True)
        finally:
            self.temp_audio_file = os.path.abspath(filename)
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            
            # example output/[soniox]-「っす」は失礼じゃない。むしろ神。.srt
            self.output_srt_path = os.path.join(OUTPUT_DIR, f"[{'stable-ts' if self.local_processor else 'soniox'}]-{os.path.splitext(os.path.basename(self.video_title))[0]}.srt")
    
    def cleanup_local_temp_files(self):
        if self.temp_audio_file:
            try:
                if os.path.exists(self.temp_audio_file):
                    os.remove(self.temp_audio_file)
                    logging.info(f"Cleaned up temporary file: {self.temp_audio_file}")
            except OSError as e:
                logging.warning(f"Could not remove temporary file {self.temp_audio_file}: {e}")
        self._temp_audio_file = None
    
def main():
    parser = argparse.ArgumentParser(description="Generate subtitles for a given audio file or YouTube video. Intended to use with ASBPlayer")
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        choices=["soniox", "stable-ts"],
        help="Specify the model (choose from %(choices)s)", required=True
    )
    parser.add_argument("-u", "--url", help="youtube URL", required=True)
    args = parser.parse_args()
    model = args.model
    url = args.url
    try:
        if model == "soniox":
            processor = SubtitleProcessor(soniox_client=SonioxProcessor())
        elif model == "stable-ts":
            print("initializing, this may take some time...")
            processor = SubtitleProcessor(local_processor=StableTSProcessor())
        else:
            logging.error(f"invalid model: {model}")
        print("local processor initialized, processing...")
    except Exception as e:
        logging.error(f"failed to initialize local processor: {e}")
        return
    processor.prepare_audio_file(url=url)
    processor.generate_subtitles()

if __name__ == "__main__":
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except(subprocess.CalledProcessError, FileNotFoundError):
        print("ffmpeg command not found. Please install ffmpeg and try again.")
    main()