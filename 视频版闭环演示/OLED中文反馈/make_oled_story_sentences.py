# -*- coding: utf-8 -*-
"""
make_oled_story_sentences.py
生成视频剧情完整句子的 OLED 点阵页。
每页 128x32，可显示两行，每行 8 个汉字，共 16 个汉字。
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).parent
OUT = BASE_DIR / "oled_story_sentences.h"

PAGES = {
    # 第一句：妈，医生建议住院，我们现在去交费，可以吗？
    "SENT_PAY_1": "医生建议住院现在",
    "SENT_PAY_2": "去交费可以吗",
    # 第二句：妈，钱不用担心。我已经请好假了，可以陪您一起。
    "SENT_WITH_1": "钱不用担心我已",
    "SENT_WITH_2": "请好假陪您一起",
    # 第三句：走，办手续去。
    "SENT_GO_1": "走办手续去",
    # 情绪句/状态句
    "SENT_WORRY_1": "妈妈有些担忧",
    "SENT_ANXIETY_1": "妈妈焦虑犹豫",
    "SENT_RELIEF_1": "妈妈安心接受",
    "SENT_CALM_1": "保持平静沟通",
}

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
]
FONT_SIZE = 16
CHAR_W = 16
CHAR_H = 16
PAGE_W = 128
PAGE_H = 32


def load_font():
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, FONT_SIZE)
    raise FileNotFoundError("找不到中文字体")


def page_to_bitmap_bytes(text: str, font) -> list[int]:
    img = Image.new("1", (PAGE_W, PAGE_H), 0)
    draw = ImageDraw.Draw(img)
    text = text[:16]
    for i, ch in enumerate(text):
        row = i // 8
        col = i % 8
        x0 = col * CHAR_W
        y0 = row * CHAR_H
        bbox = draw.textbbox((0, 0), ch, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = x0 + max(0, (CHAR_W - tw) // 2) - bbox[0]
        y = y0 + max(0, (CHAR_H - th) // 2) - bbox[1]
        draw.text((x, y), ch, font=font, fill=1)
    data = []
    for y in range(PAGE_H):
        for bx in range(0, PAGE_W, 8):
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
        "// 自动生成：视频剧情完整句子 OLED 点阵页。每页 128x32。\n",
        "// 使用 display.drawBitmap(0, 16, SENT_PAY_1, 128, 32, SSD1306_WHITE);\n\n",
    ]
    for name, text in PAGES.items():
        parts.append(f"// {text}\n")
        parts.append(fmt_array(name, page_to_bitmap_bytes(text, font)))
        parts.append("\n")
    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"OK: {OUT}")


if __name__ == "__main__":
    main()
