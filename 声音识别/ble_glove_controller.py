# -*- coding: utf-8 -*-
"""
ble_glove_controller.py
右手 BLE 手套控制器（稳定版 v2）

用途：
- 给右手 Arduino BLE 主控发送 PRD 情绪区域码：PH/PL/NH/NL/CF/UK/NT
- 发送旧版情绪指令：A/C/S/F/U（兼容）
- 发送 OLED 文本：T:文字\n
稳定性改进：
1. 连接后立即 start_notify，参考手语识别模块，让 BLE 链路保持活跃。
2. 后台 keepalive 每隔数秒发送换行符；Arduino 会忽略该字符，但 BLE 链路不会长时间空闲。
3. 所有写入串行化，并设置最小写入间隔，避免连续写入压垮透传模块。
4. 断线回调记录状态，写入前自动重连；写入失败后重连并重试。
5. Windows 下调用 uninitialize_sta，规避 VS Code/GUI STA 导致的 Bleak WinRT 扫描错误。

注意：本模块不包装 sys.stdout/sys.stderr，避免与主程序重复包装导致
ValueError: I/O operation on closed file。
"""

import asyncio
import sys
import time
from typing import Optional

try:
    from bleak.backends.winrt.util import uninitialize_sta, allow_sta
except Exception:
    uninitialize_sta = None
    allow_sta = None

from bleak import BleakClient, BleakScanner

BLE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
DEFAULT_RIGHT_BLE_ADDR = "00:00:00:00:00:00"

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


