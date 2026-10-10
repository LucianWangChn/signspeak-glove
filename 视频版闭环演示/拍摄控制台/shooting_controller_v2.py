# -*- coding: utf-8 -*-
"""
shooting_controller_v2.py
视频拍摄专用 BLE 手套控制台 v2

适配 oled_story_jelly_sentence_demo：
- 只发送最终两字符命令，避免先发 NL/PL 导致 Arduino 提前显示别的状态。
- 支持句子页命令：P1/P2/B1/B2。
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
    "1": {"name": "妈妈担忧", "code": "TW", "hint": "先水母，后显示：妈妈有些担忧"},
    "2": {"name": "焦虑犹豫", "code": "TS", "hint": "先水母，后显示：妈妈焦虑犹豫"},
    "3": {"name": "妈妈安心", "code": "TA", "hint": "先水母，后显示：妈妈安心接受"},
    "4": {"name": "放松接受", "code": "TR", "hint": "先水母，后显示：妈妈安心接受"},
    "5": {"name": "住院交费", "code": "TP", "hint": "先水母，后显示第一句第一页"},
    "6": {"name": "陪你一起", "code": "TB", "hint": "先水母，后显示第二句第一页"},
    "7": {"name": "去办手续", "code": "TG", "hint": "先水母，后显示：走办手续去"},
    "8": {"name": "平静沟通", "code": "TC", "hint": "默认平静状态"},
    "9": {"name": "住院交费 第2页", "code": "P2", "hint": "直接显示：去交费可以吗"},
    "10": {"name": "陪你一起 第2页", "code": "B2", "hint": "直接显示：请好假陪您一起"},
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
        await asyncio.sleep(1.0)
        await client.start_notify(BLE_UUID, lambda _c, data: None)
        print("✅ 已订阅通知，连接保持活跃")
    except Exception as exc:
        print(f"⚠️ 订阅通知失败，但仍尝试写入: {exc}")
    return client


async def send_code(client, code: str):
    payload = (code.strip() + "\n").encode("ascii", errors="ignore")
    await client.write_gatt_char(BLE_UUID, payload, response=False)
    await asyncio.sleep(0.15)
    print(f"✅ 已发送 BLE 命令：{code}")


async def main_async(args):
    client = await connect_right(args.right)
    try:
        while True:
            print("\n=== 视频拍摄控制台 v2 ===")
            for key, item in PRESETS.items():
                print(f"{key}. {item['name']} [{item['code']}] - {item['hint']}")
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
            try:
                await send_code(client, PRESETS[choice]["code"])
            except Exception as exc:
                print(f"❌ 发送失败，尝试重连: {exc}")
                try:
                    await client.disconnect()
                except Exception:
                    pass
                client = await connect_right(args.right)
                await send_code(client, PRESETS[choice]["code"])
    finally:
        try:
            if client and client.is_connected:
                await client.disconnect()
        except Exception:
            pass
        print("🔌 BLE 已断开")


def main():
    parser = argparse.ArgumentParser(description="视频拍摄专用 BLE 手套控制台 v2")
    parser.add_argument("--right", default=RIGHT_GLOVE_ADDR, help="右手 BLE 地址")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
