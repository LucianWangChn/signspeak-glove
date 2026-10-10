# -*- coding: utf-8 -*-
"""
finger_trigger_audio_feedback.py
拍摄专用：用手指阈值触发电脑播放台词，同时可发送 1/2 控制 OLED + 振动。

逻辑：
- 大拇指 Thumb > 800 的上升沿：播放第一句
- 食指 Index > 800 的上升沿：播放第二句
- 中指 Middle > 800 的上升沿：播放第三句
- 只在上升沿触发一次；保持大于 800 不会重复触发
- 新触发会打断当前音频，立即播放新音频
- 键盘输入 1/2：通过 BLE 或串口发送到 Arduino，执行当前 OLED + 振动逻辑

运行示例：
    python finger_trigger_audio_feedback.py
    python finger_trigger_audio_feedback.py --threshold 800
    python finger_trigger_audio_feedback.py --serial COM6
    python finger_trigger_audio_feedback.py --command-mode serial --serial COM6

依赖：
    pip install bleak
可选串口：
    pip install pyserial
"""

import argparse
import asyncio
import io
import re
import sys
import threading
import time
import winsound
from pathlib import Path
from typing import Optional

if sys.platform.startswith("win"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

RIGHT_GLOVE_ADDR = "00:00:00:00:00:00"
BLE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "audio_output"
AUDIO_MAP = {
    "thumb": AUDIO_DIR / "01_hospital_payment.wav",
    "index": AUDIO_DIR / "02_dont_worry.wav",
    "middle": AUDIO_DIR / "03_go_paperwork.wav",
}
TEXT_MAP = {
    "thumb": "妈，医生建议住院，我们现在去交费，可以吗？",
    "index": "妈，钱不用担心。我已经请好假了，可以陪您一起。",
    "middle": "走，办手续去。",
}
FIELD_MAP = {
    "thumb": "Thumb",
    "index": "Index",
    "middle": "Middle",
}

latest_values = {"Thumb": 0.0, "Index": 0.0, "Middle": 0.0}
above_state = {"thumb": False, "index": False, "middle": False}
last_trigger_time = {"thumb": 0.0, "index": 0.0, "middle": 0.0}

ble_client = None
serial_obj = None
command_queue: asyncio.Queue[str] | None = None
notify_pause_event: asyncio.Event | None = None


def parse_sensor_line(line: str) -> Optional[dict]:
    line = line.strip()
    if not line:
        return None
    if line.startswith("R:") or line.startswith("L:"):
        line = line[2:]
    data = {}
    for part in line.split(","):
        m = re.match(r"(\w+):(-?\d+(?:\.\d+)?)", part.strip())
        if m:
            data[m.group(1)] = float(m.group(2))
    if not any(k in data for k in ["Thumb", "Index", "Middle"]):
        return None
    return data


def stop_audio():
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass


def play_audio(trigger_name: str):
    path = AUDIO_MAP.get(trigger_name)
    if not path or not path.exists():
        print(f"\n⚠️ 找不到音频文件: {path}")
        return
    text = TEXT_MAP.get(trigger_name, trigger_name)
    stop_audio()
    print(f"\n🔊 {trigger_name} 触发，播放：{text}")
    print(f"   {path.name}")
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)


def handle_values(data: dict, threshold: float, debounce_sec: float):
    now = time.time()
    for name, field in FIELD_MAP.items():
        if field not in data:
            continue
        value = float(data[field])
        latest_values[field] = value
        is_above = value > threshold
        was_above = above_state[name]

        # 上升沿：之前没有超过阈值，现在超过阈值
        if is_above and not was_above:
            if now - last_trigger_time[name] >= debounce_sec:
                play_audio(name)
                last_trigger_time[name] = now
        above_state[name] = is_above


def notification_handler_factory(threshold: float, debounce_sec: float):
    def handler(_characteristic, data: bytearray):
        if notify_pause_event is not None and notify_pause_event.is_set():
            return
        text = data.decode("utf-8", errors="ignore")
        for line in text.split("\n"):
            parsed = parse_sensor_line(line)
            if parsed:
                handle_values(parsed, threshold, debounce_sec)
    return handler


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


async def dump_ble_services(client):
    """打印当前设备暴露的 GATT 服务/特征，方便排查 UUID 是否变化。"""
    try:
        services = client.services
        print("\n=== 当前 BLE GATT 特征列表 ===")
        for service in services:
            print(f"Service: {service.uuid}")
            for ch in service.characteristics:
                props = ",".join(ch.properties or [])
                print(f"  Char: {ch.uuid}  [{props}]")
        print("=== GATT 列表结束 ===\n")
    except Exception as exc:
        print(f"\n⚠️ 读取 GATT 服务列表失败: {exc}")


