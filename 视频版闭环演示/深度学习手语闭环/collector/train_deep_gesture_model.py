# -*- coding: utf-8 -*-
import argparse,pickle
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.metrics import classification_report,confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
FEATURE=['R_Thumb','R_Index','R_Middle','R_Ring','R_Pinky','R_aX','R_aY','R_gZ','L_Thumb','L_Index','L_Middle','L_Ring','L_Pinky','L_aX','L_aY','L_gZ']
BASE=Path(__file__).resolve().parent
def ext(df):
    v=df[FEATURE].astype(float).values; fs=[]
    fs+=list(v.mean(0))+list(v.std(0))+list(v.min(0))+list(v.max(0))+list(v[-1]-v[0])
    if len(v)>1:
        d=np.diff(v,axis=0); fs+=list(np.mean(np.abs(d),axis=0))+list(np.max(np.abs(d),axis=0))
    else: fs+=list(np.zeros(len(FEATURE)*2))
    return np.array(fs,dtype=np.float32)
def load(data):
    X=[]; y=[]; files=sorted(Path(data).glob('*.csv'))
    if not files: raise FileNotFoundError(f'没有 CSV 数据：{data}')
    for p in files:
        df=pd.read_csv(p,encoding='utf-8-sig')
        if any(c not in df.columns for c in FEATURE): print('跳过',p.name); continue
        X.append(ext(df)); y.append(str(df['label'].iloc[0]))
    return np.vstack(X),np.array(y)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data',default=str(BASE/'dataset_deep')); ap.add_argument('--output',default=str(BASE/'gesture_deep_model.pkl')); a=ap.parse_args(); X,y=load(a.data); labs,cnt=np.unique(y,return_counts=True); print('样本统计',dict(zip(labs,cnt)))
    model=Pipeline([('scaler',StandardScaler()),('clf',MLPClassifier(hidden_layer_sizes=(256,128,64),activation='relu',alpha=1e-4,max_iter=1200,random_state=42))])
    if len(y)>=8 and len(labs)>=2 and cnt.min()>=2:
        Xtr,Xte,ytr,yte=train_test_split(X,y,test_size=.25,random_state=42,stratify=y); model.fit(Xtr,ytr); pr=model.predict(Xte); print(classification_report(yte,pr,zero_division=0)); print(confusion_matrix(yte,pr,labels=labs))
    else: print('样本较少，全量训练'); model.fit(X,y)
    with Path(a.output).open('wb') as f: pickle.dump({'model':model,'feature_order':FEATURE,'labels':sorted(labs.tolist())},f)
    print('✅ 模型已保存',a.output)
if __name__=='__main__': main()
