import asyncio
import sys
from bleak import BleakClient, BleakScanner

# 解决控制台输出中文乱码
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 右手手套蓝牙精确物理证书
DEVICE_ADDRESS = "00:00:00:00:00:00" 

# 刚刚通过 Service Scan 精准扒出来的满血透传格子
WRITE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

async def main():
    print(f"🛰️ [BLE] Step 1: Pre-scanning to lock target [{DEVICE_ADDRESS}]...")
    
    # 核心升级：先寻找空气中的手套设备，确保物理链路存活
    device = await BleakScanner.find_device_by_address(DEVICE_ADDRESS, timeout=10.0)
    
    if not device:
        print(f"❌ ERROR: Cannot find device {DEVICE_ADDRESS} via radio scan.")
        print("💡 [排查提示]：")
        print("1. 请断开手机 App 连接，确保右手蓝牙模块 LED 正在【疯狂闪烁】！")
        print("2. 7.4V 电池盒开关是否打开？供电是否正常？")
        return

    print("🎯 [BLE] Target found and locked! Step 2: Establishing GATT session...")
    
    try:
        # 使用扫描到的特定 device 对象发起连接，成功率接近 100%
        async with BleakClient(device, timeout=5.0) as client:
            if client.is_connected:
                print("====================================================")
                print("✅ 成功！Python 已经跨越 BLE 协议栈实现完美合体！")
                print("====================================================")
                print("[💥 现场确认] 快看右手主机！蓝牙红灯是否瞬间【常亮】了？！")
                
                # 向特征值 ffe1 写入单字节大写字母 'A'
                print(f"[DATA] Injected command 'A' into characteristic [{WRITE_UUID}]...")
                await client.write_gatt_char(WRITE_UUID, b'A')
                
                print("[HARDWARE] 右手马达应当立刻开始 3 秒狂震，OLED 屏幕变脸愤怒表情！")
                
                # 保持连接 3 秒让马达震完
                await asyncio.sleep(3)
                print("[BLE] Session closed safely.")
            else:
                print("❌ FAILED: Found device, but GATT handshake rejected.")
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())