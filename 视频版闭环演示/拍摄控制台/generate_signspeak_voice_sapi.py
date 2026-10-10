# -*- coding: utf-8 -*-
"""
generate_signspeak_voice_sapi.py
使用 Windows SAPI 本地生成女儿手语翻译语音外放音频（WAV）。
不依赖联网 API，适合视频拍摄兜底。
"""

from pathlib import Path
import win32com.client

OUT_DIR = Path(__file__).parent / "audio_output"

LINES = [
    ("01_hospital_payment", "妈，医生建议住院，我们现在去交费，可以吗？"),
    ("02_dont_worry", "妈，钱不用担心。我已经请好假了，可以陪您一起。"),
    ("03_go_paperwork", "走，办手续去。"),
]


def pick_chinese_voice(sp):
    voices = sp.GetVoices()
    for i in range(voices.Count):
        v = voices.Item(i)
        desc = v.GetDescription()
        if "Chinese" in desc or "Huihui" in desc or "Hui" in desc:
            return v
    return voices.Item(0) if voices.Count else None


def synthesize(name: str, text: str):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sp = win32com.client.Dispatch("SAPI.SpVoice")
    voice = pick_chinese_voice(sp)
    if voice is not None:
        sp.Voice = voice
    sp.Rate = 0
    sp.Volume = 100

    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    # 22kHz 16-bit mono PCM
    stream.Format.Type = 22
    out = OUT_DIR / f"{name}.wav"
    stream.Open(str(out), 3, False)  # SSFMCreateForWrite = 3
    old_stream = sp.AudioOutputStream
    sp.AudioOutputStream = stream
    sp.Speak(text)
    sp.AudioOutputStream = old_stream
    stream.Close()
    print(f"OK {out}")


def main():
    for name, text in LINES:
        synthesize(name, text)
    print(f"DONE: {OUT_DIR}")


if __name__ == "__main__":
    main()
