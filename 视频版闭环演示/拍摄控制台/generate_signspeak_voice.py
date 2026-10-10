# -*- coding: utf-8 -*-
"""
generate_signspeak_voice.py
为 SIGNSPEAK 视频生成女儿手语翻译的语音外放音频。

注意：API key 从环境变量 OPENAI_API_KEY 读取，避免把密钥写入文件。
PowerShell 示例：
$env:OPENAI_API_KEY="你的 key"
$env:OPENAI_BASE_URL="https://ai.space.cx/v1"
python generate_signspeak_voice.py
"""

import base64
import json
import os
from pathlib import Path

import requests

BASE_URL = os.getenv("OPENAI_BASE_URL", "https://ai.space.cx/v1").rstrip("/")
API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-audio-preview")
VOICE = os.getenv("OPENAI_TTS_VOICE", "alloy")
OUT_DIR = Path(__file__).parent / "audio_output"

LINES = [
    ("01_hospital_payment", "妈，医生建议住院，我们现在去交费，可以吗？"),
    ("02_dont_worry", "妈，钱不用担心。我已经请好假了，可以陪您一起。"),
    ("03_go_paperwork", "走，办手续去。"),
]


def synthesize(name: str, text: str):
    if not API_KEY:
        raise RuntimeError("请先设置环境变量 OPENAI_API_KEY")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "modalities": ["text", "audio"],
        "audio": {"voice": VOICE, "format": "mp3"},
        "messages": [
            {
                "role": "system",
                "content": "你是一名中文配音演员。请用自然、清晰、年轻女性的语气朗读台词，语速适中，适合视频中作为手语翻译的语音外放。只朗读台词本身，不要添加解释。",
            },
            {"role": "user", "content": text},
        ],
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:1000]}")
    data = resp.json()
    msg = data["choices"][0]["message"]
    audio = msg.get("audio") or {}
    b64 = audio.get("data")
    if not b64:
        raise RuntimeError("响应中没有 audio.data；请确认中转站支持 gpt-4o-audio-preview 的 audio 输出。")

    audio_bytes = base64.b64decode(b64)
    out = OUT_DIR / f"{name}.mp3"
    out.write_bytes(audio_bytes)
    meta = OUT_DIR / f"{name}.json"
    meta.write_text(json.dumps({"text": text, "model": MODEL, "voice": VOICE}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK {out}")


def main():
    for name, text in LINES:
        synthesize(name, text)
    print(f"DONE: {OUT_DIR}")


if __name__ == "__main__":
    main()
