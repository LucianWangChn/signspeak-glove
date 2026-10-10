# -*- coding: utf-8 -*-
import argparse
import socket
import sys
import time
import select
import re

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9001

SENSOR_RE = re.compile(r"(?:R:)?\s*Thumb[:=](\d+)\s*,\s*Index[:=](\d+)\s*,\s*Middle[:=](\d+)", re.I)


def now():
    return time.strftime("%H:%M:%S")


def decode_bytes(data: bytes) -> str:
    for enc in ("utf-8", "gbk", "latin1"):
        try:
            return data.decode(enc)
        except Exception:
            pass
    return data.decode("utf-8", errors="replace")


def parse_and_print(buffer: str):
    found = False
    for m in SENSOR_RE.finditer(buffer):
        found = True
        print(f"[{now()}] PARSED Thumb={m.group(1)} Index={m.group(2)} Middle={m.group(3)}", flush=True)
    return found


def tcp_client(host: str, port: int, seconds: float):
    print(f"[{now()}] TCP Client: connecting to {host}:{port} ...", flush=True)
    with socket.create_connection((host, port), timeout=10) as sock:
        print(f"[{now()}] CONNECTED. 等待串口助手转发数据...", flush=True)
        sock.setblocking(False)
        end = time.time() + seconds
        total = 0
        text_buffer = ""
        while time.time() < end:
            r, _, _ = select.select([sock], [], [], 0.5)
            if not r:
                continue
            data = sock.recv(4096)
            if not data:
                print(f"[{now()}] SERVER_CLOSED", flush=True)
                break
            total += len(data)
            text = decode_bytes(data)
            text_buffer += text
            print(f"[{now()}] RAW {len(data)} bytes: {text!r}", flush=True)
            parse_and_print(text_buffer[-2000:])
        print(f"[{now()}] DONE total_bytes={total}", flush=True)


def tcp_server(host: str, port: int, seconds: float):
    print(f"[{now()}] TCP Server: listening on {host}:{port} ...", flush=True)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(1)
        s.settimeout(seconds)
        try:
            conn, addr = s.accept()
        except socket.timeout:
            print(f"[{now()}] TIMEOUT: 没有客户端连接。", flush=True)
            return
        with conn:
            print(f"[{now()}] CLIENT_CONNECTED {addr}. 等待数据...", flush=True)
            conn.setblocking(False)
            end = time.time() + seconds
            total = 0
            text_buffer = ""
            while time.time() < end:
                r, _, _ = select.select([conn], [], [], 0.5)
                if not r:
                    continue
                data = conn.recv(4096)
                if not data:
                    print(f"[{now()}] CLIENT_CLOSED", flush=True)
                    break
                total += len(data)
                text = decode_bytes(data)
                text_buffer += text
                print(f"[{now()}] RAW {len(data)} bytes: {text!r}", flush=True)
                parse_and_print(text_buffer[-2000:])
            print(f"[{now()}] DONE total_bytes={total}", flush=True)


def udp_server(host: str, port: int, seconds: float):
    print(f"[{now()}] UDP: listening on {host}:{port} ...", flush=True)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((host, port))
        s.setblocking(False)
        end = time.time() + seconds
        total = 0
        text_buffer = ""
        while time.time() < end:
            r, _, _ = select.select([s], [], [], 0.5)
            if not r:
                continue
            data, addr = s.recvfrom(4096)
            total += len(data)
            text = decode_bytes(data)
            text_buffer += text
            print(f"[{now()}] UDP_FROM {addr} RAW {len(data)} bytes: {text!r}", flush=True)
            parse_and_print(text_buffer[-2000:])
        print(f"[{now()}] DONE total_bytes={total}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="测试串口助手 TCP/UDP 转发是否有数据")
    parser.add_argument("--mode", choices=["client", "server", "udp"], default="client", help="client=连接串口助手TCP Server；server=等待串口助手TCP Client连接；udp=监听UDP")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--seconds", type=float, default=60)
    args = parser.parse_args()

    try:
        if args.mode == "client":
            tcp_client(args.host, args.port, args.seconds)
        elif args.mode == "server":
            tcp_server(args.host, args.port, args.seconds)
        else:
            udp_server(args.host, args.port, args.seconds)
    except KeyboardInterrupt:
        print("\n用户中断。", flush=True)
    except Exception as exc:
        print(f"[{now()}] ERROR {type(exc).__name__}: {exc}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
