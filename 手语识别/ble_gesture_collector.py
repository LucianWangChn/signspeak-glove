# -*- coding: utf-8 -*-
"""
ble_gesture_collector.py
第二版手语数据采集脚本 - 仅 BLE 版

重要：当前硬件蓝牙通信是 BLE，不是串口，因此本脚本不会列出 COM 口。

用法：
    python ble_gesture_collector.py
    python ble_gesture_collector.py --right 00:00:00:00:00:00
    python ble_gesture_collector.py --scan

依赖：pip install bleak pandas
数据格式：frame,label,label_name,hand,Thumb,Index,Middle,Ring,Pinky,aX,aY,gZ
"""

import argparse
import asyncio
import csv
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

RIGHT_GLOVE_ADDR = "00:00:00:00:00:00"
LEFT_GLOVE_ADDR = ""
BLE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
COLLECT_DURATION_S = 3.0
DEFAULT_LABELS = {"1": "你好", "2": "谢谢", "3": "帮助", "4": "疼痛", "5": "停止"}
FEATURE_ORDER = ["Thumb", "Index", "Middle", "Ring", "Pinky", "aX", "aY", "gZ"]
BASE_DIR = Path(__file__).parent
LABELS_PATH = BASE_DIR / "gesture_labels.json"
OUTPUT_DIR = BASE_DIR / "dataset"
right_buffer: list[dict] = []
left_buffer: list[dict] = []


def load_labels() -> dict[str, str]:
    if LABELS_PATH.exists():
        with LABELS_PATH.open("r", encoding="utf-8") as f:
            return {str(k): str(v) for k, v in json.load(f).items()}
    return DEFAULT_LABELS


def parse_sensor_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    hand = "R"
    if line.startswith("L:"):
        hand = "L"
        line = line[2:]
    elif line.startswith("R:"):
        hand = "R"
        line = line[2:]
    data = {"hand": hand}
    for part in line.split(","):
        m = re.match(r"(\w+):(-?\d+(?:\.\d+)?)", part.strip())
        if m:
            data[m.group(1)] = float(m.group(2))
    if not all(k in data for k in FEATURE_ORDER):
        return None
    return data


def notification_handler(hand: str):
    def handler(characteristic, data: bytearray):
        text = data.decode("utf-8", errors="ignore")
        for line in text.split("\n"):
            parsed = parse_sensor_line(line)
            if parsed and parsed["hand"] == hand:
                if hand == "R":
                    right_buffer.append(parsed)
                else:
                    left_buffer.append(parsed)
    return handler


async def scan_devices():
    from bleak import BleakScanner
    print("🔍 扫描 BLE 设备（10秒）...")
    devices = await BleakScanner.discover(timeout=10.0)
    for d in devices:
        name = d.name or "未知"
        tag = " ← 可能是手套" if any(k in name.upper() for k in ["GLOVE", "BLE", "JDY", "HM"]) else ""
        print(f"  [{d.address}] {name}{tag}")


def save_csv(samples: list[dict], label_id: str, label_name: str, hand: str, path: Path):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["frame", "label", "label_name", "hand", *FEATURE_ORDER])
        for i, row in enumerate(samples):
            writer.writerow([i, label_id, label_name, hand, *[row.get(k, 0) for k in FEATURE_ORDER]])


def hand_label(hand: str) -> str:
    return "right" if hand == "R" else "left"


async def collect_one_sample(label_id: str, label_name: str, hand: str, duration: float):
    buf = right_buffer if hand == "R" else left_buffer
    buf.clear()
    hand_cn = "右手" if hand == "R" else "左手"
    print(f"\n🖐️  [{hand_cn}] 采集动作 {label_id}={label_name}，{duration}秒")
    print("请摆好起始姿态，3秒后开始。")
    for i in range(3, 0, -1):
        print(f"  {i}...")
        await asyncio.sleep(1)
    print("🎬 开始采集！")
    start_count = len(buf)
    await asyncio.sleep(duration)
    samples = list(buf[start_count:])
    print(f"✅ 采集完成，获取 {len(samples)} 帧")
    if len(samples) < 3:
        print("⚠️  帧数太少，可能 BLE 未推送传感器数据，请检查右手程序是否在发送 R:Thumb... 数据。")
        return []
    return samples


