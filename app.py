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

# ── Paths ──────────────────────────────────────────────────────────────────────
try:
    BASE_DIR = Path(__file__).parent
except NameError:
    BASE_DIR = Path.cwd()

DATA_DIR  = BASE_DIR / "data"
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

# ── Data helpers ───────────────────────────────────────────────────────────────
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
    missing  = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"컬럼 인식 실패: {missing}\n인식된 컬럼: {list(df.columns)}")

    df["year"]  = year
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

    return df[["year", "region", "branch", "route", "section",
               "direction", "km_start", "count", "lat", "lng"]].reset_index(drop=True)

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

# ── Session state ──────────────────────────────────────────────────────────────
if "all_data" not in st.session_state:
    with st.spinner("데이터 로딩 중…"):
        st.session_state.all_data = load_all_preset()

all_data: dict = st.session_state.all_data
years = sorted(all_data.keys(), reverse=True)

# ── 공통 스타일 상수 ───────────────────────────────────────────────────────────
DARK_BG = "rgba(0,0,0,0)"
GRID    = "#2e3347"
FONT    = dict(color="#8892a4")
PALETTE = ["#4f8ef7","#7c5cfc","#22c55e","#f59e0b",
           "#ef4444","#06b6d4","#ec4899","#84cc16"]

# ── 공통 함수 ──────────────────────────────────────────────────────────────────
def make_map(df: pd.DataFrame):
    """PyDeck ScatterplotLayer 반환. 데이터 없으면 None."""
    mdf = df[["lat","lng","count","route","section","direction","year","region"]].dropna().copy()
    if mdf.empty:
        return None
    mx   = mdf["count"].max() or 1
    norm = mdf["count"] / mx
    mdf["r"]       = (norm * 200 + 55).astype(int)
    mdf["g"]       = ((1 - norm) * 100).astype(int)
    mdf["b"]       = ((1 - norm) * 220).astype(int)
    mdf["radius"]  = (norm * 3000 + 500).astype(int)
    mdf["tooltip"] = (
        mdf["route"] + " " + mdf["section"] +
        " (" + mdf["direction"] + ")\n" +
        mdf["count"].astype(str) + "건 | " +
        mdf["year"].astype(str) + "년"
    )
    layer = pdk.Layer(
        "ScatterplotLayer", mdf,
        get_position=["lng","lat"],
        get_color=["r","g","b", 200],
        get_radius="radius",
        pickable=True,
    )
    return pdk.Deck(
        layers=[layer],
        initial_view_state=pdk.ViewState(
            latitude=36.5, longitude=127.8, zoom=6.3, pitch=0),
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        tooltip={"text": "{tooltip}"},
    )

def _risk_color(norm: float):
    """norm 0~1 → [R,G,B,A]. 낮음=노랑, 중간=주황, 높음=빨강."""
    if norm > 0.6:
        return [239, 68,  68,  230]   # 빨강
    elif norm > 0.3:
        return [249, 115, 22,  230]   # 주황
    else:
        return [234, 179, 8,   230]   # 노랑

def make_map_lines(df: pd.DataFrame):
    """구간을 선(LineLayer)으로 표시. 낮음=노랑, 중간=주황, 높음=빨강.
    같은 노선·방향의 인접 지점을 km_start 순으로 연결.
    단일 지점만 있을 경우 점(ScatterplotLayer)으로 대체."""
    need = ["lat","lng","count","route","section","direction","km_start"]
    mdf  = df[[c for c in need if c in df.columns]].dropna(subset=["lat","lng"]).copy()
    if mdf.empty:
        return None

    max_c    = mdf["count"].max() or 1
    segments = []

    for (route, direction), grp in mdf.groupby(["route", "direction"]):
        grp_s = grp.sort_values("km_start").reset_index(drop=True)
        rows  = grp_s.to_dict("records")

        for i in range(len(rows) - 1):
            r0, r1  = rows[i], rows[i + 1]
            avg_cnt = (r0["count"] + r1["count"]) / 2
            col     = _risk_color(avg_cnt / max_c)
            segments.append({
                "start":   [r0["lng"], r0["lat"]],
                "end":     [r1["lng"], r1["lat"]],
                "r": col[0], "g": col[1], "b": col[2], "a": col[3],
                "tooltip": (
                    f"{route}  {r0['section']} → {r1['section']}\n"
                    f"방향: {direction} | 평균 {int(avg_cnt)}건"
                ),
            })

    # 인접 구간이 없으면(단일 점만 존재) ScatterplotLayer 로 대체
    if not segments:
        return make_map(df)

    seg_df = pd.DataFrame(segments)
    layer  = pdk.Layer(
        "LineLayer", seg_df,
        get_source_position="start",
        get_target_position="end",
        get_color=["r", "g", "b", "a"],
        get_width=6,
        width_min_pixels=3,
        pickable=True,
    )
    return pdk.Deck(
        layers=[layer],
        initial_view_state=pdk.ViewState(
            latitude=36.5, longitude=127.8, zoom=6.3, pitch=0),
        map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
        tooltip={"text": "{tooltip}"},
    )

