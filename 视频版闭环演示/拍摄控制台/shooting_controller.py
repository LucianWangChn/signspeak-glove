# -*- coding: utf-8 -*-
"""
shooting_controller.py
视频拍摄专用 BLE 手套控制台

用途：拍摄医院剧情时，场外同学按键触发手套 OLED 中文状态与震动反馈。
协议建议：
- TW: 担忧 / 长震
- TS: 焦虑 / 长震
- TA: 安心 / 两短震
- TR: 放松 / 两短震
- TC: 平静 / 轻反馈
- TO: 接受 / 两短震

如果当前 Arduino 还没支持 TW/TA 等中文状态码，本脚本也会同步发送兼容 PRD 区域码：
- negative_low / NL
- positive_low / PL
- neutral / NT
"""

import argparse
import asyncio
import io
import sys
from pathlib import Path

if sys.platform.startswith("win"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

RIGHT_GLOVE_ADDR = "00:00:00:00:00:00"
BLE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

PRESETS = {
    "1": {"name": "担忧", "code": "TW", "zone": "NL", "hint": "母亲：行……吧…… / 长震"},
    "2": {"name": "焦虑", "code": "TS", "zone": "NH", "hint": "压力/犹豫增强 / 长震或急促震"},
    "3": {"name": "安心", "code": "TA", "zone": "PL", "hint": "母亲：行吧！听你的！ / 两短震"},
    "4": {"name": "放松", "code": "TR", "zone": "PL", "hint": "安抚后放松 / 两短震"},
    "5": {"name": "平静", "code": "TC", "zone": "NT", "hint": "中性状态 / 轻反馈"},
    "6": {"name": "接受", "code": "TO", "zone": "PL", "hint": "接受建议 / 两短震"},
}


def safe_text(s: str) -> str:
    return str(s).encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")


async def connect_right(addr: str):
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


async def send_line(client, line: str):
    payload = (line.strip() + "\n").encode("utf-8", errors="ignore")
    await client.write_gatt_char(BLE_UUID, payload, response=False)
    await asyncio.sleep(0.12)


async def send_preset(client, item: dict):
    # 先发 PRD 区域码，兼容已有 right_ble_master 逻辑。
    await send_line(client, item["zone"])
    # 再发中文显示状态码，供新版 OLED 中文点阵程序使用。
    await send_line(client, item["code"])
    # 再发一行英文兜底，供旧 OLED 文本程序显示。
    await send_line(client, "T:" + item["code"])
    print(f"✅ 已发送：{item['name']}  code={item['code']} zone={item['zone']}  用途：{item['hint']}")


async def main_async(args):
    client = await connect_right(args.right)
    try:
        while True:
            print("\n=== 视频拍摄控制台 ===")
            for key, item in PRESETS.items():
                print(f"{key}. {item['name']}  [{item['code']} / {item['zone']}]  {item['hint']}")
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
                await send_preset(client, PRESETS[choice])
            except Exception as exc:
                print(f"❌ 发送失败，尝试重连: {exc}")
                try:
                    await client.disconnect()
                except Exception:
                    pass
                client = await connect_right(args.right)
                await send_preset(client, PRESETS[choice])
    finally:
        try:
            if client and client.is_connected:
                await client.disconnect()
        except Exception:
            pass
        print("🔌 BLE 已断开")


def main():
    parser = argparse.ArgumentParser(description="视频拍摄专用 BLE 手套控制台")
    parser.add_argument("--right", default=RIGHT_GLOVE_ADDR, help="右手 BLE 地址")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
