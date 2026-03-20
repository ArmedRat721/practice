import os
import re
import json
import chardet
import pandas as pd
from flask import Flask, jsonify, request, render_template, abort
from werkzeug.utils import secure_filename

app = Flask(__name__)

# 경로 설정
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 프리셋 파일 경로
PRESET_FILES = {
    2019: os.path.join(DOWNLOADS, "로드킬데이터_사고잦은구간(2019년상반기).csv"),
    2020: os.path.join(DOWNLOADS, "한국도로공사_로드킬 데이터 정보_20200630_수정.csv"),
    2021: os.path.join(DOWNLOADS, "로드킬데이터_사고잦은구간(2021).csv"),
    2022: os.path.join(DOWNLOADS, "로드킬 데이터 정보(2022년6월).csv"),
    2023: os.path.join(DOWNLOADS, "로드킬 데이터 정보(2023).csv"),
    2025: os.path.join(DOWNLOADS, "한국도로공사_로드킬 데이터 정보_20250501.csv"),
}

# 메모리 데이터 저장소
all_data: dict[int, list[dict]] = {}

# ── 데이터 처리 유틸리티 ──────────────────────────────────────────────────────

def detect_encoding(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read(32768)
    result = chardet.detect(raw)
    enc = result.get("encoding") or "cp949"
    if enc.lower() in ("ascii", "windows-1252"):
        enc = "cp949"
    return enc

def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """컬럼명 표준화"""
    df.columns = [str(c).strip().replace(" ", "") for c in df.columns]
    col_map = {}
    for c in df.columns:
        if any(k in c for k in ("본부명", "도로본부")): col_map[c] = "region"
        elif "지사명" in c or "지사" in c: col_map[c] = "branch"
        elif "노선명" in c: col_map[c] = "route"
        elif "구간" in c: col_map[c] = "section"
        elif "방향" in c: col_map[c] = "direction"
        elif "5km" in c.lower() or "시점" in c: col_map[c] = "km_start"
        elif "발생건수" in c or "건수" in c: col_map[c] = "count"
        elif "위도" in c: col_map[c] = "lat"
        elif "경도" in c: col_map[c] = "lng"
    return df.rename(columns=col_map)

def load_csv(path: str, year: int) -> list[dict]:
    enc = detect_encoding(path)
    try:
        df = pd.read_csv(path, encoding=enc)
    except Exception:
        df = pd.read_csv(path, encoding="cp949")

    df = normalize_df(df)
    required = ["region", "route", "section", "direction", "count", "lat", "lng"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"컬럼 인식 실패: {missing}")

    df["year"] = year
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lng"] = pd.to_numeric(df["lng"], errors="coerce")
    df["km_start"] = pd.to_numeric(df.get("km_start", 0), errors="coerce").fillna(0).astype(int)

    # 좌표 필터링 (한국 범위)
    df = df[(df["lat"] >= 33) & (df["lat"] <= 38.5) & 
            (df["lng"] >= 124) & (df["lng"] <= 130.5)].dropna(subset=["lat", "lng"])

    keep = ["year", "region", "branch", "route", "section", "direction", "km_start", "count", "lat", "lng"]
    return df[keep].to_dict("records")

def load_all():
    """초기 데이터 로드"""
    for year, path in PRESET_FILES.items():
        if os.path.exists(path):
            try:
                all_data[year] = load_csv(path, year)
            except Exception as e:
                print(f"[ERR] {year}: {e}")
    
    if os.path.exists(UPLOAD_FOLDER):
        for fname in os.listdir(UPLOAD_FOLDER):
            if fname.endswith(".csv"):
                m = re.search(r"(\d