def _metric_yoy(col, label: str, value: str, delta_str=None):
    """'작년대비' 라벨을 delta 위에 표시하는 커스텀 KPI 카드 (흰 배경, 검은 텍스트)."""
    if delta_str is None:
        col.metric(label, value)
        return
    is_up  = delta_str.startswith("+")
    color  = "#ef4444" if is_up else "#22c55e"
    arrow  = "▲" if is_up else "▼"
    num    = delta_str[1:] if delta_str[0] in ("+", "-") else delta_str
    col.markdown(f"""
<div style="background:#ffffff;border-radius:8px;padding:14px 18px 12px;border:1px solid #e5e7eb">
  <p style="color:#555;font-size:0.82rem;margin:0 0 6px 0;font-weight:500">{label}</p>
  <p style="color:#111;font-size:2.1rem;font-weight:700;margin:0 0 10px 0;line-height:1">{value}</p>
  <p style="color:#888;font-size:0.70rem;margin:0 0 2px 0">작년대비</p>
  <p style="color:{color};font-size:0.88rem;margin:0;font-weight:600">{arrow} {num}</p>
</div>""", unsafe_allow_html=True)

def kpi_row(df: pd.DataFrame, prev_df: pd.DataFrame = None):
    """4개 KPI 카드 렌더링."""
    total = int(df["count"].sum())
    avg   = round(float(df["count"].mean()), 2)
    max_c = int(df["count"].max())
    rc    = df.groupby("route")["count"].sum()
    top_r = rc.idxmax() if not rc.empty else "—"

    delta_total = None
    delta_avg   = None
    if prev_df is not None and not prev_df.empty:
        pt = int(prev_df["count"].sum())
        pa = round(float(prev_df["count"].mean()), 2)
        if pt > 0:
            diff_t = total - pt
            pct_t  = round(diff_t / pt * 100, 1)
            s      = "+" if diff_t >= 0 else ""
            delta_total = f"{s}{diff_t:,}건 ({s}{pct_t}%)"
        if pa > 0:
            diff_a = round(avg - pa, 2)
            pct_a  = round(diff_a / pa * 100, 1)
            s2     = "+" if diff_a >= 0 else ""
            delta_avg = f"{s2}{diff_a}건 ({s2}{pct_a}%)"

    c1, c2, c3, c4 = st.columns(4)
    _metric_yoy(c1, "총 발생건수",        f"{total:,}건", delta_total)
    _metric_yoy(c2, "구간 평균 발생건수", f"{avg}건",     delta_avg)
    c3.metric("최다 발생건",   f"{max_c:,}건")
    c4.metric("최고위험 노선", top_r)

def chart_route(df: pd.DataFrame):
    """노선별 발생건수 수평 막대."""
    rc = df.groupby("route")["count"].sum().nlargest(15).reset_index()
    rc.columns = ["노선","발생건수"]
    mv = rc["발생건수"].max() or 1
    rc["color"] = rc["발생건수"].apply(
        lambda v: "#ef4444" if v/mv > 0.6 else ("#f97316" if v/mv > 0.3 else "#4f8ef7")
    )
    fig = px.bar(rc, x="발생건수", y="노선", orientation="h",
                 color="노선",
                 color_discrete_map={r: c for r, c in zip(rc["노선"], rc["color"])})
    fig.update_layout(
        paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG, font=FONT,
        showlegend=False,
        yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor=GRID),
        margin=dict(l=10, r=10, t=10, b=10), height=360,
    )
    return fig

