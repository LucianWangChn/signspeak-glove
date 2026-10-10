# -*- coding: utf-8 -*-
"""
demo_main.py
智能情绪反馈手套 - 综合演示主程序（BLE稳定/无乱码版）

功能：
1. 右手 BLE 连接与重连
2. 手动情绪区域下发：PH/PL/NH/NL/CF/UK/NT
3. OLED 文本下发：T:文字\n
说明：
- 当前硬件通信是 BLE，不使用串口 COM。
- Windows 下强制 UTF-8 stdout/stderr，避免中文乱码。
"""

import argparse
import asyncio
import io
import sys
from datetime import datetime

if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

RIGHT_BLE_ADDR = "00:00:00:00:00:00"

from pathlib import Path
BASE_DIR = Path(__file__).parent.parent
VOICE_DIR = BASE_DIR / "声音识别"
sys.path.insert(0, str(VOICE_DIR))

from ble_glove_controller import BleGloveController


class EmotionTester:
    def __init__(self, glove: BleGloveController):
        self.glove = glove
        self.zone_map = {
            "1": ("PH", "积极高唤醒"),
            "2": ("PL", "积极低唤醒"),
            "3": ("NH", "消极高唤醒"),
            "4": ("NL", "消极低唤醒"),
            "5": ("CF", "冲突表达"),
            "6": ("UK", "不确定"),
            "7": ("NT", "中性"),
        }

    async def interactive_loop(self):
        print("\n🎭 情绪反馈测试")
        print("输入数字切换情绪区域，或输入 t:文字 显示在 OLED。")
        for k, (code, name) in self.zone_map.items():
            print(f"  {k} = {code} ({name})")
        print("  r = 重新连接 BLE")
        print("  q = 退出\n")

        while True:
            choice = await asyncio.get_event_loop().run_in_executor(None, input, "情绪> ")
            choice = choice.strip()
            if not choice:
                continue
            if choice.lower() == "q":
                break
            if choice.lower() == "r":
                await self.glove.reconnect()
                continue
            if choice.startswith("t:") or choice.startswith("T:"):
                await self.glove.send_text(choice[2:])
                continue
            if choice in self.zone_map:
                code, name = self.zone_map[choice]
                print(f"🎭 切换到: {code} ({name})")
                ok1 = await self.glove.send_zone_and_text(code, name)
                ok2 = True
                if not (ok1 and ok2):
                    print("⚠️  本次发送失败，可输入 r 重新连接后再试。")
                continue
            await self.glove.send_text(choice)


async def scan_devices():
    from bleak import BleakScanner
    print("🔍 扫描 BLE 设备（10秒）...")
    devices = await BleakScanner.discover(timeout=10.0)
    for d in devices:
        print(f"  [{d.address}] {d.name or '未知'}")


async def main():
    parser = argparse.ArgumentParser(description="智能情绪反馈手套 - 综合演示（BLE稳定版）")
    parser.add_argument("--right", "--right-ble", dest="right", default=RIGHT_BLE_ADDR, help="右手 BLE 地址")
    parser.add_argument("--scan", action="store_true", help="扫描 BLE 设备")
    args = parser.parse_args()

    if args.scan:
        await scan_devices()
        return

    print("=" * 55)
    print("🧤 智能情绪反馈手套 - 综合演示（BLE稳定版）")
    print("=" * 55)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"右手 BLE: {args.right}")
    print("说明: 当前版本不使用串口 COM。")
    print()

    glove = BleGloveController(args.right)
    await glove.connect()
    tester = EmotionTester(glove)
    try:
        await tester.interactive_loop()
    finally:
        await glove.disconnect()
        print("👋 演示结束")


if __name__ == "__main__":
    asyncio.run(main())
