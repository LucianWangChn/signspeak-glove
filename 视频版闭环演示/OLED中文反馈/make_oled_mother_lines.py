# -*- coding: utf-8 -*-
"""
make_oled_mother_lines.py
生成妈妈台词 OLED 全屏大字点阵。
只保留：行吧、行吧听你的。
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).parent
OUT = BASE_DIR / "oled_mother_lines.h"

PAGES = {
    "MOM_LINE_1": "行吧",
    "MOM_LINE_2": "行吧听你的",
}

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
]
PAGE_W = 128
PAGE_H = 64


def load_font(text: str):
    # 两个字可以尽量大；五个字稍小但仍尽量占满宽度。
    sizes = [40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20, 18, 16]
    for font_path in FONT_CANDIDATES:
        if not Path(font_path).exists():
            continue
        for size in sizes:
            font = ImageFont.truetype(font_path, size)
            dummy = Image.new("1", (PAGE_W, PAGE_H), 0)
            draw = ImageDraw.Draw(dummy)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            if tw <= PAGE_W - 4 and th <= PAGE_H - 4:
                return font
    raise FileNotFoundError("找不到可用中文字体")


def page_to_bitmap_bytes(text: str) -> list[int]:
    font = load_font(text)
    img = Image.new("1", (PAGE_W, PAGE_H), 0)
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (PAGE_W - tw) // 2 - bbox[0]
    y = (PAGE_H - th) // 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=1)

    data = []
    for y0 in range(PAGE_H):
        for bx in range(0, PAGE_W, 8):
            val = 0
            for bit in range(8):
                if img.getpixel((bx + bit, y0)):
                    val |= (1 << (7 - bit))
            data.append(val)
    return data


def fmt_array(name: str, data: list[int]) -> str:
    rows = []
    for i in range(0, len(data), 16):
        rows.append("  " + ", ".join(f"0x{x:02X}" for x in data[i:i+16]))
    return f"const unsigned char {name}[] PROGMEM = {{\n" + ",\n".join(rows) + "\n};\n"


def main():
    parts = [
        "#pragma once\n",
        "#include <Arduino.h>\n",
        "// 自动生成：妈妈台词 OLED 全屏大字点阵，128x64。\n\n",
    ]
    for name, text in PAGES.items():
        parts.append(f"// {text}\n")
        parts.append(fmt_array(name, page_to_bitmap_bytes(text)))
        parts.append("\n")
    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"OK: {OUT}")


if __name__ == "__main__":
    main()
