# -*- coding: utf-8 -*-
"""train_sequence_deep_model.py
可选的更大序列模型：PyTorch 1D-CNN。输入为双手 16 维时间序列，不再只用统计特征。
如果没有安装 torch，请继续用 train_deep_gesture_model.py 的 MLP 版本。
"""
import argparse,pickle
from pathlib import Path
import numpy as np,pandas as pd
FEATURE=['R_Thumb','R_Index','R_Middle','R_Ring','R_Pinky','R_aX','R_aY','R_gZ','L_Thumb','L_Index','L_Middle','L_Ring','L_Pinky','L_aX','L_aY','L_gZ']
BASE=Path(__file__).resolve().parent
try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader,TensorDataset
except Exception as e:
    torch=None; TORCH_ERR=e
class CNN1D(nn.Module):
    def __init__(self,n_class):
        super().__init__(); self.net=nn.Sequential(nn.Conv1d(16,64,5,padding=2),nn.ReLU(),nn.Conv1d(64,128,5,padding=2),nn.ReLU(),nn.AdaptiveAvgPool1d(1)); self.fc=nn.Linear(128,n_class)
    def forward(self,x): return self.fc(self.net(x).squeeze(-1))
def resample(arr,T=80):
    if len(arr)==T: return arr
    old=np.linspace(0,1,len(arr)); new=np.linspace(0,1,T); out=np.zeros((T,arr.shape[1]),dtype=np.float32)
    for i in range(arr.shape[1]): out[:,i]=np.interp(new,old,arr[:,i])
    return out
def load(data,T=80):
    X=[]; y=[]
    for p in sorted(Path(data).glob('*.csv')):
        df=pd.read_csv(p,encoding='utf-8-sig')
        if any(c not in df.columns for c in FEATURE): print('跳过',p.name); continue
        X.append(resample(df[FEATURE].astype(float).values,T).T); y.append(str(df['label'].iloc[0]))
    if not X: raise FileNotFoundError('没有可训练 CSV')
    labels=sorted(set(y)); mp={v:i for i,v in enumerate(labels)}
    return np.stack(X).astype('float32'),np.array([mp[v] for v in y],dtype='int64'),labels
def main():
    if torch is None: raise RuntimeError(f'未安装 torch，不能训练 CNN：{TORCH_ERR}')
    ap=argparse.ArgumentParser(); ap.add_argument('--data',default=str(BASE/'dataset_deep')); ap.add_argument('--output',default=str(BASE/'gesture_cnn_model.pt')); ap.add_argument('--epochs',type=int,default=80); a=ap.parse_args()
    X,y,labels=load(a.data); mean=X.mean(axis=(0,2),keepdims=True); std=X.std(axis=(0,2),keepdims=True)+1e-6; X=(X-mean)/std
    ds=TensorDataset(torch.tensor(X),torch.tensor(y)); dl=DataLoader(ds,batch_size=min(16,len(ds)),shuffle=True)
    model=CNN1D(len(labels)); opt=torch.optim.Adam(model.parameters(),lr=1e-3); loss_fn=nn.CrossEntropyLoss()
    for ep in range(1,a.epochs+1):
        total=0
        for xb,yb in dl:
            opt.zero_grad(); loss=loss_fn(model(xb),yb); loss.backward(); opt.step(); total+=float(loss)
        if ep%10==0 or ep==1: print(f'epoch {ep}/{a.epochs} loss={total/len(dl):.4f}')
    torch.save({'state_dict':model.state_dict(),'labels':labels,'feature_order':FEATURE,'mean':mean,'std':std,'T':80},a.output)
    print('✅ CNN 模型已保存',a.output)
if __name__=='__main__': main()
