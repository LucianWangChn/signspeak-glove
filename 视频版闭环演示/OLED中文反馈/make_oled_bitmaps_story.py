# -*- coding: utf-8 -*-
"""
make_oled_bitmaps_story.py
生成视频剧本专用 OLED 中文固定点阵。
每个短语 64x16，适合 128x64 OLED 一行显示。
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).parent
OUT = BASE_DIR / "oled_story_words.h"

PHRASES = {
    "TXT_MOM_WORRY": "妈妈担忧",
    "TXT_ANXIETY": "焦虑犹豫",
    "TXT_RELIEF": "妈妈安心",
    "TXT_RELAX": "放松接受",
    "TXT_PAY": "住院交费",
    "TXT_ACCOMPANY": "陪你一起",
    "TXT_PAPERWORK": "去办手续",
    "TXT_CALM": "平静沟通",
}

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
]
FONT_SIZE = 16
CHAR_W = 16
CHAR_H = 16
PHRASE_W = 64
PHRASE_H = 16


def load_font():
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, FONT_SIZE)
    raise FileNotFoundError("找不到中文字体")


def phrase_to_bitmap_bytes(text: str, font) -> list[int]:
    img = Image.new("1", (PHRASE_W, PHRASE_H), 0)
    draw = ImageDraw.Draw(img)
    for i, ch in enumerate(text[:4]):
        x0 = i * CHAR_W
        bbox = draw.textbbox((0, 0), ch, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = x0 + max(0, (CHAR_W - tw) // 2) - bbox[0]
        y = max(0, (CHAR_H - th) // 2) - bbox[1]
        draw.text((x, y), ch, font=font, fill=1)
    data = []
    for y in range(PHRASE_H):
        for bx in range(0, PHRASE_W, 8):
            val = 0
            for bit in range(8):
                if img.getpixel((bx + bit, y)):
                    val |= (1 << (7 - bit))
            data.append(val)
    return data


def fmt_array(name: str, data: list[int]) -> str:
    rows = []
    for i in range(0, len(data), 16):
        rows.append("  " + ", ".join(f"0x{x:02X}" for x in data[i:i+16]))
    return f"const unsigned char {name}[] PROGMEM = {{\n" + ",\n".join(rows) + "\n};\n"


def main():
    font = load_font()
    parts = [
        "#pragma once\n",
        "#include <Arduino.h>\n",
        "// 自动生成：视频剧本 OLED 中文短语点阵。每个短语 64x16。\n",
        "// 使用 display.drawBitmap(x, y, TXT_MOM_WORRY, 64, 16, SSD1306_WHITE);\n\n",
    ]
    for name, text in PHRASES.items():
        parts.append(f"// {text}\n")
        parts.append(fmt_array(name, phrase_to_bitmap_bytes(text, font)))
        parts.append("\n")
    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"OK: {OUT}")


if __name__ == "__main__":
    main()