def chart_region(df: pd.DataFrame):
    """지역(본부)별 파이 차트."""
    reg = df[df["region"] != ""].groupby("region")["count"].sum().reset_index()
    reg.columns = ["본부","발생건수"]
    fig = px.pie(reg, names="본부", values="발생건수", hole=0.4,
                 color_discrete_sequence=PALETTE)
    fig.update_layout(
        paper_bgcolor=DARK_BG, font=FONT,
        legend=dict(orientation="h", yanchor="top", y=-0.05),
        margin=dict(l=10, r=10, t=10, b=40), height=360,
    )
    return fig

def detail_table(df: pd.DataFrame, key_prefix: str):
    """검색·필터·테이블·CSV 다운로드 블록."""
    cf1, cf2, cf3, cf4 = st.columns([2, 1.5, 1.5, 1])
    with cf1:
        search = st.text_input("검색", placeholder="노선·구간·방향 검색…",
                               label_visibility="collapsed",
                               key=f"{key_prefix}_search")
    with cf2:
        reg_opts = ["전체 본부"] + sorted(df["region"].dropna().unique().tolist())
        sel_reg  = st.selectbox("본부", reg_opts, label_visibility="collapsed",
                                key=f"{key_prefix}_reg")
    with cf3:
        rt_opts = ["전체 노선"] + sorted(df["route"].dropna().unique().tolist())
        sel_rt  = st.selectbox("노선", rt_opts, label_visibility="collapsed",
                               key=f"{key_prefix}_rt")
    with cf4:
        min_cnt = st.number_input("최소 건수", 0, int(df["count"].max()), 0,
                                  key=f"{key_prefix}_cnt")

    fdf = df.copy()
    if search:
        mask = fdf[["route","section","direction","region","branch"]].apply(
            lambda col: col.astype(str).str.contains(search, case=False, na=False)
        ).any(axis=1)
        fdf = fdf[mask]
    if sel_reg != "전체 본부":
        fdf = fdf[fdf["region"] == sel_reg]
    if sel_rt != "전체 노선":
        fdf = fdf[fdf["route"] == sel_rt]
    if min_cnt > 0:
        fdf = fdf[fdf["count"] >= min_cnt]

    disp = fdf[["year","region","branch","route","section","direction","count"]].rename(columns={
        "year":"연도","region":"본부","branch":"지사","route":"노선명",
        "section":"구간","direction":"방향","count":"발생건수",
    })
    st.caption(f"총 {len(disp):,}건")
    st.dataframe(disp, use_container_width=True, height=360)
    csv_out = disp.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button("⬇ CSV 내보내기", data=csv_out,
                       file_name=f"roadkill_{key_prefix}.csv",
                       mime="text/csv", key=f"{key_prefix}_dl")

# ══════════════════════════════════════════════════════════════════════════════
# 헤더
# ══════════════════════════════════════════════════════════════════════════════
st.title("🦌 국내 고속도로 로드킬 데이터 대시보드")
_min_y = min(all_data.keys()) if all_data else 2019
_max_y = max(all_data.keys()) if all_data else "—"
st.caption(f"데이터 출처: 한국도로공사 공공데이터 | 분석 기간: {_min_y} ~ {_max_y}년")

