# -*- coding: utf-8 -*-
"""
ble_send_once.py

声音识别专用的一次性 BLE 发送脚本。

设计原则：尽量照搬手语识别 ble_gesture_predict.py / ble_gesture_collector.py 的稳定连接方式：
1. 在函数内部导入 bleak
2. BleakScanner.find_device_by_address 查找设备
3. BleakClient(dev, timeout=12.0)
4. await client.connect()
5. start_notify 订阅通知
6. write_gatt_char(response=False) 发送
7. disconnect 断开

它由主程序 subprocess 调用，独立于 sounddevice / transformers / requests 等复杂依赖，
避免声音识别主进程污染 Windows Bleak/WinRT 状态。
"""

import argparse
import asyncio
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BLE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
DEFAULT_ADDR = "00:00:00:00:00:00"
ZONE_TO_CMD = {
    "positive_high": "PH",
    "positive_low": "PL",
    "negative_high": "NH",
    "negative_low": "NL",
    "conflict": "CF",
    "unknown": "UK",
    "neutral": "NT",
    "PH": "PH",
    "PL": "PL",
    "NH": "NH",
    "NL": "NL",
    "CF": "CF",
    "UK": "UK",
    "NT": "NT",
}


def notification_handler(_sender, _data: bytearray):
    # 只用于保持链路行为与手语识别脚本一致，不在这里刷屏。
    return


async def send_once(address: str, zone: str, text: str, timeout: float = 12.0) -> bool:
    # 关键：和手语识别脚本一样，在真正运行函数内部导入 bleak。
    from bleak import BleakClient, BleakScanner

    cmd = ZONE_TO_CMD.get((zone or "NT").strip(), "NT")
    display_text = str(text or "")[:16]

    print(f"🔗 连接右手 BLE {address}...", flush=True)
    dev = await BleakScanner.find_device_by_address(address, timeout=timeout)
    if not dev:
        print(f"❌ 找不到右手设备 {address}", flush=True)
        return False

    client = BleakClient(dev, timeout=timeout)
    try:
        await client.connect()
        print("✅ 右手 BLE 已连接", flush=True)

        try:
            await client.start_notify(BLE_UUID, notification_handler)
            print("✅ 已订阅右手通知", flush=True)
        except Exception as exc:
            # 有些透传模块允许写但通知订阅偶发失败，发送仍可继续。
            print(f"⚠️ 通知订阅失败，继续发送: {exc}", flush=True)

        await client.write_gatt_char(BLE_UUID, cmd.encode("utf-8"), response=False)
        print(f"🚀 已发送情绪区域: {cmd}", flush=True)
        await asyncio.sleep(0.25)

        if display_text:
            safe_text = display_text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
            payload = f"T:{safe_text}\n".encode("utf-8", errors="ignore")
            await client.write_gatt_char(BLE_UUID, payload, response=False)
            print(f"📝 已发送 OLED 文字: {safe_text}", flush=True)
            await asyncio.sleep(0.25)

        return True
    finally:
        try:
            if client.is_connected:
                try:
                    await client.stop_notify(BLE_UUID)
                except Exception:
                    pass
                await client.disconnect()
                print("🔌 BLE 已断开", flush=True)
        except Exception:
            pass


async def main():
    parser = argparse.ArgumentParser(description="一次性 BLE 情绪反馈发送")
    parser.add_argument("--addr", default=DEFAULT_ADDR)
    parser.add_argument("--zone", default="NT")
    parser.add_argument("--text", default="")
    parser.add_argument("--timeout", type=float, default=12.0)
    args = parser.parse_args()

    ok = await send_once(args.addr, args.zone, args.text, args.timeout)
    raise SystemExit(0 if ok else 2)


if __name__ == "__main__":
    asyncio.run(main())
