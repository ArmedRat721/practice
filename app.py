import streamlit as st
import pandas as pd
import chardet
import re
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
from io import BytesIO
from pathlib import Path

st.set_page_config(
    page_title="국내 고속도로 로드킬 데이터 대시보드",
    page_icon="🦌",
    layout="wide",
)

# ── Paths ──────────────────────────────────────────────────────────────
try:
    BASE_DIR = Path(__file__).parent
except NameError:
    BASE_DIR = Path.cwd()

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DOWNLOADS = Path.home() / "Downloads"

PRESET_FILENAMES = {
    2019: "로드킬데이터_사고잦은구간(2019년상반기).csv",
    2020: "한국도로공사_로드킬 데이터 정보_20200630_수정.csv",
    2021: "로드킬데이터_사고잦은구간(2021).csv",
    2022: "로드킬 데이터 정보(2022년6월).csv",
    2023: "로드킬 데이터 정보(2023).csv",
    2025: "한국도로공사_로드킬 데이터 정보_20250501.csv",
}

# ── Data helpers ────────────────────────────────────────────────────────
def detect_encoding(data: bytes) -> str:
    result = chardet.detect(data[:32768])
    enc = result.get("encoding") or "cp949"
    if enc.lower() in ("ascii", "windows-1252"):
        enc = "cp949"
    return enc

def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().replace(" ", "") for c in df.columns]
    col_map = {}
    for c in df.columns:
        if any(k in c for k in ("본부명", "도로본부")):
            col_map[c] = "region"
        elif "지사" in c:
            col_map[c] = "branch"
        elif "노선명" in c:
            col_map[c] = "route"
        elif "구간" in c:
            col_map[c] = "section"
        elif "방향" in c:
            col_map[c] = "direction"
        elif "5km" in c.lower() or "시점" in c:
            col_map[c] = "km_start"
        elif "발생건수" in c:
            col_map[c] = "count"
        elif "위도" in c:
            col_map[c] = "lat"
        elif "경도" in c:
            col_map[c] = "lng"
    return df.rename(columns=col_map)

@st.cache_data(show_spinner=False)
def parse_csv_bytes(data: bytes, year: int) -> pd.DataFrame:
    enc = detect_encoding(data)
    try:
        df = pd.read_csv(BytesIO(data), encoding=enc)
    except Exception:
        df = pd.read_csv(BytesIO(data), encoding="cp949")

    df = normalize_df(df)

    required = ["region", "route", "section", "direction", "count", "lat", "lng"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"컬럼 인식 실패: {missing}\n인식된 컬럼: {list(df.columns)}")

    df["year"] = year
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    df["lat"]   = pd.to_numeric(df["lat"],   errors="coerce")
    df["lng"]   = pd.to_numeric(df["lng"],   errors="coerce")

    km_col = df.get("km_start", pd.Series(dtype=float))
    if not isinstance(km_col, pd.Series):
        km_col = pd.Series(dtype=float)
    df["km_start"] = pd.to_numeric(km_col, errors="coerce").fillna(0).astype(int)

    df = df[df["lat"].between(33, 38.5) & df["lng"].between(124, 130.5)]
    df = df.dropna(subset=["lat", "lng"])

    for col in ("region", "branch", "route", "section", "direction"):
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
        else:
            df[col] = ""

    keep = ["year", "region", "branch", "route", "section",
            "direction", "km_start", "count", "lat", "lng"]
    return df[keep].reset_index(drop=True)

@st.cache_data(show_spinner=False)
def load_all_preset() -> dict:
    result = {}
    for year, fname in PRESET_FILENAMES.items():
        for folder in (DATA_DIR, DOWNLOADS):
            path = folder / fname
            if path.exists():
                try:
                    result[year] = parse_csv_bytes(path.read_bytes(), year)
                    break
                except Exception:
                    pass
    for fpath in sorted(DATA_DIR.glob("*.csv")):
        m = re.search(r"(\d{4})", fpath.name)
        if not m:
            continue
        year = int(m.group(1))
        if year not in result:
            try:
                result[year] = parse_csv_bytes(fpath.read_bytes(), year)
            except Exception:
                pass
    return result

# ── Session state ───────────────────────────────────────────────────────
if "all_data" not in st.session_state:
    with st.spinner("데이터 로딩 중…"):
        st.session_state.all_data = load_all_preset()

all_data: dict = st.session_state.all_data
years = sorted(all_data.keys())

