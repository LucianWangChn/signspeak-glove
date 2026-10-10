# -*- coding: utf-8 -*-
"""
原版 vocie_llm_combination.py 的 PRD + BLE 可用版。

来源：<LOCAL_PROJECT_PATH>
目标：<LOCAL_PROJECT_PATH>

改动：
1. 继续使用原版 voice_demo.py / saved_model / Baidu ASR / Spark LLM，不使用 v3。
2. 串口 GloveController 改为 BLE：向右手主控发送 A/C/S 和 PRD 区域码 PH/PL/NH/NL/CF/UK/NT。
3. 加入简化 PRD 决策法庭：输出 courtState + finalEmotionZone。
4. Windows 控制台 UTF-8 修复，避免中文乱码。
"""

import asyncio
import base64
import io
import os
import sys
import time
import subprocess
import shlex
import warnings
warnings.filterwarnings("ignore")

# 强制 HuggingFace/Transformers 离线加载本地缓存，避免演示现场因网络失败崩溃。
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

# Windows 控制台 UTF-8 修复：不要重新包一层 TextIOWrapper，避免 stdout 被提前关闭。
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np
import requests
import sounddevice as sd
import soundfile as sf


# 直接导入同目录原版 voice_demo，使用原本已训练好的 Wav2Vec2 + MLP。
import voice_demo

# ============================================================
# 配置
# ============================================================
RIGHT_BLE_ADDR = "00:00:00:00:00:00"

BAIDU_AK = __import__('os').environ.get('SIGNSPEAK_BAIDU_AK', '')
BAIDU_SK = __import__('os').environ.get('SIGNSPEAK_BAIDU_SK', '')
SPARK_PWD = "gWeMluADmkjpUNSojhhL:WlAvVRhFVRXhQlPKRXNm"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_WAV = os.path.join(BASE_DIR, "temp_fusion.wav")
BLE_WORKER = os.path.join(BASE_DIR, "ble_worker.py")
_ble_proc = None


def sanitize_ble_text(value, limit: int = 16) -> str:
    """清洗发给 BLE/OLED 的文本，去掉代理项等无法 UTF-8 编码的字符。"""
    s = str(value or "")
    s = s.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
    s = s.replace("\r", " ").replace("\n", " ").replace("|", " ")
    return s[:limit]