async def run_collector(right_addr: str, left_addr: str, duration: float):
    from bleak import BleakClient, BleakScanner
    labels = load_labels()
    print("=" * 50)
    print("🖐️  BLE 手语数据采集器（无串口版）")
    print("=" * 50)
    print(f"右手 BLE: {right_addr or '未设置'}")
    print(f"左手 BLE: {left_addr or '未设置'}")
    print(f"动作标签: {labels}")
    print(f"输出目录: {OUTPUT_DIR}")
    print()

    if not right_addr and not left_addr:
        print("⚠️  未设置 BLE 地址，先扫描。")
        await scan_devices()
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    right_client = left_client = None

    if right_addr:
        print(f"🔗 连接右手 BLE {right_addr}...")
        dev = await BleakScanner.find_device_by_address(right_addr, timeout=12.0)
        if not dev:
            print(f"❌ 找不到右手设备 {right_addr}")
            return
        right_client = BleakClient(dev, timeout=12.0)
        await right_client.connect()
        print("✅ 右手 BLE 已连接")
        await right_client.start_notify(BLE_UUID, notification_handler("R"))
        print("✅ 已订阅右手传感器通知")

    if left_addr:
        print(f"🔗 连接左手 BLE {left_addr}...")
        dev = await BleakScanner.find_device_by_address(left_addr, timeout=12.0)
        if dev:
            left_client = BleakClient(dev, timeout=12.0)
            await left_client.connect()
            print("✅ 左手 BLE 已连接")
            await left_client.start_notify(BLE_UUID, notification_handler("L"))
        else:
            print("⚠️  未找到左手，继续只采右手")

    try:
        print("\n输入动作序号开始采集；输入 l 查看标签；输入 s 扫描；输入 q 退出。")
        while True:
            print(f"\n可选动作: {labels}")
            choice = input("动作序号> ").strip()
            if choice.lower() in {"q", "quit", "exit"}:
                break
            if choice.lower() in {"l", "labels"}:
                continue
            if choice.lower() == "s":
                await scan_devices()
                continue
            if choice not in labels:
                print(f"❌ 无效序号: {choice}")
                continue
            label_name = labels[choice]
            if right_client and right_client.is_connected:
                samples = await collect_one_sample(choice, label_name, "R", duration)
                if samples:
                    path = OUTPUT_DIR / f"gesture_{choice}_{label_name}_{hand_label('R')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    save_csv(samples, choice, label_name, "R", path)
                    print(f"💾 已保存: {path}")
            if left_client and left_client.is_connected:
                samples = await collect_one_sample(choice, label_name, "L", duration)
                if samples:
                    path = OUTPUT_DIR / f"gesture_{choice}_{label_name}_{hand_label('L')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    save_csv(samples, choice, label_name, "L", path)
                    print(f"💾 已保存: {path}")
    finally:
        for client in [right_client, left_client]:
            if client:
                try:
                    if client.is_connected:
                        await client.stop_notify(BLE_UUID)
                        await client.disconnect()
                except Exception:
                    pass
        print("🔌 BLE 已断开")


def main():
    parser = argparse.ArgumentParser(description="BLE 手语数据采集器（无串口版）")
    parser.add_argument("--right", default=RIGHT_GLOVE_ADDR, help="右手 BLE 地址")
    parser.add_argument("--left", default=LEFT_GLOVE_ADDR, help="左手 BLE 地址，可留空")
    parser.add_argument("--duration", type=float, default=COLLECT_DURATION_S, help="每次采集时长秒")
    parser.add_argument("--scan", action="store_true", help="扫描 BLE 设备")
    args = parser.parse_args()
    if args.scan:
        asyncio.run(scan_devices())
    else:
        asyncio.run(run_collector(args.right, args.left, args.duration))


if __name__ == "__main__":
    main()
