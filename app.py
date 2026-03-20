import os
import re
import json
import chardet
import pandas as pd
from flask import Flask, jsonify, request, render_template, abort
from werkzeug.utils import secure_filename

app = Flask(__name__)

DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Preset CSV file paths (from Downloads)
PRESET_FILES = {
    2019: os.path.join(DOWNLOADS, "로드킬데이터_사고잦은구간(2019년상반기).csv"),
    2020: os.path.join(DOWNLOADS, "한국도로공사_로드킬 데이터 정보_20200630_수정.csv"),
    2021: os.path.join(DOWNLOADS, "로드킬데이터_사고잦은구간(2021).csv"),
    2022: os.path.join(DOWNLOADS, "로드킬 데이터 정보(2022년6월).csv"),
    2023: os.path.join(DOWNLOADS, "로드킬 데이터 정보(2023).csv"),
    2025: os.path.join(DOWNLOADS, "한국도로공사_로드킬 데이터 정보_20250501.csv"),
}

# In-memory store: year (int) -> list of records
all_data: dict[int, list[dict]] = {}


def detect_encoding(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read(32768)
    result = chardet.detect(raw)
    enc = result.get("encoding") or "cp949"
    if enc.lower() in ("ascii", "windows-1252"):
        enc = "cp949"
    return enc


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names across different CSV formats."""
    df.columns = [str(c).strip().replace(" ", "") for c in df.columns]

    col_map = {}
    for c in df.columns:
        if any(k in c for k in ("본부명", "도로본부")):
            col_map[c] = "region"
        elif "지사명" in c or "지사" in c:
            col_map[c] = "branch"
        elif "노선명" in c:
            col_map[c] = "route"
        elif "구간" in c:
            col_map[c] = "section"
        elif "방향" in c:
            col_map[c] = "direction"
        elif "5km" in c.lower() or "시점" in c:
            col_map[c] = "km_start"
        elif "발생건수" in c or "건수" in c:
            col_map[c] = "count"
        elif "위도" in c:
            col_map[c] = "lat"
        elif "경도" in c:
            col_map[c] = "lng"
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
        raise ValueError(f"컬럼 인식 실패: {missing} | 인식된 컬럼: {list(df.columns)}")

    df["year"] = year
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    df["lat"]   = pd.to_numeric(df["lat"], errors="coerce")
    df["lng"]   = pd.to_numeric(df["lng"], errors="coerce")
    df["km_start"] = pd.to_numeric(
        df.get("km_start", pd.Series(dtype=float)), errors="coerce"
    ).fillna(0).astype(int)

    # Keep only valid Korean coordinates
    df = df[
        (df["lat"] >= 33) & (df["lat"] <= 38.5) &
        (df["lng"] >= 124) & (df["lng"] <= 130.5)
    ].dropna(subset=["lat", "lng"])

    for col in ("region", "branch", "route", "section", "direction"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
        else:
            df[col] = ""

    keep = ["year", "region", "branch", "route", "section", "direction",
            "km_start", "count", "lat", "lng"]
    return df[keep].to_dict("records")


# ── Initial data load ──────────────────────────────────────────────────────

def load_all():
    for year, path in PRESET_FILES.items():
        if os.path.exists(path):
            try:
                all_data[year] = load_csv(path, year)
                print(f"[OK] {year}: {len(all_data[year])}건 로드")
            except Exception as e:
                print(f"[ERR] {year} ({path}): {e}")
        else:
            print(f"[SKIP] {year}: 파일 없음 → {path}")

    for fname in sorted(os.listdir(UPLOAD_FOLDER)):
        if not fname.lower().endswith(".csv"):
            continue
        m = re.search(r"(\d{4})", fname)
        if not m:
            continue
        year = int(m.group(1))
        if year in all_data:
            continue
        try:
            all_data[year] = load_csv(os.path.join(UPLOAD_FOLDER, fname), year)
            print(f"[OK] {year} (업로드): {len(all_data[year])}건 로드")
        except Exception as e:
            print(f"[ERR] 업로드 파일 {fname}: {e}")

load_all()


# ── API routes ─────────────────────────────────────────────────────────────

@app.route("/api/years")
def api_years():
    return jsonify(sorted(all_data.keys()))


@app.route("/api/data")
def api_data():
    year = request.args.get("year", type=int)
    if year is not None:
        return jsonify(all_data.get(year, []))
    combined = [r for records in all_data.values() for r in records]
    return jsonify(combined)


@app.route("/api/stats")
def api_stats():
    stats = {}
    year_totals = {y: sum(r["count"] for r in recs) for y, recs in all_data.items()}

    for year, records in all_data.items():
        if not records:
            continue
        counts = [r["count"] for r in records]
        total  = sum(counts)

        route_counts: dict[str, int] = {}
        for r in records:
            route_counts[r["route"]] = route_counts.get(r["route"], 0) + r["count"]

        region_counts: dict[str, int] = {}
        for r in records:
            region_counts[r["region"]] = region_counts.get(r["region"], 0) + r["count"]

        top_route = max(route_counts, key=route_counts.get) if route_counts else ""

        prev_year = max((y for y in year_totals if y < year), default=None)
        yoy = None
        if prev_year and year_totals[prev_year] > 0:
            yoy = round((total - year_totals[prev_year]) / year_totals[prev_year] * 100, 1)

        stats[year] = {
            "total": total,
            "avg": round(total / len(records), 2),
            "max_single": max(counts),
            "top_route": top_route,
            "record_count": len(records),
            "region_counts": region_counts,
            "route_counts": route_counts,
            "yoy": yoy,
        }
    return jsonify(stats)


@app.route("/api/matrix")
def api_matrix():
    years  = sorted(all_data.keys())
    matrix: dict[str, dict[int, int]] = {}
    for year, records in all_data.items():
        for r in records:
            route = r["route"]
            if route not in matrix:
                matrix[route] = {}
            matrix[route][year] = matrix[route].get(year, 0) + r["count"]

    totals = {route: sum(matrix[route].values()) for route in matrix}
    sorted_routes = sorted(totals, key=totals.get, reverse=True)

    rows = []
    for route in sorted_routes:
        row = {"route": route, "total": totals[route]}
        for y in years:
            row[str(y)] = matrix[route].get(y, None)
        rows.append(row)
    return jsonify({"years": years, "rows": rows})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "파일이 없습니다"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "파일명이 없습니다"}), 400

    year_str = request.form.get("year", "").strip()
    if not year_str:
        m = re.search(r"(\d{4})", f.filename)
        year_str = m.group(1) if m else ""
    if not year_str or not year_str.isdigit():
        return jsonify({"error": "연도를 입력해주세요"}), 400

    year      = int(year_str)
    save_path = os.path.join(UPLOAD_FOLDER, f"{year}_roadkill.csv")
    f.save(save_path)

    try:
        records = load_csv(save_path, year)
        all_data[year] = records
        return jsonify({"success": True, "year": year, "count": len(records)})
    except Exception as e:
        if os.path.exists(save_path):
            os.remove(save_path)
        return jsonify({"error": str(e)}), 400


@app.route("/api/year/<int:year>", methods=["DELETE"])
def api_delete_year(year: int):
    if year not in all_data:
        return jsonify({"error": "해당 연도 데이터가 없습니다"}), 404
    del all_data[year]
    save_path = os.path.join(UPLOAD_FOLDER, f"{year}_roadkill.csv")
    if os.path.exists(save_path):
        os.remove(save_path)
    return jsonify({"success": True, "year": year})


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