def start_ble_worker():
    """启动独立 BLE 后台进程。

    后台进程连接方式参考手语识别脚本，并保持连接不断开。主进程只通过 stdin
    发送 `ZONE|TEXT`，避免每轮识别都重复 GATT connect。
    """
    global _ble_proc
    if _ble_proc and _ble_proc.poll() is None:
        return _ble_proc
    cmd = [sys.executable, BLE_WORKER, "--addr", RIGHT_BLE_ADDR]
    try:
        _ble_proc = subprocess.Popen(
            cmd,
            cwd=BASE_DIR,
            stdin=subprocess.PIPE,
            stdout=None,
            stderr=None,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        print("✅ BLE 后台进程已启动；连接方式参考手语识别脚本。", flush=True)
    except Exception as exc:
        print(f"⚠️  BLE 后台进程启动失败: {exc}", flush=True)
        _ble_proc = None
    return _ble_proc


def send_ble_feedback(zone: str, display_text: str) -> bool:
    proc = start_ble_worker()
    if not proc or not proc.stdin or proc.poll() is not None:
        print("⚠️  BLE 后台进程不可用，跳过本次硬件反馈。", flush=True)
        return False
    line = f"{zone or 'NT'}|{sanitize_ble_text(display_text)}\n"
    try:
        proc.stdin.write(line)
        proc.stdin.flush()
        return True
    except Exception as exc:
        print(f"⚠️  BLE 命令写入后台进程失败: {exc}", flush=True)
        return False


def stop_ble_worker():
    global _ble_proc
    proc = _ble_proc
    _ble_proc = None
    if not proc:
        return
    try:
        if proc.poll() is None and proc.stdin:
            proc.stdin.write("QUIT\n")
            proc.stdin.flush()
    except Exception:
        pass
    try:
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass


async def wait_for_enter(prompt: str = "👉 按【回车】开始录音 (说出模拟台词)..."):
    """异步等待回车，避免阻塞事件循环。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, input, prompt)


# ============================================================
# 左脑：ASR + LLM
# ============================================================
def get_baidu_token():
    url = (
        "https://aip.baidubce.com/oauth/2.0/token"
        f"?grant_type=client_credentials&client_id={BAIDU_AK}&client_secret={BAIDU_SK}"
    )
    return requests.post(url, timeout=15).json().get("access_token")


def asr_process(audio_file, token):
    with open(audio_file, "rb") as f:
        audio_data = f.read()
    audio_base64 = base64.b64encode(audio_data).decode("utf-8")
    url = "https://vop.baidu.com/server_api"
    payload = {
        "format": "wav",
        "rate": 16000,
        "channel": 1,
        "cuid": "glove_dual_brain",
        "token": token,
        "speech": audio_base64,
        "len": len(audio_data),
        "dev_pid": 1537,
    }
    try:
        res = requests.post(url, json=payload, timeout=20).json()
        return res["result"][0] if res.get("err_no") == 0 else "Error"
    except Exception as exc:
        print(f"⚠️ ASR失败: {exc}")
        return "Error"


def llm_process(text):
    url = "https://spark-api-open.xf-yun.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {SPARK_PWD}", "Content-Type": "application/json"}
    prompt = f"""你是一个专业的医疗情感分析AI。请分析患者家属的话语，判断其真实情绪，并严格按要求输出控制指令（绝对只输出单个字母，不要解释）：

【指令映射表】
C - 平静/正面：打招呼、询问、喜悦、感谢。
A - 急躁/高压：愤怒、焦急、害怕、不耐烦、质问。
S - 悲伤/低落：伤心、绝望、无助。

【学习案例】
话语："Hello hello，你能听见吗？" -> 输出：C
话语："太好了，终于好了。" -> 输出：C
话语："大夫，这个单子怎么交费？" -> 输出：C
话语："你到底在干什么？" -> 输出：A
话语："我怎么办？" -> 输出：A
话语："我真的好伤心。" -> 输出：S

请分析以下话语：
话语："{text}" -> 输出："""
    payload = {
        "model": "lite",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.01,
    }
    try:
        ans = requests.post(url, headers=headers, json=payload, timeout=20).json()["choices"][0]["message"]["content"].strip()
        for ch in ans:
            if ch.upper() in {"A", "C", "S"}:
                return ch.upper()
        return "C"
    except Exception as exc:
        print(f"⚠️ LLM失败: {exc}")
        return "Error"

# ============================================================
# PRD 决策法庭（基于原版输出的简化可用版）
# ============================================================
def acoustic_to_va(acoustic_label: str):
    table = {
        "happy": (0.80, 0.75),
        "calm": (0.45, 0.25),
        "neutral": (0.0, 0.25),
        "sad": (-0.75, 0.25),
        "angry": (-0.85, 0.90),
        "fearful": (-0.75, 0.85),
        "unknown": (0.0, 0.0),
    }
    return table.get(acoustic_label, (0.0, 0.0))


def semantic_to_zone(semantic_cmd: str):
    return {"C": "positive_low", "A": "negative_high", "S": "negative_low"}.get(semantic_cmd, "unknown")


def va_to_zone(valence: float, arousal: float):
    if valence >= 0.25 and arousal >= 0.55:
        return "positive_high"
    if valence >= 0.25:
        return "positive_low"
    if valence <= -0.25 and arousal >= 0.55:
        return "negative_high"
    if valence <= -0.25:
        return "negative_low"
    return "neutral"


def run_prd_court(acoustic_label: str, acoustic_score: float, semantic_cmd: str):
    semantic_cmd = semantic_cmd if semantic_cmd in {"A", "C", "S"} else "C"
    valence, arousal = acoustic_to_va(acoustic_label)
    acoustic_zone = va_to_zone(valence, arousal)
    semantic_zone = semantic_to_zone(semantic_cmd)

    # 低置信度：不确定。
    if acoustic_score < 0.35 and semantic_cmd == "C":
        return {
            "courtState": "uncertain",
            "finalEmotionZone": "unknown",
            "legacyCommand": "U",
            "reason": "声学置信度较低且语义无明显情绪",
        }

    # 原版高优先级规则 + PRD状态。
    if acoustic_label == "sad":
        return {
            "courtState": "intensified" if semantic_cmd == "S" else "conflict" if semantic_cmd == "A" else "consistent",
            "finalEmotionZone": "negative_low",
            "legacyCommand": "S",
            "reason": "右脑检测到悲伤声学特征，按悲伤优先处理",
        }

    if semantic_cmd == "A" or acoustic_label in {"angry", "fearful"}:
        state = "intensified" if semantic_zone == acoustic_zone else "consistent" if acoustic_zone == "neutral" else "conflict"
        return {
            "courtState": state,
            "finalEmotionZone": "negative_high",
            "legacyCommand": "A",
            "reason": "语义或声学触发高压/急躁报警",
        }

    if semantic_cmd == "S":
        return {
            "courtState": "consistent" if acoustic_zone in {"negative_low", "neutral"} else "conflict",
            "finalEmotionZone": "negative_low",
            "legacyCommand": "S",
            "reason": "左脑文本判断为低落情绪",
        }

    return {
        "courtState": "consistent",
        "finalEmotionZone": acoustic_zone if acoustic_zone.startswith("positive") else "positive_low" if acoustic_zone == "neutral" else acoustic_zone,
        "legacyCommand": "C",
        "reason": "整体情绪平稳或正向",
    }


async def main():
    print("正在初始化 BLE 手套...", flush=True)
    print("ℹ️  声音识别将参考手语识别方式，用独立 BLE 后台进程保持连接。", flush=True)
    start_ble_worker()

    print("=" * 60, flush=True)
    print(" 声学+语义双引擎多模态情感识别系统 - 原版PRD_BLE")
    print(" 右脑: 原版 Wav2Vec2-Base + MLP")
    print(" 左脑: Baidu ASR + 讯飞Spark LLM")
    print(" 硬件: BLE 右手主控 + PRD区域码 + OLED文字")
    print("=" * 60)

    print("\n--> 唤醒右脑 (Wav2Vec2 + MLP)...")
    voice_demo.load_my_model()

    print("--> 连接左脑 (Baidu ASR + Spark LLM)...")
    baidu_token = get_baidu_token()
    print("✅ 双脑同步完成！系统就绪。\n" + "=" * 60 + "\n")

    try:
        while True:
            await wait_for_enter("👉 按【回车】开始录音 (说出模拟台词)...")

            fs, duration = 16000, 3
            print("🔴 正在聆听...", flush=True)
            rec = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype="float32")
            sd.wait()
            sf.write(TEMP_WAV, rec, fs)
            print("✅ 录音结束，双脑开始并行思考...\n", flush=True)

            start_time = time.time()

            acoustic_res = voice_demo.recognize_emotion(TEMP_WAV)
            acoustic_result = acoustic_res["top_label"] if acoustic_res.get("success") else "unknown"
            acoustic_cn = acoustic_res.get("top_emotion", "未知")
            acoustic_score = float(acoustic_res.get("top_score", 0.0))
            print(f"🎵 [右脑-物理本能] 声带情绪: 【 {acoustic_result.upper()} ({acoustic_cn}) 】 置信度={acoustic_score:.2f}")

            text = asr_process(TEMP_WAV, baidu_token)
            semantic_result = "C"
            if text != "Error":
                print(f"🗣️  [左脑-听写转换] 捕获语义文本: 【 {text} 】")
                semantic_result = llm_process(text)
                print(f"🧠 [左脑-逻辑推理] 文字情绪指令: 【 {semantic_result} 】")
            else:
                print("🗣️  [左脑] 听写失败，跳过语义分析。")

            print("\n⚖️  --- PRD 决策法庭 ---")
            court = run_prd_court(acoustic_result, acoustic_score, semantic_result)
            print(f"🎯 最终区域: {court['finalEmotionZone']} | 旧指令: {court['legacyCommand']}")
            print(f"⚖️  状态: {court['courtState']} | 原因: {court['reason']}")

            display_text = sanitize_ble_text(text if text != "Error" else court["finalEmotionZone"])
            ok = send_ble_feedback(court["finalEmotionZone"], display_text)
            if not ok:
                print("⚠️  BLE 发送失败；语音识别主流程继续。")

            print(f"⏱️  双脑协同总耗时: {time.time() - start_time:.2f} 秒")
            print("✅ 本轮闭环完成：语音输入 → 声学识别 → ASR/LLM → PRD决策 → BLE/OLED反馈。\n", flush=True)
    finally:
        stop_ble_worker()


if __name__ == "__main__":
    asyncio.run(main())
