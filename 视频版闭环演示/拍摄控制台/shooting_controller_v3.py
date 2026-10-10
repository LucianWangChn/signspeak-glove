# -*- coding: utf-8 -*-
"""
shooting_controller_v3.py
视频拍摄专用 BLE 手套控制台 v3 - 强发送/诊断版

改进：
- 每次命令发送多种格式：CODE、CODE\n、CODE\r\n、T:CODE\n。
- write_gatt_char 同时尝试 response=False 和 response=True。
- 适合排查 PC->BLE->Arduino 方向是否通。
"""

import argparse
import asyncio
import io
import sys

if sys.platform.startswith("win"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

RIGHT_GLOVE_ADDR = "00:00:00:00:00:00"
BLE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

PRESETS = {
    "1": ("TW", "妈妈担忧"),
    "2": ("TS", "焦虑犹豫"),
    "3": ("TA", "妈妈安心"),
    "4": ("TR", "放松接受"),
    "5": ("TP", "住院交费"),
    "6": ("TB", "陪你一起"),
    "7": ("TG", "去办手续"),
    "8": ("TC", "平静沟通"),
    "9": ("P2", "住院交费第2页"),
    "10": ("B2", "陪你一起第2页"),
}


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


async def connect_right(addr: str):
    await prepare_windows_ble()
    from bleak import BleakClient, BleakScanner
    print(f"🔗 正在连接右手 BLE {addr} ...")
    dev = await BleakScanner.find_device_by_address(addr, timeout=12.0)
    if not dev:
        raise RuntimeError(f"找不到右手 BLE: {addr}")
    client = BleakClient(dev, timeout=12.0)
    await client.connect()
    print("✅ 右手 BLE 已连接")
    try:
        await asyncio.sleep(1.2)
        await client.start_notify(BLE_UUID, lambda _c, data: None)
        print("✅ 已订阅通知，连接保持活跃")
    except Exception as exc:
        print(f"⚠️ 订阅通知失败，但仍尝试写入: {exc}")
    return client


async def write_payload(client, payload: bytes):
    # 先用无响应写，兼容透传模块。
    await client.write_gatt_char(BLE_UUID, payload, response=False)
    await asyncio.sleep(0.18)
    # 再尝试响应写；有些模块不支持，失败不影响。
    try:
        await client.write_gatt_char(BLE_UUID, payload, response=True)
        await asyncio.sleep(0.18)
    except Exception as exc:
        print(f"  response=True 跳过: {exc}")


async def send_code_strong(client, code: str):
    code = code.strip().upper()
    payloads = [
        code.encode("ascii"),
        (code + "\n").encode("ascii"),
        (code + "\r\n").encode("ascii"),
        ("T:" + code + "\n").encode("ascii"),
    ]
    for p in payloads:
        print(f"  -> {p!r}")
        await write_payload(client, p)
    print(f"✅ 强发送完成：{code}")


async def main_async(args):
    client = await connect_right(args.right)
    try:
        while True:
            print("\n=== 视频拍摄控制台 v3 强发送版 ===")
            for k, (code, name) in PRESETS.items():
                print(f"{k}. {name} [{code}]")
            print("r. 重新连接")
            print("q. 退出")
            choice = input("选择> ").strip().lower()
            if choice in {"q", "quit", "exit"}:
                break
            if choice == "r":
                try:
                    await client.disconnect()
                except Exception:
                    pass
                client = await connect_right(args.right)
                continue
            if choice not in PRESETS:
                print("无效选择")
                continue
            code, _name = PRESETS[choice]
            try:
                await send_code_strong(client, code)
            except Exception as exc:
                print(f"❌ 发送失败，尝试重连: {exc}")
                try:
                    await client.disconnect()
                except Exception:
                    pass
                client = await connect_right(args.right)
                await send_code_strong(client, code)
    finally:
        try:
            if client and client.is_connected:
                await client.disconnect()
        except Exception:
            pass
        print("🔌 BLE 已断开")


def main():
    parser = argparse.ArgumentParser(description="视频拍摄 BLE 控制台 v3 强发送版")
    parser.add_argument("--right", default=RIGHT_GLOVE_ADDR, help="右手 BLE 地址")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
