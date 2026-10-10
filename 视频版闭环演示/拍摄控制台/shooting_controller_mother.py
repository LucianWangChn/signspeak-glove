# -*- coding: utf-8 -*-
"""
shooting_controller_mother.py
妈妈台词 OLED 拍摄控制台 - 最简版

只保留：
1 = 伤心水母 -> 行吧
2 = 开心水母 -> 行吧听你的
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
    "1": ("1", "伤心水母 -> 行吧"),
    "2": ("2", "开心水母 -> 行吧听你的"),
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
    print(f"正在连接右手 BLE {addr} ...")
    dev = await BleakScanner.find_device_by_address(addr, timeout=12.0)
    if not dev:
        raise RuntimeError(f"找不到右手 BLE: {addr}")
    client = BleakClient(dev, timeout=12.0)
    await client.connect()
    print("右手 BLE 已连接")
    try:
        await asyncio.sleep(1.2)
        await client.start_notify(BLE_UUID, lambda _c, data: None)
        print("通知订阅完成")
    except Exception as exc:
        print(f"通知订阅失败，继续尝试写入: {exc}")
    return client


async def write_payload(client, payload: bytes):
    await client.write_gatt_char(BLE_UUID, payload, response=False)
    await asyncio.sleep(0.18)
    try:
        await client.write_gatt_char(BLE_UUID, payload, response=True)
        await asyncio.sleep(0.18)
    except Exception:
        pass


async def send_code_strong(client, code: str):
    code = code.strip().upper()
    payloads = [
        code.encode("ascii"),
        (code + "\n").encode("ascii"),
        (code + "\r\n").encode("ascii"),
        ("T:" + code + "\n").encode("ascii"),
    ]
    for payload in payloads:
        await write_payload(client, payload)
    print(f"已发送：{code}")


async def main_async(args):
    client = await connect_right(args.right)
    try:
        while True:
            print("\n=== 妈妈台词 OLED 控制台 ===")
            for key, (_code, name) in PRESETS.items():
                print(f"{key}. {name}")
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
                print(f"发送失败，尝试重连: {exc}")
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
        print("BLE 已断开")


def main():
    parser = argparse.ArgumentParser(description="妈妈台词 OLED 拍摄控制台")
    parser.add_argument("--right", default=RIGHT_GLOVE_ADDR, help="右手 BLE 地址")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
