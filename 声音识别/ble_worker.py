# -*- coding: utf-8 -*-
"""
ble_worker.py

声音识别专用 BLE 后台进程。

核心目标：把 BLE 从声音识别主进程中彻底隔离出去，避免 sounddevice / transformers /
requests 等依赖影响 Windows Bleak/WinRT。连接方式严格参考手语识别脚本：

    BleakScanner.find_device_by_address
    BleakClient(dev, timeout=12.0)
    await client.connect()
    await client.start_notify(BLE_UUID, handler)

主进程通过 stdin 给本进程发送命令，每行格式：
    ZONE|TEXT
例如：
    NT|hello
    NH|angry
"""

import argparse
import asyncio
import sys
from collections import deque

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

rx_lines = deque(maxlen=20)


def notification_handler(_sender, data: bytearray):
    text = data.decode("utf-8", errors="ignore").strip()
    if text:
        rx_lines.append(text)


class BLEWorker:
    def __init__(self, address: str, timeout: float = 12.0):
        self.address = address
        self.timeout = timeout
        self.client = None
        self.connected = False

    async def connect(self) -> bool:
        from bleak import BleakClient, BleakScanner

        if self.client and self.client.is_connected:
            self.connected = True
            return True

        await self.disconnect(quiet=True)

        print(f"🔗 [BLE-Worker] 连接右手 BLE {self.address}...", flush=True)
        dev = await BleakScanner.find_device_by_address(self.address, timeout=self.timeout)
        if not dev:
            print(f"❌ [BLE-Worker] 找不到右手设备 {self.address}", flush=True)
            self.connected = False
            return False

        self.client = BleakClient(dev, timeout=self.timeout)
        await self.client.connect()
        print("✅ [BLE-Worker] 右手 BLE 已连接", flush=True)

        try:
            await self.client.start_notify(BLE_UUID, notification_handler)
            print("✅ [BLE-Worker] 已订阅右手通知", flush=True)
        except Exception as exc:
            print(f"⚠️ [BLE-Worker] 通知订阅失败，继续发送: {exc}", flush=True)

        self.connected = True
        return True

    async def disconnect(self, quiet: bool = False):
        if self.client:
            try:
                if self.client.is_connected:
                    try:
                        await self.client.stop_notify(BLE_UUID)
                    except Exception:
                        pass
                    await self.client.disconnect()
                    if not quiet:
                        print("🔌 [BLE-Worker] BLE 已断开", flush=True)
            except Exception:
                pass
        self.client = None
        self.connected = False

    async def send(self, zone: str, text: str = "") -> bool:
        if not await self.connect():
            return False

        cmd = ZONE_TO_CMD.get((zone or "NT").strip(), "NT")
        display_text = str(text or "")[:16]

        try:
            await self.client.write_gatt_char(BLE_UUID, cmd.encode("utf-8"), response=False)
            print(f"🚀 [BLE-Worker] 已发送情绪区域: {cmd}", flush=True)
            await asyncio.sleep(0.25)

            if display_text:
                safe_text = display_text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
                await self.client.write_gatt_char(BLE_UUID, f"T:{safe_text}\n".encode("utf-8", errors="ignore"), response=False)
                print(f"📝 [BLE-Worker] 已发送 OLED 文字: {safe_text}", flush=True)
                await asyncio.sleep(0.25)
            return True
        except Exception as exc:
            print(f"⚠️ [BLE-Worker] 写入失败: {exc}，准备重连", flush=True)
            await self.disconnect(quiet=True)
            return False


async def stdin_reader(queue: asyncio.Queue):
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if line == "":
            await queue.put(None)
            return
        await queue.put(line.rstrip("\n"))


async def main():
    parser = argparse.ArgumentParser(description="声音识别 BLE 后台发送进程")
    parser.add_argument("--addr", default=DEFAULT_ADDR)
    parser.add_argument("--timeout", type=float, default=12.0)
    args = parser.parse_args()

    worker = BLEWorker(args.addr, args.timeout)
    queue = asyncio.Queue()
    reader_task = asyncio.create_task(stdin_reader(queue))

    # 启动后先尝试连接一次；失败也不退出，后续收到命令会继续重试。
    try:
        await worker.connect()
    except Exception as exc:
        print(f"⚠️ [BLE-Worker] 初始连接失败: {exc}", flush=True)

    print("✅ [BLE-Worker] 已启动，等待主程序命令", flush=True)

    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            item = item.strip()
            if not item:
                continue
            if item.upper() in {"QUIT", "EXIT"}:
                break
            if "|" in item:
                zone, text = item.split("|", 1)
            else:
                zone, text = item, ""
            try:
                ok = await worker.send(zone, text)
                print(f"[BLE-Worker] SEND_OK={ok}", flush=True)
            except Exception as exc:
                print(f"[BLE-Worker] SEND_OK=False ERROR={exc}", flush=True)
    finally:
        reader_task.cancel()
        await worker.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