# ── Sidebar ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📅 연도 선택")
    year_opts = ["전체 비교"] + [f"{y}년" for y in years]
    sel = st.radio("", year_opts, label_visibility="collapsed")

    st.divider()

    st.header("📂 새 연도 데이터 추가")
    up_file = st.file_uploader("CSV 파일", type=["csv"], label_visibility="collapsed")
    up_year = st.number_input("연도", 2000, 2099, 2024)
    if st.button("업로드", type="primary", use_container_width=True):
        if up_file:
            try:
                raw = up_file.read()
                df_up = parse_csv_bytes(raw, int(up_year))
                st.session_state.all_data[int(up_year)] = df_up
                (DATA_DIR / f"{int(up_year)}_roadkill.csv").write_bytes(raw)
                st.cache_data.clear()
                st.success(f"✓ {up_year}년 {len(df_up):,}건 업로드 완료!")
                st.rerun()
            except Exception as e:
                st.error(f"오류: {e}")
        else:
            st.warning("파일을 선택하세요.")

    if years:
        st.divider()
        st.header("🗑️ 연도 삭제")
        del_year = st.selectbox("", years, format_func=lambda y: f"{y}년",
                                label_visibility="collapsed")
        if st.button("삭제", type="secondary", use_container_width=True):
            del st.session_state.all_data[del_year]
            p = DATA_DIR / f"{del_year}_roadkill.csv"
            if p.exists():
                p.unlink()
            st.success(f"✓ {del_year}년 삭제 완료")
            st.rerun()

# ── Header ──────────────────────────────────────────────────────────────
st.title("🦌 국내 고속도로 로드킬 데이터 대시보드")
st.caption("데이터 출처: 한국도로공사 공공데이터 | 분석 기간: 2019 ~ 2025년")

if not all_data:
    st.warning("데이터가 없습니다. 사이드바에서 CSV 파일을 업로드해주세요.")
    st.stop()

# ── Active data ─────────────────────────────────────────────────────────
if sel == "전체 비교":
    active_year = None
    df = pd.concat(all_data.values(), ignore_index=True)
else:
    active_year = int(sel.replace("년", ""))
    df = all_data.get(active_year, pd.DataFrame())
    if df.empty:
        st.warning("해당 연도 데이터가 없습니다.")
        st.stop()

# ── KPI Cards ───────────────────────────────────────────────────────────
total = int(df["count"].sum())
avg   = round(float(df["count"].mean()), 2)
max_c = int(df["count"].max())
rc    = df.groupby("route")["count"].sum()
top_r = rc.idxmax() if not rc.empty else "—"
top_c = int(rc.max())  if not rc.empty else 0

yoy_str = None
if active_year:
    prev = max((y for y in years if y < active_year), default=None)
    if prev and prev in all_data:
        prev_total = int(all_data[prev]["count"].sum())
        if prev_total > 0:
            delta = round((total - prev_total) / prev_total * 100, 1)
            yoy_str = f"{'+' if delta >= 0 else ''}{delta}%"

c1, c2, c3, c4 = st.columns(4)
c1.metric("총 발생건수",        f"{total:,}건", yoy_str)
c2.metric("구간 평균 발생건수", f"{avg}건",      f"{len(df):,}개 구간")
c3.metric("최다 단일구간",      f"{max_c:,}건")
c4.metric("최고위험 노선",      top_r,           f"{top_c:,}건")

st.divider()

# ── Map + Trend ─────────────────────────────────────────────────────────
col_map, col_trend = st.columns([1.3, 0.7])

with col_map:
    st.subheader("📍 지도 핫스팟 시각화")
    map_df = df[["lat", "lng", "count", "route", "section",
                 "direction", "year", "region"]].dropna().copy()
    if not map_df.empty:
        mx   = map_df["count"].max() or 1
        norm = map_df["count"] / mx
        map_df["r"]      = (norm * 200 + 55).astype(int)
        map_df["g"]      = ((1 - norm) * 100).astype(int)
        map_df["b"]      = ((1 - norm) * 220).astype(int)
        map_df["radius"] = (norm * 3000 + 500).astype(int)
        map_df["tooltip"] = (
            map_df["route"] + " " + map_df["section"] +
            " (" + map_df["direction"] + ")\n" +
            map_df["count"].astype(str) + "건 | " +
            map_df["year"].astype(str) + "년"
        )
        layer = pdk.Layer(
            "ScatterplotLayer", map_df,
            get_position=["lng", "lat"],
            get_color=["r", "g", "b", 200],
            get_radius="radius",
            pickable=True,
        )
        st.pydeck_chart(pdk.Deck(
            layers=[layer],
            initial_view_state=pdk.ViewState(
                latitude=36.5, longitude=127.8, zoom=6.3, pitch=0),
            map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
            tooltip={"text": "{tooltip}"},
        ), use_container_width=True)

with col_trend:
    st.subheader("📈 연도별 발생건수 추이")
    if len(years) >= 2:
        tdf = pd.DataFrame([
            {"연도": str(y),
             "총 발생건수": int(all_data[y]["count"].sum()),
             "구간 평균":   round(float(all_data[y]["count"].mean()), 2)}
            for y in years
        ])
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=tdf["연도"], y=tdf["총 발생건수"], name="총 발생건수",
            mode="lines+markers", line=dict(color="#ef4444", width=2),
            marker=dict(size=8), yaxis="y1",
        ))
        fig.add_trace(go.Scatter(
            x=tdf["연도"], y=tdf["구간 평균"], name="구간 평균",
            mode="lines+markers", line=dict(color="#4f8ef7", width=2, dash="dot"),
            marker=dict(size=8), yaxis="y2",
        ))
        if active_year:
            fig.add_vline(x=str(active_year), line_dash="dash",
                          line_color="rgba(255,255,255,0.4)", line_width=1)
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#8892a4"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            yaxis=dict(title="총 건수", gridcolor="#333", color="#ef4444"),
            yaxis2=dict(title="평균", overlaying="y", side="right",
                        gridcolor="rgba(0,0,0,0)", color="#4f8ef7"),
            margin=dict(l=10, r=10, t=40, b=10), height=360,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("연도 데이터가 2개 이상이면 추이 차트가 표시됩니다.")

