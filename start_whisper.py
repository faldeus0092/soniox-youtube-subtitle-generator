import json
import base64
import logging
import os
import re
import subprocess
import threading
from dataclasses import dataclass

import requests
# import yaml
# import yt_dlp
import torch
# from dataclasses_json import dataclass_json

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
TARGET_LANGUAGE = os.environ.get("TARGET_LANGUAGE")

class StableTSProcessor:
    """
    Processor to run stable-ts on a local audio file and return segment/word timestamps similar to groq output.
    """

    def __init__(self, model="turbo", extra_args=None):
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

    def get_audio_segments(self, audio_path, language="ja", word_timestamps=False, vad=True, min_silence_duration_ms=250):
        """
        Run stable-ts (via stable_whisper) on the given audio file and return parsed segments/words.
        Returns a dict with 'segments' and 'words' keys, similar to groq output.
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
    
class SubtitleProcessor:
    def __init__(self, soniox_client=None, local_processor=None) -> None:
        self.local_processor: StableTSProcessor = local_processor
        self.temp_audio_file = None
    
    def generate_subtitles(self, input_file_path, output_file_path, language=TARGET_LANGUAGE, model="small"):
        result = None
        try:
            result = self.local_processor.get_audio_segments(input_file_path, language=language, word_timestamps=True)
        except Exception as e:
            logging.error(f"Error executing {os.path.basename(input_file_path)}: {e}")
        
        if result is None:
            print("No subtitles were generated.")
            return None
        try:
            with open(output_file_path, "w", encoding="utf-8") as f:
                f.write(result)
                logging.info(f"Successfully generated srt file {output_file_path}")
                print(f"Successfully generated srt file {output_file_path}")
        except IOError as e:
            logging.error(f"Failed to generate srt file: {e}")
            print(f"Failed to generate srt file: {e}")
        finally:
            self.cleanup_local_temp_files()
    
    def prepare_audio_file(self, input_file_path):
        self.temp_audio_file = input_file_path
        # download from youtube...
    
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
    audio_file_path = "「目に入れても痛くない」言い過ぎでは？.m4a"
    output_file_path = os.path.join(OUTPUT_DIR, f"{os.path.splitext(os.path.basename(audio_file_path))[0]}.srt")
    try:
        if os.path.exists(audio_file_path):
            print(f"found file: {audio_file_path}")
    except OSError as e:
        print(f"Could not find the file {audio_file_path}: {e}")
    try:
        processor = SubtitleProcessor(local_processor=StableTSProcessor())
        print("local processor initialized, processing...")
    except Exception as e:
        logging.error(f"failed to initialize local processor: {e}")
        return
    processor.prepare_audio_file(input_file_path=audio_file_path)
    processor.generate_subtitles(audio_file_path, output_file_path)

if __name__ == "__main__":
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except(subprocess.CalledProcessError, FileNotFoundError):
        print("ffmpeg command not found. Please install ffmpeg and try again.")
    main()