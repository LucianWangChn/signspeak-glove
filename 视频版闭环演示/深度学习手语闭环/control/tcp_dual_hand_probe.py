# -*- coding: utf-8 -*-
"""
tcp_dual_hand_probe.py

用于测试 right_315m_ble_min_rx.ino 输出的 R:/L: 双手数据。
从串口助手 TCP Server 读取数据，统计右手/左手帧数，并提示左手 315M 是否收到。

运行：
  python tcp_dual_hand_probe.py
  python tcp_dual_hand_probe.py --host 127.0.0.1 --port 9001
"""

import argparse
import re
import socket
import time

SENSOR_RE = re.compile(
    r"([RL]):Thumb:([-\d.]+),Index:([-\d.]+),Middle:([-\d.]+),Ring:([-\d.]+),"
    r"Pinky:([-\d.]+),aX:([-\d.]+),aY:([-\d.]+),gZ:([-\d.]+)"
)


def decode_bytes(data: bytes) -> str:
    for enc in ("utf-8", "gbk", "latin1"):
        try:
            return data.decode(enc)
        except Exception:
            pass
    return data.decode("utf-8", errors="replace")


def parse_line(line: str):
    m = SENSOR_RE.search(line)
    if not m:
        return None
    hand = m.group(1)
    vals = list(map(float, m.groups()[1:]))
    names = ["Thumb", "Index", "Middle", "Ring", "Pinky", "aX", "aY", "gZ"]
    return hand, dict(zip(names, vals))


def is_nonzero_left(values: dict) -> bool:
    return any(abs(values.get(k, 0.0)) > 0.01 for k in values)


def main():
    ap = argparse.ArgumentParser(description="测试 TCP 转发中的 R/L 双手数据")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9001)
    ap.add_argument("--seconds", type=float, default=20.0)
    args = ap.parse_args()

    print(f"连接 {args.host}:{args.port} ...")
    counts = {"R": 0, "L": 0}
    left_nonzero = 0
    latest = {"R": None, "L": None}
    buf = ""
    start = time.time()
    last_report = 0.0

    with socket.create_connection((args.host, args.port), timeout=10) as sock:
        sock.settimeout(1.0)
        print("✅ 已连接，开始读取。Ctrl+C 可提前退出。")
        while time.time() - start < args.seconds:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            if not data:
                print("⚠️ TCP 连接关闭")
                break

            buf += decode_bytes(data)
            parts = re.split(r"[\r\n]+", buf)
            buf = parts[-1]

            for line in parts[:-1]:
                parsed = parse_line(line)
                if not parsed:
                    continue
                hand, values = parsed
                counts[hand] += 1
                latest[hand] = values
                if hand == "L" and is_nonzero_left(values):
                    left_nonzero += 1

            now = time.time() - start
            if now - last_report >= 1.0:
                last_report = now
                print(f"R帧={counts['R']:4d}  L帧={counts['L']:4d}  L非零={left_nonzero:4d}")

    print("\n===== 结果 =====")
    print(f"右手 R 帧数：{counts['R']}")
    print(f"左手 L 帧数：{counts['L']}")
    print(f"左手非零帧：{left_nonzero}")
    if counts["R"] == 0:
        print("❌ 没收到右手数据：检查 BLE/串口助手/TCP 转发。")
    elif counts["L"] == 0:
        print("⚠️ 没有 L 行：右手 ino 可能不是 right_315m_ble_min_rx，或输出被截断。")
    elif left_nonzero == 0:
        print("⚠️ 有 L 行但全是 0：右手没收到左手 315M，有可能左手没开、频率/接线/包结构不匹配。")
    else:
        print("✅ 左手 315M 数据已进入右手，并通过 TCP 转发到电脑。")

    if latest["R"]:
        print("最新 R:", latest["R"])
    if latest["L"]:
        print("最新 L:", latest["L"])


if __name__ == "__main__":
    main()
