# -*- coding: utf-8 -*-
"""
Wav2Vec2 + MLP 语音情感识别训练脚本
基于预训练 Wav2Vec2-base 提取深度语音表示，再接轻量分类头

作者：王晨旭 | 2026-04-11
数据集：RAVDESS（1440 条，5 类情绪）
训练集/测试集：80% / 20%
预期训练精度：90%+

依赖：pip install transformers torch librosa soundfile scikit-learn numpy tqdm
"""

import warnings
warnings.filterwarnings("ignore")

import os, sys, glob
import io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import torch  # 必须在 @torch.no_grad() 装饰器之前 import
import numpy as np
import librosa
import soundfile
import pickle
from tqdm import tqdm

# ============================================================
# 配置
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "dataset", "Actor_*", "*.wav")
SAVE_DIR = os.path.join(BASE_DIR, "saved_model")
os.makedirs(SAVE_DIR, exist_ok=True)

EMOTION_MAP = {
    '01': 'neutral',
    '02': 'calm',
    '03': 'happy',
    '04': 'sad',
    '05': 'angry',
    '06': 'fearful',
    '07': 'disgust',
    '08': 'surprised',
}
OBSERVED_EMOTIONS = ['calm', 'happy', 'sad', 'angry', 'fearful']
EMOTION_COLORS = {
    'calm':     '#14b8a6',
    'happy':    '#22c55e',
    'sad':      '#3b82f6',
    'angry':    '#ef4444',
    'fearful':  '#f97316',
}
EMOTION_CN = {
    'calm':     '平静',
    'happy':    '快乐',
    'sad':      '悲伤',
    'angry':    '愤怒',
    'fearful':  '恐惧',
}


# ============================================================
# 第一步：加载音频文件
# ============================================================
def load_audio_paths():
    """收集所有音频路径"""
    files = glob.glob(DATASET_DIR)
    print(f"\n[1/4] 发现 {len(files)} 条音频文件")
    return files


def parse_label(file_path):
    """从文件名解析情绪标签"""
    basename = os.path.basename(file_path)
    parts = basename.split("-")
    code = parts[2]
    emotion = EMOTION_MAP.get(code, None)
    if emotion not in OBSERVED_EMOTIONS:
        return None
    return emotion


# ============================================================
# 第二步：加载 Wav2Vec2 模型（特征提取器）
# ============================================================
def load_feature_extractor():
    """加载 Wav2Vec2 特征提取器（预训练，不微调，推理用）"""
    print("\n[2/4] 加载 Wav2Vec2-Base 预训练模型（约需下载 400MB）...")
    from transformers import AutoFeatureExtractor, AutoModel
    import torch

    model_name = "facebook/wav2vec2-base"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"    设备: {device.upper()}")

    feature_extractor = AutoFeatureExtractor.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name).to(device)
    model.eval()

    print("    Wav2Vec2 模型加载完成！")
    return feature_extractor, model, device


