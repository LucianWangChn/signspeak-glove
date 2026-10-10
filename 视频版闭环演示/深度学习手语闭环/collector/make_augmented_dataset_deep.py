# -*- coding: utf-8 -*-
"""
make_augmented_dataset_deep.py

从 dataset_deep 读取真实采集 CSV，生成一个新的清理+增强数据集目录，默认不覆盖原目录。

输出目录：dataset_deep_augmented_YYYYMMDD_HHMMSS
默认目标数量：每个标签 25 条。

注意：这是用于结课演示/小样本模型验证的数据增强，不等价于真实大规模采集。
"""

import argparse
import csv
import math
import random
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "dataset_deep"

FEATURE_COLS = [
    "R_Thumb", "R_Index", "R_Middle", "R_Ring", "R_Pinky", "R_aX", "R_aY", "R_gZ",
    "L_Thumb", "L_Index", "L_Middle", "L_Ring", "L_Pinky", "L_aX", "L_aY", "L_gZ",
]

LABEL_NAME = {
    "0": "静止",
    "1": "住院交费",
    "2": "不用担心陪你",
    "3": "去办手续",
}

NUMERIC_COLS = ["frame", "t", "duration", *FEATURE_COLS]


def safe_float(x, default=0.0):
    try:
        if x is None or x == "":
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    clean = []
    for i, row in enumerate(rows):
        out = dict(row)
        for col in NUMERIC_COLS:
            if col in out:
                out[col] = safe_float(out[col])
        out["frame"] = i
        clean.append(out)
    return clean


def write_csv(path: Path, rows, label: str, label_name: str):
    fieldnames = ["frame", "t", "label", "label_name", "duration", *FEATURE_COLS]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        duration = rows[-1].get("t", 0.0) if rows else 0.0
        for i, row in enumerate(rows):
            out = {k: row.get(k, 0.0) for k in fieldnames}
            out["frame"] = i
            out["label"] = label
            out["label_name"] = label_name
            out["duration"] = round(float(duration), 3)
            writer.writerow(out)


def infer_label(path: Path, rows):
    if rows:
        label = str(rows[0].get("label", "")).strip()
        if label in LABEL_NAME:
            return label
    m = re.search(r"gesture_([0-3])_", path.name)
    if m:
        return m.group(1)
    return None


def clean_rows(rows, min_frames=5):
    if len(rows) < min_frames:
        return []
    out = []
    last_t = -1.0
    for i, row in enumerate(rows):
        nr = {}
        for col in FEATURE_COLS:
            nr[col] = safe_float(row.get(col, 0.0))
        t = safe_float(row.get("t", i * 0.2))
        if t <= last_t:
            t = last_t + 0.2
        last_t = t
        nr["t"] = round(t, 3)
        nr["frame"] = i
        out.append(nr)
    return out


def augment_rows(rows, label: str, variant_idx: int):
    # 数据增强：整体偏移、缩放、轻微噪声、时间扰动。
    rng = random.Random(20260601 + int(label) * 1000 + variant_idx)
    new_rows = []

    # 各通道的全局仿射扰动，保持动作形状但制造个体差异。
    scale = {c: rng.uniform(0.985, 1.015) for c in FEATURE_COLS}
    offset = {}
    for c in FEATURE_COLS:
        if "Thumb" in c or "Index" in c or "Middle" in c or "Ring" in c or "Pinky" in c:
            offset[c] = rng.uniform(-8, 8)
        else:
            offset[c] = rng.uniform(-1.5, 1.5)

    time_scale = rng.uniform(0.94, 1.06)
    for i, row in enumerate(rows):
        nr = {}
        for c in FEATURE_COLS:
            v = safe_float(row.get(c, 0.0))
            if c.startswith("L_") and abs(v) < 0.01:
                # 没有左手数据时保持 0，不凭空造左手信号。
                nv = 0.0
            else:
                noise = rng.uniform(-3, 3) if c.endswith(("Thumb", "Index", "Middle", "Ring", "Pinky")) else rng.uniform(-0.8, 0.8)
                nv = v * scale[c] + offset[c] + noise
                if c.endswith(("Thumb", "Index", "Middle", "Ring", "Pinky")):
                    nv = max(0, min(1023, nv))
            nr[c] = round(nv, 3)
        nr["t"] = round(safe_float(row.get("t", i * 0.2)) * time_scale, 3)
        nr["frame"] = i
        new_rows.append(nr)
    return new_rows


def main():
    parser = argparse.ArgumentParser(description="清理并增强 dataset_deep，不覆盖原目录")
    parser.add_argument("--source", default=str(SRC_DIR))
    parser.add_argument("--target-per-label", type=int, default=25, help="每个标签目标数量，建议 20-30，默认25")
    parser.add_argument("--out", default="", help="输出目录，不传则自动 dataset_deep_augmented_时间戳")
    parser.add_argument("--min-frames", type=int, default=5)
    args = parser.parse_args()

    src = Path(args.source)
    if not src.exists():
        raise FileNotFoundError(src)
    out_dir = Path(args.out) if args.out else src.parent / ("dataset_deep_augmented_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=False)

    by_label = defaultdict(list)
    skipped = []
    for path in sorted(src.glob("*.csv")):
        rows = clean_rows(read_csv(path), min_frames=args.min_frames)
        if not rows:
            skipped.append(path.name)
            continue
        label = infer_label(path, rows)
        if label is None:
            skipped.append(path.name)
            continue
        by_label[label].append((path, rows))

    print(f"源目录: {src}")
    print(f"输出目录: {out_dir}")
    print("原始数量:")
    for label in sorted(LABEL_NAME):
        print(f"  {label}-{LABEL_NAME[label]}: {len(by_label[label])}")

    summary = []
    for label in sorted(LABEL_NAME):
        label_name = LABEL_NAME[label]
        items = by_label[label]
        if not items:
            print(f"⚠️ 标签 {label}-{label_name} 没有原始样本，无法增强")
            continue

        label_dir_count = 0
        # 先复制清理后的真实样本
        for idx, (src_path, rows) in enumerate(items):
            dst = out_dir / f"real_{label}_{label_name}_{idx+1:03d}_{src_path.stem}.csv"
            write_csv(dst, rows, label, label_name)
            label_dir_count += 1

        # 再增强到目标数量
        aug_idx = 1
        while label_dir_count < args.target_per_label:
            src_path, rows = items[(aug_idx - 1) % len(items)]
            aug = augment_rows(rows, label, aug_idx)
            dst = out_dir / f"aug_{label}_{label_name}_{aug_idx:03d}_from_{src_path.stem}.csv"
            write_csv(dst, aug, label, label_name)
            label_dir_count += 1
            aug_idx += 1

        summary.append((label, label_name, label_dir_count))

    # 写摘要
    report = out_dir / "README_augmented_dataset.md"
    with report.open("w", encoding="utf-8", newline="") as f:
        f.write("# dataset_deep augmented\n\n")
        f.write(f"source: `{src}`\n\n")
        f.write(f"target_per_label: {args.target_per_label}\n\n")
        f.write("## counts\n\n")
        for label, name, count in summary:
            f.write(f"- {label} {name}: {count}\n")
        if skipped:
            f.write("\n## skipped\n\n")
            for s in skipped:
                f.write(f"- {s}\n")
        f.write("\n说明：该目录由真实样本清理+轻微扰动增强生成，不覆盖原 dataset_deep。\n")

    print("\n最终数量:")
    for label, name, count in summary:
        print(f"  {label}-{name}: {count}")
    print(f"`nDONE: {out_dir}")


if __name__ == "__main__":
    main()

