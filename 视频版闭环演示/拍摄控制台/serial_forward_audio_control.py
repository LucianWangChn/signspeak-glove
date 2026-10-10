# -*- coding: utf-8 -*-
import argparse
import socket
import sys
import time
import select
import re
import threading
import queue
from pathlib import Path

try:
    import winsound
except Exception:
    winsound = None

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9001
SENSOR_RE = re.compile(r"(?:R:)?\s*Thumb[:=](\d+)\s*,\s*Index[:=](\d+)\s*,\s*Middle[:=](\d+)", re.I)

BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "audio_output"
AUDIO_MAP = {
    "thumb": (AUDIO_DIR / "01_hospital_payment.wav", "妈，医生建议住院，我们现在去交费，可以吗？"),
    "index": (AUDIO_DIR / "02_dont_worry.wav", "妈，钱不用担心。我已经请好假了，可以陪您一起。"),
    "middle": (AUDIO_DIR / "03_go_paperwork.wav", "走，办手续去。"),
}

stop_flag = False
send_enabled = True
cmd_queue: "queue.Queue[str]" = queue.Queue()
last_values = {"thumb": 0, "index": 0, "middle": 0}
last_trigger_time = {"thumb": 0.0, "index": 0.0, "middle": 0.0}


def now():
    return time.strftime("%H:%M:%S")


def decode_bytes(data: bytes) -> str:
    for enc in ("utf-8", "gbk", "latin1"):
        try:
            return data.decode(enc)
        except Exception:
            pass
    return data.decode("utf-8", errors="replace")


def stop_audio():
    if winsound:
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass


def play_audio(key: str):
    path, label = AUDIO_MAP[key]
    print(f"\n[{now()}] 🔊 {key} 触发，播放：{label}")
    print(f"  {path.name}")
    if winsound and path.exists():
        stop_audio()
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    elif winsound:
        print(f"⚠️ 音频不存在：{path}，用提示音占位")
        winsound.Beep(880, 300)
    else:
        print("⚠️ 当前环境不可用 winsound，无法播放 WAV")


def handle_sensor_values(thumb: int, index: int, middle: int, threshold: int, debounce: float):
    global last_values, last_trigger_time
    current = {"thumb": thumb, "index": index, "middle": middle}
    print(f"[{now()}] Thumb={thumb} Index={index} Middle={middle}")
    t = time.time()
    for key, value in current.items():
        prev = last_values.get(key, 0)
        if prev <= threshold < value:
            if t - last_trigger_time.get(key, 0.0) >= debounce:
                last_trigger_time[key] = t
                play_audio(key)
        last_values[key] = value


def keyboard_loop():
    global stop_flag
    print("\n键盘控制：1=伤心水母/行吧/conflict；2=开心水母/行吧听你的；s=停止音频；q=退出")
    while not stop_flag:
        try:
            cmd = input("控制> ").strip().lower()
        except EOFError:
            break
        if cmd in {"q", "quit", "exit"}:
            stop_flag = True
            cmd_queue.put("__quit__")
            break
        if cmd == "s":
            stop_audio()
            print("已停止音频")
            continue
        if cmd in {"1", "2", "m1", "m2"}:
            if not send_enabled:
                print("当前禁用了反向发送；如需用 1/2 控 OLED，请不要加 --disable-send。")
                continue
            normalized = "1" if cmd in {"1", "m1"} else "2"
            cmd_queue.put(normalized)
        else:
            print("只支持 1 / 2 / s / q")


def send_to_serial_helper(sock: socket.socket, cmd: str):
    # 强兼容：有些助手/蓝牙模块需要换行或 T: 前缀才会透传/触发。
    payloads = [cmd, cmd + "\n", cmd + "\r\n", "T:" + cmd + "\n"]
    ok = 0
    last_error = None
    for text in payloads:
        try:
            sock.sendall(text.encode("ascii"))
            ok += 1
            time.sleep(0.08)
        except Exception as exc:
            last_error = exc
            break
    if ok:
        print(f"\n[{now()}] 📤 已通过 TCP→串口助手→蓝牙发送命令：{cmd}  包数={ok}")
    else:
        print(f"\n[{now()}] ⚠️ 命令发送失败：{last_error}")