async def start_notify_with_retry(client, uuid: str, handler, retries: int = 10, interval: float = 0.8) -> bool:
    """Windows/BLE 连接刚建立时服务表可能还没就绪，重试 start_notify。"""
    last_error = None
    for i in range(1, retries + 1):
        try:
            await client.start_notify(uuid, handler)
            print(f"✅ 已订阅传感器通知: {uuid}")
            return True
        except Exception as exc:
            last_error = exc
            msg = str(exc)
            if "was not found" in msg or "not found" in msg or exc.__class__.__name__.endswith("NotFoundError"):
                print(f"⏳ GATT 特征还没就绪，等待后重试 {i}/{retries}...")
                await asyncio.sleep(interval)
                continue
            print(f"⚠️ start_notify 失败: {exc}")
            await asyncio.sleep(interval)
    print(f"❌ 多次重试后仍找不到 BLE 特征: {uuid}")
    print(f"最后错误: {last_error}")
    await dump_ble_services(client)
    return False


async def send_ble_command(cmd: str):
    global ble_client
    if ble_client is None:
        print("\n⚠️ BLE client 不存在，无法发送命令")
        return

    # 注意：Windows/Bleak 有时通知仍在正常接收，但 is_connected 会短暂/错误显示 False。
    # 所以这里不再用 is_connected 提前拦截，而是直接尝试写入；失败时再提示真实错误。
    try:
        connected_state = getattr(ble_client, "is_connected", "unknown")
    except Exception:
        connected_state = "unknown"

    payloads = [
        cmd.encode("ascii"),
        (cmd + "\n").encode("ascii"),
        (cmd + "\r\n").encode("ascii"),
        ("T:" + cmd + "\n").encode("ascii"),
    ]

    ok_count = 0
    last_error = None
    for payload in payloads:
        try:
            await ble_client.write_gatt_char(BLE_UUID, payload, response=False)
            ok_count += 1
            await asyncio.sleep(0.12)
            continue
        except Exception as exc:
            last_error = exc
        try:
            await ble_client.write_gatt_char(BLE_UUID, payload, response=True)
            ok_count += 1
            await asyncio.sleep(0.12)
        except Exception as exc:
            last_error = exc

    if ok_count > 0:
        print(f"\n📤 已通过 BLE 发送 OLED/振动命令：{cmd}  成功包数={ok_count}  is_connected={connected_state}")
    else:
        print(f"\n⚠️ BLE 写入失败：{last_error}  is_connected={connected_state}")
        print("   如果仍能接收 Thumb/Index/Middle，说明通知通道还在，但写通道被 Windows/BLE 模块拒绝；可临时用 --serial COMx --no-ble-write 走 USB 串口发送 1/2。")

def send_serial_command(cmd: str):
    global serial_obj
    if not serial_obj:
        print("\n⚠️ 未启用串口，无法串口发送")
        return
    try:
        for s in [cmd, cmd + "\n", "T:" + cmd + "\n"]:
            serial_obj.write(s.encode("ascii"))
            serial_obj.flush()
            time.sleep(0.08)
        print(f"\n📤 已通过串口发送 OLED/振动命令：{cmd}")
    except Exception as exc:
        print(f"\n⚠️ 串口发送失败: {exc}")


def keyboard_thread(loop: asyncio.AbstractEventLoop, command_mode: str):
    global command_queue
    print("\n键盘控制：输入 1/2 控制手套 OLED+振动；输入 s 停止当前音频；q 退出。")
    print(f"命令发送模式：{command_mode}")
    while True:
        try:
            cmd = input("控制> ").strip().lower()
        except EOFError:
            break
        if cmd in {"q", "quit", "exit"}:
            loop.call_soon_threadsafe(loop.stop)
            break
        if cmd == "s":
            stop_audio()
            print("已停止音频")
            continue
        if cmd not in {"1", "2", "m1", "m2"}:
            print("只支持 1 / 2 / s / q")
            continue
        normalized = "1" if cmd in {"1", "m1"} else "2"

        # 纯 BLE 拍摄版：发命令前先暂停处理 notify，给 Arduino SoftwareSerial 留出接收空档。
        if command_mode in {"ble", "both"}:
            try:
                loop.call_soon_threadsafe(notify_pause_event.set)
            except Exception:
                pass
            time.sleep(0.35)

        if command_mode == "serial":
            send_serial_command(normalized)
        elif command_mode == "both":
            send_serial_command(normalized)
            if command_queue is not None:
                loop.call_soon_threadsafe(command_queue.put_nowait, normalized)
        else:
            if command_queue is not None:
                loop.call_soon_threadsafe(command_queue.put_nowait, normalized)
            else:
                print("\n⚠️ 未启用 BLE 命令队列")


