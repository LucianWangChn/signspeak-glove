# -*- coding: utf-8 -*-
"""
collect_deep_gesture_tcp.py

通过串口助手 TCP 转发采集 R:/L: 双手完整传感器序列，保存为 CSV。

常改参数已集中放在文件最前面：
- LABEL_DURATION_SECONDS：四类动作各自采集时长
- COUNTDOWN_SECONDS：采集前倒计时
- MIN_FRAMES_TO_SAVE：少于多少帧不保存
"""

import argparse
import csv
import json
import re
import select
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

# ==================== 你最常改这里 ====================
HOST = "127.0.0.1"
PORT = 9001

# 四类动作分别采多久，单位：秒。
# 训练脚本允许每条样本帧数不同；但同一个标签建议尽量保持同一时长。
LABEL_DURATION_SECONDS = {
    "1": 10.0,  # 住院交费
    "2": 10.0,  # 不用担心陪你
    "3": 6.0,  # 去办手续
    "0": 3.0,  # 静止
}

COUNTDOWN_SECONDS = 3
MIN_FRAMES_TO_SAVE = 5
SELECT_TIMEOUT_SECONDS = 0.2
# =======================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "dataset_deep"
LABEL_PATH = BASE_DIR / "gesture_labels_deep.json"

DEFAULT_LABELS = {
    "1": "住院交费",
    "2": "不用担心陪你",
    "3": "去办手续",
    "0": "静止",
}

FEATURE_ORDER = [
    "R_Thumb", "R_Index", "R_Middle", "R_Ring", "R_Pinky", "R_aX", "R_aY", "R_gZ",
    "L_Thumb", "L_Index", "L_Middle", "L_Ring", "L_Pinky", "L_aX", "L_aY", "L_gZ",
]

SENSOR_RE = re.compile(
    r"([RL]):Thumb:([-\d.]+),Index:([-\d.]+),Middle:([-\d.]+),Ring:([-\d.]+),"
    r"Pinky:([-\d.]+),aX:([-\d.]+),aY:([-\d.]+),gZ:([-\d.]+)"
)


def fix_console_encoding():
    """尽量避免 Windows 控制台中文乱码。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_labels():
    if not LABEL_PATH.exists():
        LABEL_PATH.write_text(json.dumps(DEFAULT_LABELS, ensure_ascii=False, indent=2), encoding="utf-8")
    return json.loads(LABEL_PATH.read_text(encoding="utf-8"))


def decode_bytes(data: bytes) -> str:
    for enc in ("utf-8", "gbk", "latin1"):
        try:
            return data.decode(enc)
        except Exception:
            pass
    return data.decode("utf-8", errors="replace")


def update_from_line(line: str, latest: dict) -> bool:
    m = SENSOR_RE.search(line)
    if not m:
        return False

    hand = m.group(1)
    vals = list(map(float, m.groups()[1:]))
    names = ["Thumb", "Index", "Middle", "Ring", "Pinky", "aX", "aY", "gZ"]
    for name, val in zip(names, vals):
        latest[f"{hand}_{name}"] = val
    return True


def collect_once(sock: socket.socket, duration: float):
    latest = {k: 0.0 for k in FEATURE_ORDER}
    rows = []
    text_buffer = ""
    start = time.time()

    while time.time() - start < duration:
        readable, _, _ = select.select([sock], [], [], SELECT_TIMEOUT_SECONDS)
        if not readable:
            continue

        data = sock.recv(4096)
        if not data:
            raise RuntimeError("TCP 连接被串口助手关闭")

        text_buffer += decode_bytes(data)
        parts = re.split(r"[\r\n]+", text_buffer)
        text_buffer = parts[-1]

        changed = False
        for line in parts[:-1]:
            changed = update_from_line(line, latest) or changed

        if changed:
            row = dict(latest)
            row["t"] = round(time.time() - start, 3)
            rows.append(row)

    return rows


def save_csv(rows, label_id: str, label_name: str, duration: float):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = label_name.replace("/", "_").replace("\\", "_")
    path = DATA_DIR / f"gesture_{label_id}_{safe_name}_{duration:.1f}s_{ts}.csv"

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["frame", "t", "label", "label_name", "duration", *FEATURE_ORDER])
        for i, row in enumerate(rows):
            writer.writerow([
                i,
                row.get("t", 0),
                label_id,
                label_name,
                duration,
                *[row.get(k, 0.0) for k in FEATURE_ORDER],
            ])

    print(f"💾 已保存 {len(rows)} 帧：{path}")


def parse_duration_overrides(text: str):
    """解析形如 1=4,2=4,3=3,0=3 的命令行覆盖参数。"""
    if not text:
        return {}
    result = {}
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"无效 duration item：{item}，应为 1=4")
        key, val = item.split("=", 1)
        result[key.strip()] = float(val.strip())
    return result


def print_help(labels, durations):
    print("\n当前标签与采集时长：")
    for k in sorted(labels.keys()):
        print(f"  {k}: {labels[k]}，采集 {durations.get(k, 4.0)} 秒")
    print("\n输入标签编号开始采集；输入 q 退出。")


def main():
    fix_console_encoding()

    parser = argparse.ArgumentParser(description="TCP 转发采集双手深度学习手语数据")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--duration", type=float, default=None, help="覆盖所有标签的采集时长，例如 --duration 4")
    parser.add_argument("--durations", default="", help="分别设置各标签时长，例如 --durations 1=4,2=4,3=3,0=3")
    parser.add_argument("--countdown", type=int, default=COUNTDOWN_SECONDS)
    args = parser.parse_args()

    labels = load_labels()
    durations = dict(LABEL_DURATION_SECONDS)
    durations.update(parse_duration_overrides(args.durations))
    if args.duration is not None:
        durations = {k: float(args.duration) for k in labels.keys()}

    print_help(labels, durations)
    print(f"\n连接串口助手 TCP Server {args.host}:{args.port} ...")

    with socket.create_connection((args.host, args.port), timeout=10) as sock:
        sock.setblocking(False)
        print("✅ 已连接，开始等待采集命令。")

        while True:
            choice = input(f"\n标签 {labels} > ").strip()
            if choice.lower() in {"q", "quit", "exit"}:
                break
            if choice not in labels:
                print("无效标签")
                continue

            duration = float(durations.get(choice, 4.0))
            print(f"准备采集：{choice}={labels[choice]}，时长 {duration} 秒")

            for i in range(args.countdown, 0, -1):
                print(i)
                time.sleep(1)

            print("开始！")
            rows = collect_once(sock, duration)
            print(f"完成，帧数={len(rows)}")

            if len(rows) >= MIN_FRAMES_TO_SAVE:
                save_csv(rows, choice, labels[choice], duration)
            else:
                print(f"⚠️ 帧数太少（<{MIN_FRAMES_TO_SAVE}），未保存。请检查 TCP 转发是否在刷数据。")


if __name__ == "__main__":
    main()