def run_client(args):
    global stop_flag, send_enabled
    send_enabled = not bool(args.disable_send)
    threading.Thread(target=keyboard_loop, daemon=True).start()
    while not stop_flag:
        try:
            print(f"[{now()}] 连接串口助手 TCP Server {args.host}:{args.port} ...")
            with socket.create_connection((args.host, args.port), timeout=10) as sock:
                print(f"[{now()}] ✅ 已连接串口助手。开始读取转发数据。")
                print("当前模式：读取串口→网络数据；键盘 1/2 会经 TCP→串口助手→蓝牙 反向控制 OLED。")
                print("注意：keepalive 默认关闭；蓝牙断开后需要在串口助手里重新点连接。")
                sock.setblocking(False)
                text_buffer = ""
                last_keepalive = time.time()
                while not stop_flag:
                    # 处理键盘命令
                    if send_enabled:
                        try:
                            while True:
                                cmd = cmd_queue.get_nowait()
                                if cmd == "__quit__":
                                    stop_flag = True
                                    break
                                send_to_serial_helper(sock, cmd)
                        except queue.Empty:
                            pass
                    else:
                        try:
                            while True:
                                cmd = cmd_queue.get_nowait()
                                if cmd == "__quit__":
                                    stop_flag = True
                                    break
                        except queue.Empty:
                            pass

                    # 保活默认关闭：实际测试中它不能维持蓝牙存活，且可能增加断开概率。
                    if args.keepalive > 0 and time.time() - last_keepalive >= args.keepalive:
                        try:
                            sock.sendall(b"\n")
                            print(f"[{now()}] ↔ keepalive")
                        except Exception as exc:
                            print(f"[{now()}] ⚠️ keepalive 失败：{exc}")
                            break
                        last_keepalive = time.time()

                    r, _, _ = select.select([sock], [], [], 0.2)
                    if not r:
                        continue
                    data = sock.recv(4096)
                    if not data:
                        print(f"[{now()}] ⚠️ 串口助手关闭连接")
                        break
                    text = decode_bytes(data)
                    text_buffer += text
                    # 避免一段 buffer 太长；保留最近文本用于跨包解析。
                    text_buffer = text_buffer[-2000:]
                    for m in SENSOR_RE.finditer(text_buffer):
                        thumb, index, middle = map(int, m.groups())
                        handle_sensor_values(thumb, index, middle, args.threshold, args.debounce)
                    # 如果一包一行，解析完后清一下，避免重复打印同一条。
                    if "\n" in text_buffer or "\r" in text_buffer:
                        tail = re.split(r"[\r\n]+", text_buffer)[-1]
                        text_buffer = tail
        except KeyboardInterrupt:
            stop_flag = True
            break
        except Exception as exc:
            print(f"[{now()}] ⚠️ 连接/读取异常：{type(exc).__name__}: {exc}")

        if not stop_flag:
            print(f"[{now()}] 2 秒后重连...")
            time.sleep(2)

    stop_audio()
    print("已退出。")


def main():
    parser = argparse.ArgumentParser(description="通过串口助手 TCP 转发读取手套数据并触发音频；默认允许反向发送 1/2 控 OLED")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--threshold", type=int, default=800, help="手指上升沿阈值")
    parser.add_argument("--debounce", type=float, default=0.8, help="同一手指防抖秒数")
    parser.add_argument("--keepalive", type=float, default=0.0, help="每隔多少秒向串口助手发一个空行保活；0=关闭。默认关闭，因为实测不能保持蓝牙存活。")
    parser.add_argument("--disable-send", action="store_true", help="禁用通过 TCP 反向发送 1/2；默认允许发送，用于控制 OLED。")
    args = parser.parse_args()
    run_client(args)


if __name__ == "__main__":
    main()
