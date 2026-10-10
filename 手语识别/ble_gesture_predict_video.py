# -*- coding: utf-8 -*-
"""
ble_gesture_predict.py
第二版手语实时预测 - 仅 BLE 版

重要：当前硬件蓝牙通信是 BLE，不是串口，因此本脚本不会列出 COM 口。

用法：
    python ble_gesture_predict.py
    python ble_gesture_predict.py --right 00:00:00:00:00:00
    python ble_gesture_predict.py --scan

依赖：pip install bleak pandas numpy scikit-learn
"""

import argparse
import asyncio
import io
import json
import pickle
import re
import sys
import time
from collections import deque
from pathlib import Path

if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np

RIGHT_GLOVE_ADDR = "00:00:00:00:00:00"
LEFT_GLOVE_ADDR = ""
BLE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
FEATURE_ORDER = ["Thumb", "Index", "Middle", "Ring", "Pinky", "aX", "aY", "gZ"]
WINDOW_SIZE = 40
PREDICT_INTERVAL = 0.5
THRESHOLD = 0.55
BASE_DIR = Path(__file__).parent
LABELS_PATH = BASE_DIR / "gesture_labels_video.json"
MODEL_PATH = BASE_DIR / "gesture_model_video.pkl"
right_queue: deque[dict] = deque(maxlen=WINDOW_SIZE)
left_queue: deque[dict] = deque(maxlen=WINDOW_SIZE)
model = None
label_names: dict = {}


def load_model() -> bool:
    global model, label_names
    if not MODEL_PATH.exists():
        print(f"❌ 模型文件不存在: {MODEL_PATH}")
        print("请先运行 ble_gesture_collector.py 采集数据，再运行 train_gesture_model.py 训练模型。")
        return False
    with MODEL_PATH.open("rb") as f:
        pack = pickle.load(f)
    model = pack["model"] if isinstance(pack, dict) and "model" in pack else pack
    if LABELS_PATH.exists():
        with LABELS_PATH.open("r", encoding="utf-8") as f:
            label_names = {str(k): str(v) for k, v in json.load(f).items()}
    print(f"✅ 模型加载完成: {MODEL_PATH.name}")
    if isinstance(pack, dict):
        print(f"✅ 标签: {pack.get('labels', [])}")
    return True


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
                    right_queue.append(parsed)
                else:
                    left_queue.append(parsed)
    return handler


def extract_sequence_features(rows: list[dict]) -> np.ndarray:
    values = np.array([[row.get(k, 0) for k in FEATURE_ORDER] for row in rows], dtype=np.float32)
    feats = []
    feats.extend(values.mean(axis=0))
    feats.extend(values.std(axis=0))
    feats.extend(values.min(axis=0))
    feats.extend(values.max(axis=0))
    feats.extend(values[-1] - values[0])
    if len(values) > 1:
        diffs = np.diff(values, axis=0)
        feats.extend(np.mean(np.abs(diffs), axis=0))
    else:
        feats.extend(np.zeros(values.shape[1]))
    return np.array(feats, dtype=np.float32).reshape(1, -1)


def predict(queue: deque, hand: str) -> str | None:
    if model is None or len(queue) < max(8, WINDOW_SIZE // 2):
        return None
    X = extract_sequence_features(list(queue))
    try:
        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(X)[0]
            idx = int(np.argmax(probs))
            label = model.classes_[idx]
            conf = float(probs[idx])
        else:
            label = model.predict(X)[0]
            conf = 1.0
        name = label_names.get(str(label), str(label))
        hand_cn = "右手" if hand == "R" else "左手"
        shown = name if conf >= THRESHOLD else f"不确定({name})"
        return f"🖐️ [{hand_cn}] {shown} 置信度={conf:.0%}"
    except Exception as exc:
        return f"⚠️ 预测失败: {exc}"


async def scan_devices():
    from bleak import BleakScanner
    print("🔍 扫描 BLE 设备（10秒）...")
    devices = await BleakScanner.discover(timeout=10.0)
    for d in devices:
        name = d.name or "未知"
        tag = " ← 可能是手套" if any(k in name.upper() for k in ["GLOVE", "BLE", "JDY", "HM"]) else ""
        print(f"  [{d.address}] {name}{tag}")


async def run_predictor(right_addr: str, left_addr: str):
    from bleak import BleakClient, BleakScanner
    if not load_model():
        return
    print("=" * 50)
    print("🖐️  BLE 手语实时预测（无串口版）")
    print("=" * 50)
    print(f"右手 BLE: {right_addr or '未设置'}")
    print(f"左手 BLE: {left_addr or '未设置'}")

    right_client = left_client = None
    if right_addr:
        print(f"🔗 连接右手 BLE {right_addr}...")
        dev = await BleakScanner.find_device_by_address(right_addr, timeout=12.0)
        if not dev:
            print(f"❌ 找不到右手 {right_addr}")
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
            print("⚠️ 未找到左手，继续只用右手")

    print("\n实时预测中... (Ctrl+C 退出)\n")
    try:
        while True:
            await asyncio.sleep(PREDICT_INTERVAL)
            results = []
            r = predict(right_queue, "R") if right_queue else None
            l = predict(left_queue, "L") if left_queue else None
            if r:
                results.append(r)
            if l:
                results.append(l)
            if results:
                sys.stdout.write("\r" + " | ".join(results) + "   ")
                sys.stdout.flush()
    except KeyboardInterrupt:
        print("\n⏹️  停止预测")
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
    parser = argparse.ArgumentParser(description="BLE 手语实时预测（无串口版）")
    parser.add_argument("--right", default=RIGHT_GLOVE_ADDR, help="右手 BLE 地址")
    parser.add_argument("--left", default=LEFT_GLOVE_ADDR, help="左手 BLE 地址，可留空")
    parser.add_argument("--scan", action="store_true", help="扫描 BLE 设备")
    args = parser.parse_args()
    if args.scan:
        asyncio.run(scan_devices())
    else:
        asyncio.run(run_predictor(args.right, args.left))


if __name__ == "__main__":
    main()