class BleGloveController:
    def __init__(
        self,
        address: str = DEFAULT_RIGHT_BLE_ADDR,
        uuid: str = BLE_UUID,
        timeout: float = 12.0,
        min_write_interval: float = 0.25,
        keepalive_interval: float = 2.0,
        enable_notify: bool = True,
        enable_keepalive: bool = True,
    ):
        self.address = address
        self.uuid = uuid
        self.timeout = timeout
        self.min_write_interval = min_write_interval
        self.keepalive_interval = keepalive_interval
        self.enable_notify = enable_notify
        self.enable_keepalive = enable_keepalive

        self.client: Optional[BleakClient] = None
        self._lock = asyncio.Lock()
        self._notify_started = False
        self._keepalive_task: Optional[asyncio.Task] = None
        self._last_write_ts = 0.0
        self._rx_lines = []
        self._ready = False

    @property
    def is_connected(self) -> bool:
        return bool(self.client and self.client.is_connected)

    def _on_disconnect(self, _client):
        self._notify_started = False
        self._ready = False
        print("⚠️  [BLE] 连接已断开，下一次发送会自动重连")

    def _notification_handler(self, _sender, data: bytearray):
        """接收 Arduino 主动推送的数据。

        这里主要用于保持 BLE 链路活跃；传感器数据不在本控制器里解析。
        为避免刷屏，只缓存最近少量文本，不实时 print。
        """
        try:
            text = bytes(data).decode("utf-8", errors="ignore").strip()
        except Exception:
            text = ""
        if text:
            self._rx_lines.append(text)
            if len(self._rx_lines) > 20:
                self._rx_lines = self._rx_lines[-20:]

    async def _prepare_windows_ble(self):
        if not sys.platform.startswith("win"):
            return
        # Bleak/WinRT 在 Windows 上要求 MTA。某些库（VS Code、sounddevice、pywin32、
        # transformers 依赖链等）可能先把主线程初始化成 GUI STA，导致：
        # "Thread is configured for Windows GUI but callbacks are not working."
        # 先尝试释放 STA；若释放不了，再 allow_sta 绕过 Bleak 的 MTA 检查。
        if uninitialize_sta is not None:
            try:
                uninitialize_sta()
            except Exception:
                pass
        if allow_sta is not None:
            try:
                allow_sta()
            except Exception:
                pass

    async def connect(self) -> bool:
        if self.is_connected:
            await self._ensure_notify_and_keepalive()
            return True

        await self._prepare_windows_ble()
        print(f"🔗 [BLE] 正在查找右手 {self.address} ...", flush=True)
        device = None
        scan_timeout = min(float(self.timeout), 5.0)
        # 优先用 discover 手动扫描。它和手语识别脚本的 notify 链路更接近，
        # 也能避免 find_device_by_address 在部分 Windows 环境里一直卡住。
        for attempt in range(2):
            try:
                devices = await asyncio.wait_for(BleakScanner.discover(timeout=scan_timeout), timeout=scan_timeout + 3.0)
                target = self.address.upper()
                for d in devices:
                    if (d.address or "").upper() == target:
                        device = d
                        break
                if device:
                    print(f"✅ [BLE] 已发现右手 {self.address}", flush=True)
                    break
                print(f"⚠️  [BLE] 第 {attempt + 1} 次扫描未发现右手，准备重试...", flush=True)
            except Exception as exc:
                msg = str(exc)
                if "Thread is configured for Windows GUI" in msg and allow_sta is not None:
                    print("⚠️  [BLE] 检测到 Windows STA 线程问题，启用 allow_sta 后重试扫描...", flush=True)
                    try:
                        allow_sta()
                    except Exception:
                        pass
                else:
                    print(f"⚠️  [BLE] 第 {attempt + 1} 次扫描异常: {exc}", flush=True)
            await asyncio.sleep(0.5)

        if not device:
            print(f"❌ [BLE] 找不到右手设备: {self.address}", flush=True)
            print("提示：如果蓝牙灯已慢闪，可能是被另一个程序/窗口占用；请关掉手语识别、串口监视器、旧 Python 进程后重试。", flush=True)
            return False

        self.client = BleakClient(device, timeout=self.timeout, disconnected_callback=self._on_disconnect)
        try:
            print("🔌 [BLE] 正在建立 GATT 连接...", flush=True)
            await asyncio.wait_for(self.client.connect(), timeout=min(float(self.timeout), 8.0))
        except asyncio.TimeoutError:
            print("⚠️  [BLE] GATT 连接等待超时，但蓝牙灯已慢闪时通常说明系统层已连接。", flush=True)
            print("   将检查当前连接状态；若仍未完成，会释放本次连接，程序继续启动。", flush=True)
        except Exception as exc:
            print(f"❌ [BLE] 连接失败: {exc}", flush=True)
            self.client = None
            return False

        if not self.client or not self.client.is_connected:
            print("❌ [BLE] 连接后状态异常/未完成；请确认没有手语识别脚本或旧 Python 进程占用该 BLE。", flush=True)
            try:
                if self.client:
                    await self.client.disconnect()
            except Exception:
                pass
            self.client = None
            return False

        print("✅ [BLE] 右手已连接", flush=True)
        await self._wait_for_services_ready()
        await self._ensure_notify_and_keepalive()
        return True

    async def _wait_for_services_ready(self, max_wait: float = 8.0) -> bool:
        """等待 BLE 模块完成 GATT 服务发现。

        有些 Windows/BLE 透传模块在 client.connect() 返回时灯刚开始慢闪，
        此时服务表还没完全准备好；立即 start_notify/write 会误报 characteristic not found。
        """
        deadline = time.monotonic() + max_wait
        last_error = None
        while time.monotonic() < deadline:
            try:
                services = self.client.services
                if services is None:
                    try:
                        services = await self.client.get_services()
                    except AttributeError:
                        services = None
                chars = []
                if services is not None:
                    for service in services:
                        for char in service.characteristics:
                            chars.append(str(char.uuid).lower())
                if self.uuid.lower() in chars:
                    self._ready = True
                    print(f"✅ [BLE] GATT 服务已就绪: {self.uuid}", flush=True)
                    await asyncio.sleep(0.5)
                    return True
                last_error = f"未发现特征 {self.uuid}，当前特征: {chars[:6]}"
            except Exception as exc:
                last_error = str(exc)
            print("⏳ [BLE] 等待 GATT 服务就绪...", flush=True)
            await asyncio.sleep(1.0)
        self._ready = False
        print(f"⚠️  [BLE] GATT 服务等待超时: {last_error}", flush=True)
        return False

    async def _ensure_notify_and_keepalive(self):
        if not self.is_connected:
            return
        if not self._ready:
            await self._wait_for_services_ready()

        if self.enable_notify and not self._notify_started and self._ready:
            try:
                await self.client.start_notify(self.uuid, self._notification_handler)
                self._notify_started = True
                print("✅ [BLE] 已订阅右手通知，连接保持活跃")
            except Exception as exc:
                # 有些 BLE 透传模块不暴露 notify；不中断主流程，keepalive 仍可改善稳定性。
                self._notify_started = False
                print(f"⚠️  [BLE] 通知订阅失败，继续使用写入+心跳模式: {exc}")

        if self.enable_keepalive and (self._keepalive_task is None or self._keepalive_task.done()):
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def _keepalive_loop(self):
        while True:
            await asyncio.sleep(self.keepalive_interval)
            if not self.is_connected:
                continue
            try:
                # 发送换行作为保活。Arduino parseBLE 会读取但忽略，不改变情绪状态。
                async with self._lock:
                    await self._write_locked(b"\n", retry=0, silent=True)
            except Exception:
                pass

    async def reconnect(self) -> bool:
        await self.disconnect(quiet=True)
        await asyncio.sleep(1.0)
        return await self.connect()

    async def disconnect(self, quiet: bool = False) -> None:
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        self._keepalive_task = None

        if self.client:
            try:
                if self.client.is_connected and self._notify_started:
                    try:
                        await self.client.stop_notify(self.uuid)
                    except Exception:
                        pass
                if self.client.is_connected:
                    await self.client.disconnect()
                    if not quiet:
                        print("🔌 [BLE] 已断开")
            finally:
                self.client = None
                self._notify_started = False
                self._ready = False

    async def _respect_write_interval(self):
        now = time.monotonic()
        wait = self.min_write_interval - (now - self._last_write_ts)
        if wait > 0:
            await asyncio.sleep(wait)

    async def _write_locked(self, data: bytes, retry: int = 1, silent: bool = False) -> bool:
        if not self.is_connected:
            ok = await self.connect()
            if not ok:
                if not silent:
                    print("⚠️  [BLE] 未连接，发送失败")
                return False

        for attempt in range(retry + 1):
            try:
                if not self._ready:
                    await self._wait_for_services_ready()
                await self._respect_write_interval()
                await self.client.write_gatt_char(self.uuid, data, response=False)
                self._last_write_ts = time.monotonic()
                return True
            except Exception as exc:
                if not silent:
                    print(f"⚠️  [BLE] 写入失败: {exc}")
                if attempt < retry:
                    if "Characteristic" in str(exc) and "not found" in str(exc):
                        self._ready = False
                        if not silent:
                            print("⏳ [BLE] 特征还没准备好，等待服务刷新后重试...")
                        await asyncio.sleep(2.0)
                        await self._wait_for_services_ready()
                    else:
                        if not silent:
                            print("🔁 [BLE] 尝试重连后重发...")
                        if not await self.reconnect():
                            return False
                else:
                    return False
        return False

    async def write(self, data: bytes, retry: int = 2, silent: bool = False) -> bool:
        async with self._lock:
            return await self._write_locked(data, retry=retry, silent=silent)

    async def send_raw(self, text: str) -> bool:
        return await self.write(str(text).encode("utf-8"))

    async def send_emotion(self, emotion_char: str) -> bool:
        cmd = (emotion_char or "C").strip().upper()[:1]
        ok = await self.write(cmd.encode("utf-8"))
        if ok:
            print(f"🚀 [BLE] 旧版情绪: {cmd}")
        return ok

    async def send_zone(self, zone: str) -> bool:
        cmd = ZONE_TO_CMD.get((zone or "NT").strip(), "NT")
        ok = await self.write(cmd.encode("utf-8"))
        if ok:
            print(f"🚀 [BLE] 情绪区域: {cmd}")
        return ok

    async def send_text(self, text: str) -> bool:
        display_text = str(text or "")[:16]
        ok = await self.write(f"T:{display_text}\n".encode("utf-8"))
        if ok:
            print(f"📝 [BLE] OLED文字: {display_text}")
        return ok

    async def send_zone_and_text(self, zone: str, text: str = "") -> bool:
        ok1 = await self.send_zone(zone)
        ok2 = True
        if text:
            ok2 = await self.send_text(text)
        return ok1 and ok2

    def latest_rx(self):
        return list(self._rx_lines)


async def _test():
    addr = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RIGHT_BLE_ADDR
    glove = BleGloveController(addr)
    if await glove.connect():
        for cmd, text in [("PH", "positive"), ("NH", "angry"), ("NL", "sad"), ("NT", "neutral")]:
            await glove.send_zone_and_text(cmd, text)
            await asyncio.sleep(2)
        await glove.disconnect()


if __name__ == "__main__":
    asyncio.run(_test())