async def command_sender_loop():
    assert command_queue is not None
    while True:
        cmd = await command_queue.get()
        await send_ble_command(cmd)


async def run(args):
    global ble_client, serial_obj, command_queue, notify_pause_event
    notify_pause_event = asyncio.Event()

    if args.serial:
        try:
            import serial
            serial_obj = serial.Serial(args.serial, args.baud, timeout=0.1)
            print(f"✅ 串口已打开: {args.serial} @ {args.baud}")
        except Exception as exc:
            print(f"⚠️ 串口打开失败: {exc}")
            serial_obj = None

    from bleak import BleakClient, BleakScanner
    await prepare_windows_ble()
    print(f"🔗 连接右手 BLE {args.right}...")
    dev = await BleakScanner.find_device_by_address(args.right, timeout=12.0)
    if not dev:
        print(f"❌ 找不到右手 BLE: {args.right}")
        return

    ble_client = BleakClient(dev, timeout=12.0)
    await ble_client.connect()
    print("✅ 右手 BLE 已连接")
    print("⏳ 等待 BLE GATT 服务刷新...")
    await asyncio.sleep(2.0)
    ok = await start_notify_with_retry(
        ble_client,
        BLE_UUID,
        notification_handler_factory(args.threshold, args.debounce),
        retries=10,
        interval=0.8,
    )
    if not ok:
        print("❌ 订阅传感器通知失败，无法接收电位器数据。")
        print("建议：断开其他 BLE/串口程序，重启手套蓝牙，再重新运行脚本。")
        return

    loop = asyncio.get_running_loop()
    command_mode = args.command_mode
    if command_mode == "auto":
        # 只要提供了 USB 串口，就默认用串口发 1/2；否则才尝试 BLE 写入。
        command_mode = "serial" if serial_obj else "ble"
    if args.no_ble_write:
        command_mode = "serial"

    if command_mode in {"ble", "both"}:
        command_queue = asyncio.Queue()
        asyncio.create_task(command_sender_loop())

    threading.Thread(target=keyboard_thread, args=(loop, command_mode), daemon=True).start()

    print("\n=== 手指上升沿触发音频 ===")
    print(f"阈值: > {args.threshold}")
    print("大拇指 Thumb  -> 第一段音频")
    print("食指   Index  -> 第二段音频")
    print("中指   Middle -> 第三段音频")
    print("新触发会打断当前音频。Ctrl+C 或键盘 q 退出。\n")

    try:
        while True:
            await asyncio.sleep(0.5)
            sys.stdout.write(
                f"\rThumb={latest_values['Thumb']:.0f}  "
                f"Index={latest_values['Index']:.0f}  "
                f"Middle={latest_values['Middle']:.0f}      "
            )
            sys.stdout.flush()
    except (KeyboardInterrupt, RuntimeError):
        pass
    finally:
        stop_audio()
        try:
            if ble_client and ble_client.is_connected:
                await ble_client.stop_notify(BLE_UUID)
                await ble_client.disconnect()
        except Exception:
            pass
        try:
            if serial_obj:
                serial_obj.close()
        except Exception:
            pass
        print("\n🔌 已退出")


def main():
    parser = argparse.ArgumentParser(description="手指阈值触发电脑音频 + 发送 OLED/振动命令")
    parser.add_argument("--right", default=RIGHT_GLOVE_ADDR, help="右手 BLE 地址")
    parser.add_argument("--threshold", type=float, default=800, help="触发阈值，默认 800")
    parser.add_argument("--debounce", type=float, default=0.8, help="同一手指上升沿防抖秒数")
    parser.add_argument("--serial", default="", help="可选：串口名，如 COM6。提供后默认用串口发送 1/2，BLE 只负责接收电位器。")
    parser.add_argument("--baud", type=int, default=9600, help="串口波特率")
    parser.add_argument("--command-mode", choices=["auto", "ble", "serial", "both"], default="ble", help="1/2 命令发送方式：默认 ble；serial=只串口；both=串口+BLE；auto=有串口则串口，否则BLE")
    parser.add_argument("--no-ble-write", action="store_true", help="兼容旧参数：键盘 1/2 不走 BLE，只走串口")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
