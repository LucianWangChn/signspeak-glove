# -*- coding: utf-8 -*-
"""
blink3state_oled_control.py

配合 right_ble_oled_stable_full_sensors_blink3state.ino 使用。
通过串口助手 TCP Server 反向发送 0/1/2 到手套：
  0 = 待机微笑水母
  1 = 伤心水母闪烁 -> 行吧 + conflict 振动
  2 = 开心水母快闪 -> 行吧听你的 + 增强振动

前提：串口助手开启 TCP Server，并允许“网络 -> 串口/蓝牙”转发。
默认连接 127.0.0.1:9001。
"""

import argparse
import socket
import time

PAYLOADS = {
    "0": [b"0", b"0\n", b"T:0\n"],
    "1": [b"1", b"1\n", b"T:1\n"],
    "2": [b"2", b"2\n", b"T:2\n"],
}

DESC = {
    "0": "待机：微笑水母",
    "1": "行吧：伤心水母闪烁 + conflict 振动",
    "2": "行吧听你的：开心水母快闪 + 增强振动",
}


def send_cmd(sock: socket.socket, cmd: str, repeat: int = 2, gap: float = 0.08):
    payloads = PAYLOADS[cmd]
    total = 0
    for _ in range(repeat):
        for p in payloads:
            sock.sendall(p)
            total += 1
            time.sleep(gap)
    print(f"✅ 已发送 {cmd}：{DESC[cmd]}  payloads={total}")


def main():
    parser = argparse.ArgumentParser(description="0/1/2 三状态 OLED 水母控制台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument("--repeat", type=int, default=2, help="每次命令重复发送几轮，默认 2")
    args = parser.parse_args()

    print(f"连接串口助手 TCP Server {args.host}:{args.port} ...")
    with socket.create_connection((args.host, args.port), timeout=10) as sock:
        print("✅ 已连接")
        print("\n按键：")
        print("  0 = 待机微笑水母")
        print("  1 = 伤心水母 + 行吧")
        print("  2 = 开心水母 + 行吧听你的")
        print("  q = 退出\n")

        while True:
            cmd = input("输入 0/1/2/q > ").strip().lower()
            if cmd in {"q", "quit", "exit"}:
                break
            if cmd not in PAYLOADS:
                print("请输入 0、1、2 或 q")
                continue
            send_cmd(sock, cmd, repeat=args.repeat)

    print("已退出")


if __name__ == "__main__":
    main()
