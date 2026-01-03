from typing import Optional
import os, time, argparse
import requests
from requests import Session
from dotenv import load_dotenv
from srt_converter import convert_srt
import downloader
import argparse

load_dotenv()

SONIOX_API_BASE_URL = "https://api.soniox.com"
SONIOX_TEMP_KEY_URL = os.environ.get("SONIOX_TEMP_KEY_URL")

def get_api_key() -> str:
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
    audio_url: Optional[str], file_id: Optional[str], translation: Optional[str]
) -> dict:
    config ={
        "model":"stt-async-v3",
        "file_id":file_id,
        "language_hints":["ja"],
        "context":"",
        "enable_speaker_diarization":False,
        "enable_language_identification":False
    }
    return config

def upload_audio(session: Session, audio_path: str) -> str:
    print("Starting file upload...")
    res = session.post(
        f"{SONIOX_API_BASE_URL}/v1/files",
        files={"file": open(audio_path, "rb")},
    )
    file_id = res.json()["id"]
    print(f"File ID: {file_id}")
    return file_id

import httpx
def upload_audio_with_httpx(api_key: str, audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        files = {"file": (audio_path, f)}
        headers = {"Authorization": f"Bearer {api_key}"}
        response = httpx.post(
            "https://api.soniox.com/v1/files",
            files=files,
            headers=headers,
            timeout=60.0,
        )
    response.raise_for_status()
    print(response)
    file_id = response.json()["id"]
    print(f"File ID: {file_id}")
    return file_id

def create_transcription(session: Session, config) -> str:
    print("Creating transcription...")
    try:
        res = session.post(
            f"{SONIOX_API_BASE_URL}/v1/transcriptions",
            json=config,
        )
        res.raise_for_status()
        transcription_id = res.json()["id"]
        print(f"Transcription ID: {transcription_id}")
        return transcription_id
    except Exception as e:
        print("error here:", e)
        
def wait_until_completed(session: Session, transcription_id: str) -> None:
    print("Waiting for transcription...")
    while True:
        res = session.get(f"{SONIOX_API_BASE_URL}/v1/transcriptions/{transcription_id}")
        res.raise_for_status()
        data = res.json()
        if data["status"] == "completed":
            return
        elif data["status"] == "error":
            raise Exception(f"Error: {data.get('error_message', 'Unknown error')}")
        time.sleep(1)

def get_transcription(session: Session, transcription_id: str) -> dict:
    res = session.get(
        f"{SONIOX_API_BASE_URL}/v1/transcriptions/{transcription_id}/transcript"
    )
    res.raise_for_status()
    return res.json()

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

def delete_transcription(session: Session, transcription_id: str) -> dict:
    res = session.delete(f"{SONIOX_API_BASE_URL}/v1/transcriptions/{transcription_id}")
    res.raise_for_status()
    
def delete_file(session: Session, file_id: str) -> dict:
    res = session.delete(f"{SONIOX_API_BASE_URL}/v1/files/{file_id}")
    res.raise_for_status()

def transcribe_file(session: Session, audio_path: Optional[str], srt_min_duration: int, srt_max_duration: int, output: str) -> None:
    if audio_path:
        assert audio_path
        file_id = upload_audio(session, audio_path)
        # file_id = "33a5db78-dd56-4284-a5e6-50701477304b"
    config = get_config(audio_url=None, file_id=file_id, translation=None)
    transcription_id = create_transcription(session, config)
    wait_until_completed(session, transcription_id)
    res = get_transcription(session, transcription_id)
    
    tokens = res["tokens"]
    text = render_tokens(tokens)
    print(text)
    # generate srt file
    convert_srt(tokens, srt_min_duration, srt_max_duration, output)
    
    delete_transcription(session, transcription_id)

    if file_id is not None:
        delete_file(session, file_id)
    return

def main():
    parser = argparse.ArgumentParser(description="Generate subtitles for a given audio file or YouTube video. Intended to use with ASBPlayer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-a", "--audio_path", help="Path to the local audio file")
    group.add_argument("-yt", "--yt_url", help="YouTube video URL")
    parser.add_argument("--srt_min_duration", type=int, default=1000, help="Minimum duration (ms) per SRT entry")
    parser.add_argument("--srt_max_duration", type=int, default=5000, help="Maximum duration (ms) per SRT entry")
    parser.add_argument("-o", "--output", default="output.srt", help="Output SRT file name")
    args = parser.parse_args()

    if args.audio_path:
        audio_path = args.audio_path
    else:
        audio_path = downloader.download_yt_from_url(args.yt_url)

    srt_min_duration = args.srt_min_duration
    srt_max_duration = args.srt_max_duration
    output = args.output
    api_key = get_api_key()
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {api_key}"
    transcribe_file(session, audio_path, srt_min_duration, srt_max_duration, output)

if __name__ == "__main__":
    main()