# ── Route + Region ──────────────────────────────────────────────────────
col_route, col_region = st.columns(2)

with col_route:
    st.subheader("🛣️ 노선별 발생건수 (상위 15)")
    rc_top = df.groupby("route")["count"].sum().nlargest(15).reset_index()
    rc_top.columns = ["노선", "발생건수"]
    mv = rc_top["발생건수"].max() or 1
    rc_top["color"] = rc_top["발생건수"].apply(
        lambda v: "#ef4444" if v / mv > 0.6 else ("#f97316" if v / mv > 0.3 else "#4f8ef7")
    )
    fig2 = px.bar(
        rc_top, x="발생건수", y="노선", orientation="h",
        color="노선",
        color_discrete_map={r: c for r, c in zip(rc_top["노선"], rc_top["color"])},
    )
    fig2.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8892a4"), showlegend=False,
        yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor="#333"),
        margin=dict(l=10, r=10, t=10, b=10), height=360,
    )
    st.plotly_chart(fig2, use_container_width=True)

with col_region:
    st.subheader("🗺️ 지역(본부)별 발생건수")
    reg = df[df["region"] != ""].groupby("region")["count"].sum().reset_index()
    reg.columns = ["본부", "발생건수"]
    fig3 = px.pie(
        reg, names="본부", values="발생건수", hole=0.4,
        color_discrete_sequence=["#4f8ef7", "#7c5cfc", "#22c55e", "#f59e0b",
                                  "#ef4444", "#06b6d4", "#ec4899", "#84cc16"],
    )
    fig3.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#8892a4"),
        legend=dict(orientation="h", yanchor="top", y=-0.05),
        margin=dict(l=10, r=10, t=10, b=40), height=360,
    )
    st.plotly_chart(fig3, use_container_width=True)

# ── Matrix ──────────────────────────────────────────────────────────────
st.subheader("🔥 노선 × 연도 발생건수 매트릭스")
if len(years) >= 2:
    all_concat = pd.concat(all_data.values(), ignore_index=True)
    matrix = all_concat.groupby(["route", "year"])["count"].sum().unstack(fill_value=0)
    matrix.columns = [f"{c}년" for c in matrix.columns]
    matrix["합계"] = matrix.sum(axis=1)
    matrix = matrix.sort_values("합계", ascending=False).head(25)
    year_cols = [c for c in matrix.columns if c != "합계"]
    styled = (
        matrix.style
        .background_gradient(cmap="RdYlBu_r", subset=year_cols, vmin=0)
        .background_gradient(cmap="Blues", subset=["합계"])
        .format("{:.0f}")
    )
    st.dataframe(styled, use_container_width=True, height=460)
else:
    st.info("연도 데이터가 2개 이상이면 매트릭스가 표시됩니다.")

# ── Detail Table ────────────────────────────────────────────────────────
st.subheader("📋 상세 데이터 테이블")

cf1, cf2, cf3, cf4 = st.columns([2, 1.5, 1.5, 1])
with cf1:
    search = st.text_input("검색", placeholder="노선·구간·방향 검색…",
                           label_visibility="collapsed")
with cf2:
    region_opts = ["전체 본부"] + sorted(df["region"].dropna().unique().tolist())
    sel_reg = st.selectbox("본부", region_opts, label_visibility="collapsed")
with cf3:
    route_opts = ["전체 노선"] + sorted(df["route"].dropna().unique().tolist())
    sel_rt = st.selectbox("노선", route_opts, label_visibility="collapsed")
with cf4:
    min_cnt = st.number_input("최소 건수", 0, int(df["count"].max()), 0)

fdf = df.copy()
if search:
    mask = fdf[["route", "section", "direction", "region", "branch"]].apply(
        lambda col: col.astype(str).str.contains(search, case=False, na=False)
    ).any(axis=1)
    fdf = fdf[mask]
if sel_reg != "전체 본부":
    fdf = fdf[fdf["region"] == sel_reg]
if sel_rt != "전체 노선":
    fdf = fdf[fdf["route"] == sel_rt]
if min_cnt > 0:
    fdf = fdf[fdf["count"] >= min_cnt]

disp = fdf[["year", "region", "branch", "route", "section", "direction", "count"]].rename(columns={
    "year": "연도", "region": "본부", "branch": "지사", "route": "노선명",
    "section": "구간", "direction": "방향", "count": "발생건수",
})
st.caption(f"총 {len(disp):,}건")
st.dataframe(disp, use_container_width=True, height=380)

csv_out = disp.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
year_label = str(active_year) if active_year else "all"
st.download_button(
    "⬇ CSV 내보내기", data=csv_out,
    file_name=f"roadkill_export_{year_label}.csv",
    mime="text/csv",
)