# ══════════════════════════════════════════════════════════════════════════════
# 3개 탭
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs(["📊 전체 연도 비교", "📅 연도별 상세 보기", "⚙️ 데이터 관리"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 : 전체 연도 비교
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    if not all_data:
        st.warning("📭 데이터가 없습니다. **[데이터 관리]** 탭에서 CSV 파일을 업로드해주세요.")
    else:
        # ── 연도 선택 필터 ──────────────────────────────────────────────────
        sel_years_t1 = st.multiselect(
            "🔎 비교할 연도 선택 (미선택 시 전체)",
            options=sorted(all_data.keys(), reverse=True),
            default=sorted(all_data.keys(), reverse=True),
            format_func=lambda y: f"{y}년",
            key="tab1_year_filter",
        )
        active_years = sorted(sel_years_t1, reverse=True) if sel_years_t1 else sorted(all_data.keys(), reverse=True)
        all_df = pd.concat([all_data[y] for y in active_years], ignore_index=True)

        # KPI - 전체 집계
        st.subheader("📌 전체 집계")
        kpi_row(all_df)

        # KPI - 최근 연도
        latest_y  = max(all_data.keys())
        prev_y    = max((y for y in all_data if y < latest_y), default=None)
        latest_df = all_data[latest_y]
        prev_df_l = all_data.get(prev_y)
        st.subheader(f"📌 최근 연도 ({latest_y}년) 집계")
        kpi_row(latest_df, prev_df_l)
        st.divider()

        # 연도별 추이 (막대 + 꺾은선)
        st.subheader("📈 연도별 발생건수 추이")
        if len(active_years) >= 2:
            tdf = pd.DataFrame([
                {"연도": str(y),
                 "총 발생건수": int(all_data[y]["count"].sum()),
                 "구간 평균":   round(float(all_data[y]["count"].mean()), 2)}
                for y in sorted(active_years)   # 차트 X축은 오름차순(시계열)
            ])
            fig_t = go.Figure()
            fig_t.add_trace(go.Bar(
                x=tdf["연도"], y=tdf["총 발생건수"], name="총 발생건수",
                marker_color="#ef4444", opacity=0.85, yaxis="y1",
            ))
            fig_t.add_trace(go.Scatter(
                x=tdf["연도"], y=tdf["구간 평균"], name="구간 평균",
                mode="lines+markers",
                line=dict(color="#4f8ef7", width=2, dash="dot"),
                marker=dict(size=8), yaxis="y2",
            ))
            fig_t.update_layout(
                paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG, font=FONT,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                yaxis =dict(title="총 건수", gridcolor=GRID, color="#ef4444"),
                yaxis2=dict(title="평균", overlaying="y", side="right",
                            gridcolor="rgba(0,0,0,0)", color="#4f8ef7"),
                margin=dict(l=10, r=10, t=40, b=10), height=360,
            )
            st.plotly_chart(fig_t, use_container_width=True, key="tab1_trend")
        else:
            st.info("연도 데이터가 2개 이상이면 추이 차트가 표시됩니다.")

        st.divider()

        # 노선 / 지역
        col_r, col_g = st.columns(2)
        with col_r:
            st.subheader("🛣️ 노선별 발생건수 (상위 15)")
            st.plotly_chart(chart_route(all_df), use_container_width=True, key="tab1_route")
        with col_g:
            st.subheader("🗺️ 지역(본부)별 발생건수")
            st.plotly_chart(chart_region(all_df), use_container_width=True, key="tab1_region")

        st.divider()

        # 노선×연도 매트릭스
        st.subheader("🔥 노선 × 연도 발생건수 매트릭스")
        if len(active_years) >= 2:
            matrix = all_df.groupby(["route","year"])["count"].sum().unstack(fill_value=0)
            matrix.columns = [f"{c}년" for c in matrix.columns]
            matrix["합계"] = matrix.sum(axis=1)
            matrix = matrix.sort_values("합계", ascending=False).head(25)
            year_cols = [c for c in matrix.columns if c != "합계"]
            styled = (
                matrix.style
                .background_gradient(cmap="RdYlBu_r", subset=year_cols, vmin=0)
                .background_gradient(cmap="Blues",    subset=["합계"])
                .format("{:.0f}")
            )
            st.dataframe(styled, use_container_width=True, height=460)
            st.markdown("""
<div style="font-size:0.78rem;color:#8892a4;margin-top:6px;line-height:1.8">
  <b>색상 기준</b> &nbsp;|&nbsp;
  <b>연도별 컬럼:</b>&nbsp;
  <span style="background:#4575b4;color:white;padding:1px 6px;border-radius:3px">■ 낮음</span>&nbsp;→&nbsp;
  <span style="background:#fee090;color:#333;padding:1px 6px;border-radius:3px">■ 중간</span>&nbsp;→&nbsp;
  <span style="background:#d73027;color:white;padding:1px 6px;border-radius:3px">■ 높음</span>
  &emsp;
  <b>합계 컬럼:</b>&nbsp;
  <span style="background:#deebf7;color:#333;padding:1px 6px;border-radius:3px">■ 낮음</span>&nbsp;→&nbsp;
  <span style="background:#08519c;color:white;padding:1px 6px;border-radius:3px">■ 높음</span>
  &emsp; (노선별 누적 발생건수 기준)
</div>""", unsafe_allow_html=True)
        else:
            st.info("연도 데이터가 2개 이상이면 매트릭스가 표시됩니다.")

        st.divider()

        # 전체 상세 테이블
        st.subheader("📋 전체 상세 데이터")
        detail_table(all_df, "all")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 : 연도별 상세 보기
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    if not all_data:
        st.warning("📭 데이터가 없습니다. **[데이터 관리]** 탭에서 CSV 파일을 업로드해주세요.")
    else:
        sel_year = st.selectbox(
            "📅 연도 선택",
            sorted(all_data.keys(), reverse=True),
            format_func=lambda y: f"{y}년",
            key="tab2_year",
        )

        yr_df   = all_data[sel_year]
        prev_yr = max((y for y in sorted(all_data.keys()) if y < sel_year), default=None)
        prev_df = all_data.get(prev_yr) if prev_yr else None

        # KPI
        st.subheader(f"📌 {sel_year}년 집계")
        kpi_row(yr_df, prev_df)
        st.divider()

        # 지도 — 상행선(서울방향) / 하행선(지방방향) 분리
        # 상행선: 서울 방향 (direction에 "상" 포함)
        # 하행선: 지방 방향 (direction에 "하" 포함)
        st.subheader("📍 지점 지도")
        map_up = yr_df[yr_df["direction"].str.contains("상", na=False)]
        map_dn = yr_df[yr_df["direction"].str.contains("하", na=False)]
        col_up, col_dn = st.columns(2)
        with col_up:
            st.markdown("**상행선** &nbsp;<span style='color:#4f8ef7;font-size:0.85rem'>(서울방향)</span>",
                        unsafe_allow_html=True)
            deck_up = make_map_lines(map_up)
            if deck_up:
                st.pydeck_chart(deck_up, use_container_width=True, key="tab2_map_up")
            else:
                st.info("상행선 데이터가 없습니다.")
        with col_dn:
            st.markdown("**하행선** &nbsp;<span style='color:#f97316;font-size:0.85rem'>(지방방향)</span>",
                        unsafe_allow_html=True)
            deck_dn = make_map_lines(map_dn)
            if deck_dn:
                st.pydeck_chart(deck_dn, use_container_width=True, key="tab2_map_dn")
            else:
                st.info("하행선 데이터가 없습니다.")
        st.markdown("""
<div style="font-size:0.78rem;color:#8892a4;margin-top:4px">
  <b>선 색상 기준</b> &nbsp;|&nbsp;
  <span style="background:#eab308;color:#111;padding:1px 8px;border-radius:3px">■ 낮음</span>&nbsp;→&nbsp;
  <span style="background:#f97316;color:white;padding:1px 8px;border-radius:3px">■ 중간</span>&nbsp;→&nbsp;
  <span style="background:#ef4444;color:white;padding:1px 8px;border-radius:3px">■ 높음</span>
  &nbsp;(인접 구간 평균 발생건수 기준 · 같은 노선·방향 순서로 연결)
</div>""", unsafe_allow_html=True)

        # 노선 차트
        st.subheader("🛣️ 노선별 발생건수 (상위 15)")
        st.plotly_chart(chart_route(yr_df), use_container_width=True, key="tab2_route")

        st.divider()

        # 지역 파이 + 위험구간 TOP10
        col_p, col_s = st.columns(2)
        with col_p:
            st.subheader("🗺️ 지역(본부)별 발생건수")
            st.plotly_chart(chart_region(yr_df), use_container_width=True, key="tab2_region")
        with col_s:
            st.subheader("🔎 위험 구간 TOP 10")
            sec = yr_df.groupby(["route","section"])["count"].sum().nlargest(10).reset_index()
            sec["label"] = sec["route"] + " " + sec["section"]
            fig_s = px.bar(sec, x="count", y="label", orientation="h",
                           labels={"count":"발생건수","label":"구간"},
                           color="count",
                           color_continuous_scale=["#4f8ef7","#f97316","#ef4444"])
            fig_s.update_layout(
                paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG, font=FONT,
                showlegend=False, coloraxis_showscale=False,
                yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"),
                xaxis=dict(gridcolor=GRID),
                margin=dict(l=10, r=10, t=10, b=10), height=360,
            )
            st.plotly_chart(fig_s, use_container_width=True, key="tab2_top10")

        st.divider()

        # 상세 테이블
        st.subheader(f"📋 {sel_year}년 상세 데이터")
        detail_table(yr_df, str(sel_year))


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 : 데이터 관리
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.subheader("⚙️ 데이터 관리")

    # ── 연도 추가 ────────────────────────────────────────────────────────────
    st.markdown("### 📂 새 연도 데이터 추가")
    st.caption("연도를 먼저 입력하고 CSV 파일을 선택한 뒤 업로드 버튼을 눌러주세요.")

    add_c1, add_c2 = st.columns([1, 3])
    with add_c1:
        up_year = st.number_input(
            "연도 입력", min_value=2000, max_value=2099, value=2024, step=1,
            help="CSV 파일에 해당하는 연도를 입력하세요.",
            key="up_year",
        )
    with add_c2:
        up_file = st.file_uploader(
            f"{int(up_year)}년 CSV 파일 선택",
            type=["csv"],
            help="한국도로공사 로드킬 데이터 CSV 파일을 선택하세요.",
            key="up_file",
        )

    if st.button("📤 업로드", type="primary", key="btn_upload"):
        if up_file is None:
            st.warning("⚠️ CSV 파일을 먼저 선택해주세요.")
        else:
            with st.spinner(f"{int(up_year)}년 데이터 처리 중…"):
                try:
                    raw    = up_file.read()
                    df_new = parse_csv_bytes(raw, int(up_year))
                    st.session_state.all_data[int(up_year)] = df_new
                    (DATA_DIR / f"{int(up_year)}_roadkill.csv").write_bytes(raw)
                    st.cache_data.clear()
                    st.success(
                        f"✅ {int(up_year)}년 데이터 {len(df_new):,}건 추가 완료! "
                        f"다른 탭으로 이동하면 바로 반영됩니다."
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 오류: {e}")

    st.divider()

    # ── 등록된 연도 목록 ─────────────────────────────────────────────────────
    st.markdown("### 📋 현재 등록된 연도 목록")
    if not all_data:
        st.info("등록된 데이터가 없습니다.")
    else:
        summary_rows = []
        for y in sorted(all_data.keys(), reverse=True):
            ydf = all_data[y]
            summary_rows.append({
                "연도":          f"{y}년",
                "총 발생건수":   f"{int(ydf['count'].sum()):,}건",
                "구간 수":       f"{len(ydf):,}개",
                "노선 수":       f"{ydf['route'].nunique()}개",
                "지역(본부) 수": f"{ydf['region'].nunique()}개",
            })
        st.dataframe(
            pd.DataFrame(summary_rows),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    # ── 연도 삭제 ────────────────────────────────────────────────────────────
    st.markdown("### 🗑️ 연도 데이터 삭제")
    if not all_data:
        st.info("삭제할 데이터가 없습니다.")
    else:
        del_c1, del_c2 = st.columns([3, 1])
        with del_c1:
            del_year = st.selectbox(
                "삭제할 연도 선택",
                sorted(all_data.keys(), reverse=True),
                format_func=lambda y: (
                    f"{y}년  ·  총 {int(all_data[y]['count'].sum()):,}건"
                    f"  ·  {len(all_data[y]):,}개 구간"
                ),
                key="del_year_sel",
            )
        with del_c2:
            st.write("")
            st.write("")
            if st.button("🗑️ 삭제", type="secondary",
                         use_container_width=True, key="btn_delete"):
                del st.session_state.all_data[del_year]
                p = DATA_DIR / f"{del_year}_roadkill.csv"
                if p.exists():
                    p.unlink()
                st.success(f"✅ {del_year}년 데이터가 삭제되었습니다.")
                st.rerun()
