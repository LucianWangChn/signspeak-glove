# -*- coding: utf-8 -*-
"""
make_oled_bitmaps.py
把少量固定中文词渲染为 16x16 / 24x24 点阵，并生成 Arduino PROGMEM 头文件。

用途：OLED 不加载完整中文字库，只显示视频中需要的固定词。
依赖：pip install pillow

运行：
python make_oled_bitmaps.py
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).parent
OUT = BASE_DIR / "oled_zh_words.h"
WORDS = {
    "WORD_WORRY": "担忧",
    "WORD_ANXIETY": "焦虑",
    "WORD_RELIEF": "安心",
    "WORD_RELAX": "放松",
    "WORD_CALM": "平静",
    "WORD_ACCEPT": "接受",
}

# Windows 常见中文字体，按顺序尝试。
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
]

FONT_SIZE = 16
CHAR_W = 16
CHAR_H = 16
WORD_W = 32
WORD_H = 16


def load_font():
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, FONT_SIZE)
    raise FileNotFoundError("找不到中文字体，请检查 C:\\Windows\\Fonts 下是否有 simhei/simsun/msyh")


def word_to_bitmap_bytes(word: str, font) -> list[int]:
    img = Image.new("1", (WORD_W, WORD_H), 0)
    draw = ImageDraw.Draw(img)
    # 每个汉字 16x16，分别居中绘制。
    for i, ch in enumerate(word[:2]):
        x0 = i * CHAR_W
        bbox = draw.textbbox((0, 0), ch, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = x0 + max(0, (CHAR_W - tw) // 2) - bbox[0]
        y = max(0, (CHAR_H - th) // 2) - bbox[1]
        draw.text((x, y), ch, font=font, fill=1)
    data = []
    for y in range(WORD_H):
        for bx in range(0, WORD_W, 8):
            val = 0
            for bit in range(8):
                if img.getpixel((bx + bit, y)):
                    val |= (1 << (7 - bit))
            data.append(val)
    return data


def fmt_array(name: str, data: list[int]) -> str:
    rows = []
    for i in range(0, len(data), 12):
        rows.append("  " + ", ".join(f"0x{x:02X}" for x in data[i:i+12]))
    body = ",\n".join(rows)
    return f"const unsigned char {name}[] PROGMEM = {{\n{body}\n}};\n"


def main():
    font = load_font()
    parts = [
        "#pragma once\n",
        "#include <Arduino.h>\n",
        "// 自动生成：固定中文词 OLED 点阵。每个词 32x16，1 bit per pixel。\n",
        "// 使用 display.drawBitmap(x, y, WORD_WORRY, 32, 16, SSD1306_WHITE);\n\n",
    ]
    for name, word in WORDS.items():
        data = word_to_bitmap_bytes(word, font)
        parts.append(f"// {word}\n")
        parts.append(fmt_array(name, data))
        parts.append("\n")
    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"OK: {OUT}")


if __name__ == "__main__":
    main()
