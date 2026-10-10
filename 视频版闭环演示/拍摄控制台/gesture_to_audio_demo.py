# -*- coding: utf-8 -*-
"""
gesture_to_audio_demo.py
视频版：检测到手语短句后，自动播放对应电脑语音。

当前即使模型还没训练好，也可以用 --mock 预览完整逻辑：
    python gesture_to_audio_demo.py --mock

训练好后运行：
    python gesture_to_audio_demo.py

依赖：
    pip install bleak numpy scikit-learn

说明：
- 读取右手 BLE 传感器通知；
- 使用 gesture_model_video.pkl 做短句分类；
- 分类稳定后播放 audio_output 里的对应 WAV；
- 加入冷却时间，避免同一个动作连续重复播放。
"""

import argparse
import asyncio
import io
import json
import pickle
import re
import sys
import time
import wave
import winsound
from collections import Counter, deque
from pathlib import Path

if sys.platform.startswith("win"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np

RIGHT_GLOVE_ADDR = "00:00:00:00:00:00"
BLE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
FEATURE_ORDER = ["Thumb", "Index", "Middle", "Ring", "Pinky", "aX", "aY", "gZ"]
WINDOW_SIZE = 40
PREDICT_INTERVAL = 0.35
THRESHOLD = 0.60
STABLE_COUNT = 3
COOLDOWN_SEC = 4.0

BASE_DIR = Path(__file__).parent
HAND_DIR = BASE_DIR.parent.parent / "手语识别"
AUDIO_DIR = BASE_DIR / "audio_output"
MODEL_PATH = HAND_DIR / "gesture_model_video.pkl"
LABELS_PATH = HAND_DIR / "gesture_labels_video.json"

# 标签 -> 音频文件
AUDIO_MAP = {
    "1": AUDIO_DIR / "01_hospital_payment.wav",
    "2": AUDIO_DIR / "02_dont_worry.wav",
    "3": AUDIO_DIR / "03_go_paperwork.wav",
}

# 标签 -> 台词说明
TEXT_MAP = {
    "1": "妈，医生建议住院，我们现在去交费，可以吗？",
    "2": "妈，钱不用担心。我已经请好假了，可以陪您一起。",
    "3": "走，办手续去。",
}

right_queue: deque[dict] = deque(maxlen=WINDOW_SIZE)
recent_labels: deque[str] = deque(maxlen=STABLE_COUNT)
model = None
label_names: dict[str, str] = {}
last_play_label = None
last_play_time = 0.0


def load_model() -> bool:
    global model, label_names
    if not MODEL_PATH.exists():
        print(f"❌ 模型不存在: {MODEL_PATH}")
        print("可以先用 --mock 预览流程；训练好后再正式连接手套。")
        return False
    with MODEL_PATH.open("rb") as f:
        pack = pickle.load(f)
    model = pack["model"] if isinstance(pack, dict) and "model" in pack else pack
    if LABELS_PATH.exists():
        label_names = {str(k): str(v) for k, v in json.loads(LABELS_PATH.read_text(encoding="utf-8")).items()}
    print(f"✅ 模型加载完成: {MODEL_PATH}")
    print(f"✅ 标签: {label_names}")
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


def notification_handler(_characteristic, data: bytearray):
    text = data.decode("utf-8", errors="ignore")
    for line in text.split("\n"):
        parsed = parse_sensor_line(line)
        if parsed and parsed.get("hand") == "R":
            right_queue.append(parsed)


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


def predict_label() -> tuple[str, float] | None:
    if model is None or len(right_queue) < max(8, WINDOW_SIZE // 2):
        return None
    X = extract_sequence_features(list(right_queue))
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(X)[0]
        idx = int(np.argmax(probs))
        label = str(model.classes_[idx])
        conf = float(probs[idx])
    else:
        label = str(model.predict(X)[0])
        conf = 1.0
    if label == "0" or conf < THRESHOLD:
        return None
    return label, conf


def play_audio_for_label(label: str):
    global last_play_label, last_play_time
    now = time.time()
    if label == last_play_label and now - last_play_time < COOLDOWN_SEC:
        return
    audio_path = AUDIO_MAP.get(label)
    if not audio_path or not audio_path.exists():
        print(f"\n⚠️ 找不到标签 {label} 对应音频: {audio_path}")
        return
    text = TEXT_MAP.get(label, label_names.get(label, label))
    print(f"\n🔊 播放手语翻译：{text}")
    print(f"   文件：{audio_path.name}")
    winsound.PlaySound(str(audio_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    last_play_label = label
    last_play_time = now


def stable_trigger(label: str) -> bool:
    recent_labels.append(label)
    if len(recent_labels) < STABLE_COUNT:
        return False
    c = Counter(recent_labels)
    top, count = c.most_common(1)[0]
    return top == label and count >= STABLE_COUNT


async def prepare_windows_ble():
    if not sys.platform.startswith("win"):
        return
    try:
        from bleak.backends.winrt.util import uninitialize_sta, allow_sta
        try:
            uninitialize_sta()
        except Exception:
            pass
        try:
            allow_sta()
        except Exception:
            pass
    except Exception:
        pass


async def run_ble(right_addr: str):
    from bleak import BleakClient, BleakScanner
    if not load_model():
        return
    await prepare_windows_ble()
    print(f"🔗 连接右手 BLE {right_addr}...")
    dev = await BleakScanner.find_device_by_address(right_addr, timeout=12.0)
    if not dev:
        print(f"❌ 找不到右手 BLE: {right_addr}")
        return
    client = BleakClient(dev, timeout=12.0)
    await client.connect()
    print("✅ 右手 BLE 已连接")
    await client.start_notify(BLE_UUID, notification_handler)
    print("✅ 已订阅右手传感器通知")
    print("\n实时检测手语中。识别稳定后会自动播放电脑音频。Ctrl+C 退出。\n")
    try:
        while True:
            await asyncio.sleep(PREDICT_INTERVAL)
            pred = predict_label()
            if not pred:
                continue
            label, conf = pred
            name = label_names.get(label, label)
            sys.stdout.write(f"\r🖐️ 预测: {name} 置信度={conf:.0%}   ")
            sys.stdout.flush()
            if stable_trigger(label):
                play_audio_for_label(label)
    except KeyboardInterrupt:
        print("\n停止")
    finally:
        try:
            if client.is_connected:
                await client.stop_notify(BLE_UUID)
                await client.disconnect()
        except Exception:
            pass
        print("🔌 BLE 已断开")


async def run_mock():
    print("=== Mock 预览：不需要模型，不需要手套 ===")
    print("输入 1/2/3 直接播放对应音频，q 退出。")
    print("1 = 住院交费")
    print("2 = 不用担心陪你")
    print("3 = 去办手续")
    while True:
        choice = input("选择> ").strip().lower()
        if choice in {"q", "quit", "exit"}:
            break
        if choice in AUDIO_MAP:
            play_audio_for_label(choice)
        else:
            print("无效输入")


def main():
    parser = argparse.ArgumentParser(description="手语识别触发电脑播放对应音频")
    parser.add_argument("--right", default=RIGHT_GLOVE_ADDR, help="右手 BLE 地址")
    parser.add_argument("--mock", action="store_true", help="不连接手套，手动输入标签预览播放逻辑")
    args = parser.parse_args()
    if args.mock:
        asyncio.run(run_mock())
    else:
        asyncio.run(run_ble(args.right))


if __name__ == "__main__":
    main()