@torch.no_grad()
def extract_wav2vec2_features(audio_path, feature_extractor, model, device):
    """用 Wav2Vec2 提取768维语音嵌入向量"""
    import torch

    # librosa 加载，统一 16kHz
    audio, sr = librosa.load(audio_path, sr=16000)

    # 静默处理（< 0.5s 跳过）
    if len(audio) < 8000:
        return None

    # 转为 tensor
    inputs = feature_extractor(
        audio, sampling_rate=16000,
        return_tensors="pt", padding=True
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    # 前向传播
    outputs = model(**inputs)

    # Mean pooling：将所有帧的768维向量取平均
    last_hidden = outputs.last_hidden_state  # (1, T, 768)
    embedding = last_hidden.mean(dim=1).squeeze().cpu().numpy()  # (768,)
    return embedding


# ============================================================
# 第三步：批量提取所有音频的嵌入向量
# ============================================================
def extract_all_features(audio_paths, feature_extractor, model, device):
    """批量提取所有音频的 Wav2Vec2 特征"""
    features, labels = [], []

    print("\n[3/4] 批量提取 Wav2Vec2 嵌入向量（无 GPU 约需 5-10 分钟）...")
    print("    提示：这是最耗时的步骤，但只需运行一次！\n")

    for i, path in enumerate(tqdm(audio_paths, desc="    提取进度")):
        emotion = parse_label(path)
        if emotion is None:
            continue

        feat = extract_wav2vec2_features(path, feature_extractor, model, device)
        if feat is not None:
            features.append(feat)
            labels.append(emotion)

    features = np.array(features)
    print(f"\n    ✅ 提取完成！有效样本：{len(features)} 条")
    print(f"    特征维度：{features.shape[1]}（Wav2Vec2 768维嵌入）")
    return features, labels


# ============================================================
# 第四步：训练 MLP 分类器
# ============================================================
def train_classifier(features, labels):
    """训练多层感知机分类器"""
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler, LabelEncoder
    from sklearn.neural_network import MLPClassifier
    from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
    import seaborn as sns
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import json

    print("\n[4/4] 训练 MLP 分类器...")

    # 标签编码
    le = LabelEncoder()
    y = le.fit_transform(labels)
    y_names = le.classes_

    # 标准化
    scaler = StandardScaler()
    X = scaler.fit_transform(features)

    # 划分训练/测试集
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"    训练集：{len(X_train)} 条 | 测试集：{len(X_test)} 条")

    # 搭建 MLP
    mlp = MLPClassifier(
        hidden_layer_sizes=(256, 128, 64),
        activation='relu',
        solver='adam',
        alpha=0.001,           # L2 正则化，防止过拟合
        batch_size=32,
        learning_rate='adaptive',
        learning_rate_init=0.001,
        max_iter=300,
        early_stopping=True,   # 早停：验证集精度不再提升时自动停止
        validation_fraction=0.1,
        n_iter_no_change=15,
        random_state=42,
        verbose=True,
    )

    print("\n    开始训练 MLP（自动早停）...")
    mlp.fit(X_train, y_train)

    # 评估
    train_acc = accuracy_score(y_train, mlp.predict(X_train))
    test_acc = accuracy_score(y_test, mlp.predict(X_test))

    print(f"\n    ╔═══════════════════════════════════╗")
    print(f"    ║  🎯 训练集准确率：{train_acc*100:.2f}%          ║")
    print(f"    ║  🎯 测试集准确率：{test_acc*100:.2f}%          ║")
    print(f"    ╚═══════════════════════════════════╝")

    # 分类报告
    print("\n    分类报告（测试集）：")
    print(classification_report(
        y_test, mlp.predict(X_test),
        target_names=[EMOTION_CN[n] for n in y_names]
    ))

    # 混淆矩阵
    cm = confusion_matrix(y_test, mlp.predict(X_test))
    plt.figure(figsize=(8, 6))
    sns.heatmap(
        cm, annot=True, fmt='d',
        xticklabels=[EMOTION_CN[n] for n in y_names],
        yticklabels=[EMOTION_CN[n] for n in y_names],
        cmap='Blues'
    )
    plt.title(f'混淆矩阵 (准确率 {test_acc*100:.1f}%)')
    plt.xlabel('预测')
    plt.ylabel('真实')
    plt.tight_layout()
    cm_path = os.path.join(SAVE_DIR, "confusion_matrix.png")
    plt.savefig(cm_path, dpi=150)
    print(f"\n    混淆矩阵已保存：{cm_path}")

    # 保存模型
    model_data = {
        "mlp": mlp,
        "scaler": scaler,
        "label_encoder": le,
        "test_acc": test_acc,
        "train_acc": train_acc,
    }
    model_path = os.path.join(SAVE_DIR, "emotion_mlp.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(model_data, f)
    print(f"\n    ✅ 模型已保存：{model_path}")

    # 保存配置
    config = {
        "feature_dim": features.shape[1],
        "num_classes": len(y_names),
        "classes": list(y_names),
        "train_acc": float(train_acc),
        "test_acc": float(test_acc),
        "emotion_cn": EMOTION_CN,
        "emotion_colors": EMOTION_COLORS,
    }
    config_path = os.path.join(SAVE_DIR, "model_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"    ✅ 配置已保存：{config_path}")

    return mlp, scaler, le, test_acc


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  🎙️ Wav2Vec2 + MLP 语音情感识别训练")
    print("=" * 60)

    # 1. 加载数据
    audio_paths = load_audio_paths()

    # 2. 加载特征提取器
    feature_extractor, model, device = load_feature_extractor()

    # 3. 提取特征
    features, labels = extract_all_features(audio_paths, feature_extractor, model, device)

    # 4. 训练分类器
    mlp, scaler, le, test_acc = train_classifier(features, labels)

    print("\n" + "=" * 60)
    print("  ✅ 训练全部完成！")
    print(f"  测试集准确率：{test_acc*100:.2f}%")
    print(f"  模型路径：{SAVE_DIR}\\emotion_mlp.pkl")
    print(f"  下一步：运行 voice_demo.py 打开网页 demo")
    print("=" * 60)
