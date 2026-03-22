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
        elif "상하행" in c:
            col_map[c] = "dir_yn"
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

def _assign_dir_yn(route: str, direction: str = "") -> str:
    """노선명(route)·방향(direction) 컬럼을 기반으로 상행선/하행선/미분류 판정.

    ── 1순위: 노선명에 명시된 방향 키워드 ──────────────────────────────
      상행선: (상행) / (북향) / (서향)
      하행선: (하행) / (남향) / (동향)

    ── 2순위: 노선별 종점 키워드 테이블 ────────────────────────────────
    direction 컬럼(노선 유형 식별자)으로 노선을 특정한 뒤,
    route 컬럼에 해당 노선의 상행·하행 종점 키워드가 포함되어 있으면 판별.

    ── 결과값 ───────────────────────────────────────────────────────────
      '상행선' | '하행선' | '미분류'
    """
    r = str(route).strip()
    d = str(direction).strip()

    # ── 1순위: 노선명 방향 키워드 ─────────────────────────────────────
    if any(kw in r for kw in ("상행", "북향", "서향")):
        return "상행선"
    if any(kw in r for kw in ("하행", "남향", "동향")):
        return "하행선"

    # ── 2순위: 노선별 종점 키워드 테이블 ─────────────────────────────
    # (direction 컬럼 매칭 키워드) → (상행 종점 키워드 목록, 하행 종점 키워드 목록)
    ROUTE_TABLE = [
        # direction 매칭 키워드,   상행(기점) 종점,         하행(종점) 종점
        (["경부"],                 ["서울"],                 ["부산"]),
        (["남해"],                 ["순천"],                 ["부산"]),
        (["영동"],                 ["인천"],                 ["강릉"]),
        (["경춘"],                 ["서울"],                 ["춘천"]),
        (["중부내륙"],             ["양평"],                 ["창원"]),
        (["중부"],                 ["하남"],                 ["통영"]),
        (["호남지선"],             ["회덕", "대전"],         ["논산"]),
        (["호남"],                 ["천안"],                 ["순천", "목포"]),
        (["서해"],                 ["서울"],                 ["목포"]),
        (["동해"],                 ["근덕"],                 ["속초"]),
        (["중앙"],                 ["춘천"],                 ["부산"]),
        (["대호", "당진대전",
          "서산영덕"],             ["당진"],                 ["대전"]),
        (["평택제천"],             ["평택"],                 ["제천"]),
        (["순천완주"],             ["완주"],                 ["순천"]),
        (["광주대구"],             ["광주"],                 ["대구"]),
        (["무안광주"],             ["광주"],                 ["무안"]),
        (["청주상주"],             ["청주"],                 ["상주"]),
        (["서천공주"],             ["공주"],                 ["서천"]),
        (["청주영덕"],             ["청주"],                 ["영덕"]),
        (["새만금포항", "새만금"], ["익산"],                 ["장수", "포항"]),
        (["당진영덕"],             [],                       ["영덕"]),
        (["대구포항"],             [],                       ["대구", "포항"]),
        (["수도권제1순환",
          "수도권"],               ["판교"],                 ["일산"]),
        (["대전남부순환",
          "대전남부"],             ["산내"],                 ["서대전"]),
        (["통영대구"],             ["대구"],                 ["통영"]),
    ]

    for dir_keys, up_kws, down_kws in ROUTE_TABLE:
        # 노선 식별: direction 컬럼(노선 유형) 또는 route 컬럼에 키워드 포함
        if any(k in d for k in dir_keys) or any(k in r for k in dir_keys):
            # 종점 키워드를 route(노선명) AND direction(방향/종점도시) 양쪽에서 탐색
            in_up   = any(kw in r for kw in up_kws)   or any(kw in d for kw in up_kws)
            in_down = any(kw in r for kw in down_kws) or any(kw in d for kw in down_kws)
            if up_kws and in_up:
                return "상행선"
            if down_kws and in_down:
                return "하행선"

    return "미분류"

@st.cache_data(show_spinner=False)
def parse_csv_bytes(data: bytes, year: int) -> pd.DataFrame:
    enc = detect_encoding(data)
    try:
        df = pd.read_csv(BytesIO(data), encoding=enc)
    except Exception:
        df = pd.read_csv(BytesIO(data), encoding="cp949")

    df = normalize_df(df)

    # direction(방향) 컬럼은 상하행 컬럼이 있으면 필수 아님
    required = ["region", "route", "section", "count", "lat", "lng"]
    if "dir_yn" not in df.columns:          # 상하행 컬럼 없으면 방향 필수
        required.append("direction")
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

    # ── 상하행 컬럼 생성 ──────────────────────────────────────────────
    # CSV에 상하행 컬럼이 있으면 직접 사용, 없으면 노선명·방향으로 자동 판별
    if "dir_yn" in df.columns:
        # CSV 값: "상행"/"하행" → 내부 표준값: "상행선"/"하행선"/"미분류"
        df["dir_yn"] = (
            df["dir_yn"].fillna("").astype(str).str.strip()
            .map({"상행": "상행선", "하행": "하행선"})
            .fillna("미분류")
        )
    else:
        df["dir_yn"] = df.apply(
            lambda r: _assign_dir_yn(r["route"], r["direction"]), axis=1
        )

    return df[["year", "region", "branch", "route", "section",
               "direction", "dir_yn", "km_start", "count", "lat", "lng"]].reset_index(drop=True)

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

# 파일명 메타 로드 (새로고침 후에도 유지)
if "filenames" not in st.session_state:
    _fn_path = DATA_DIR / "filenames.json"
    if _fn_path.exists():
        import json as _json
        try:
            _raw = _json.loads(_fn_path.read_text(encoding="utf-8"))
            # 키를 int로 통일
            st.session_state["filenames"] = {int(k): v for k, v in _raw.items()}
        except Exception:
            st.session_state["filenames"] = {}
    else:
        st.session_state["filenames"] = {}

# ── dir_yn 컬럼 역호환 패치 ─────────────────────────────────────────────────
# 구버전 캐시 데이터에 dir_yn 컬럼이 없을 경우 즉석 생성
for _yr, _df in all_data.items():
    if "dir_yn" not in _df.columns:
        all_data[_yr] = _df.assign(
            dir_yn=_df.apply(
                lambda row: _assign_dir_yn(row["route"], row.get("direction", "")), axis=1
            )
        )
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

def _section_radius(section_str: str, default_km: int = 5) -> int:
    """구간 문자열에서 km 길이를 추출해 반경(m) 반환. 예: ' 260~265 ' → 2500m"""
    import re
    m = re.search(r"(\d+\.?\d*)\s*[~～\-]\s*(\d+\.?\d*)", str(section_str))
    if m:
        length_km = abs(float(m.group(2)) - float(m.group(1)))
        return max(int(length_km * 500), 500)
    return default_km * 500

def _risk_color(norm: float):
    """norm 0~1 → [R,G,B,A]. 최솟값(0)=초록, 최댓값(1)=빨강, 중간=노랑."""
    if norm >= 1.0:
        return [239, 68,  68,  230]   # 빨강 (최댓값)
    elif norm <= 0.0:
        return [34,  197, 94,  230]   # 초록 (최솟값)
    else:
        return [234, 179, 8,   230]   # 노랑 (중간)

def make_map_lines(df: pd.DataFrame, min_count: int = -1, max_count: int = 0):
    """구간을 점(ScatterplotLayer)으로 표시. 최솟값=초록, 중간=노랑, 최댓값=빨강.
    - 지사+노선+구간 동일 & 건수 동일  → 점 1개, 툴팁에 양방향 표시
    - 지사+노선+구간 동일 & 건수 다름  → 각각 살짝 어긋난 점으로 표시
    """
    need = ["lat","lng","count","route","section","direction","dir_yn","km_start","branch"]
    mdf  = df[[c for c in need if c in df.columns]].dropna(subset=["lat","lng"]).copy()
    if mdf.empty:
        return None

    # 방향 표시용 컬럼 결정
    dir_col = "direction" if "direction" in mdf.columns else ("dir_yn" if "dir_yn" in mdf.columns else None)

    # 그룹 기준: 지사+노선+구간
    grp_keys = [k for k in ["branch","route","section"] if k in mdf.columns]

    OFFSET = 0.008   # ~800m 어긋남
    result_rows = []

    for _, grp in mdf.groupby(grp_keys, sort=False):
        grp    = grp.reset_index(drop=True)
        lat0   = float(grp["lat"].iloc[0])
        lng0   = float(grp["lng"].iloc[0])
        counts = grp["count"].tolist()
        dirs   = grp[dir_col].astype(str).tolist() if dir_col else [""] * len(grp)

        if len(grp) > 1 and len(set(counts)) == 1:
            # 건수 동일 → 점 1개, 방향 병합
            base = grp.iloc[0].to_dict()
            base["lat"]          = lat0
            base["lng"]          = lng0
            base["_tooltip_dir"] = " / ".join(dirs)
            result_rows.append(base)
        else:
            # 단일 행 or 건수 다름 → 각각 위도 방향으로 어긋나게
            n = len(grp)
            for i in range(n):
                base = grp.iloc[i].to_dict()
                offset = (i - (n - 1) / 2) * OFFSET
                base["lat"]          = lat0 + offset
                base["lng"]          = lng0
                base["_tooltip_dir"] = dirs[i]
                result_rows.append(base)

    if not result_rows:
        return None

    result = pd.DataFrame(result_rows).reset_index(drop=True)

    min_c   = min_count if min_count >= 0 else int(result["count"].min())
    max_c   = max_count if max_count > 0  else int(result["count"].max())
    range_c = (max_c - min_c) or 1
    result["norm"]   = ((result["count"] - min_c) / range_c).clip(0, 1)
    result["r"]      = result["norm"].apply(lambda n: _risk_color(n)[0])
    result["g"]      = result["norm"].apply(lambda n: _risk_color(n)[1])
    result["b"]      = result["norm"].apply(lambda n: _risk_color(n)[2])
    result["a"]      = result["norm"].apply(lambda n: _risk_color(n)[3])
    result["radius"] = result["section"].apply(_section_radius)
    result["tooltip"] = (
        result["route"] + "  " + result["section"] + "\n"
        + "방향: " + result["_tooltip_dir"] + " | " + result["count"].astype(str) + "건"
    )

    layer = pdk.Layer(
        "ScatterplotLayer", result,
        get_position=["lng", "lat"],
        get_color=["r", "g", "b", "a"],
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

def _delta_html(label: str, delta_str: str) -> str:
    """작년대비/평균대비 한 줄 HTML 조각."""
    stripped = delta_str.lstrip("+-")
    is_zero  = stripped.startswith("0건") or stripped.startswith("0.00건")
    if is_zero or delta_str[0] not in ("+", "-"):
        color = "#555"
        arrow = ""
        num   = delta_str
    else:
        is_up = delta_str.startswith("+")
        color = "#ef4444" if is_up else "#22c55e"
        arrow = "▲ " if is_up else "▼ "
        num   = delta_str[1:]
    return (
        f'<p style="color:#888;font-size:0.70rem;margin:6px 0 2px 0">{label}</p>'
        f'<p style="color:{color};font-size:0.88rem;margin:0;font-weight:600">{arrow}{num}</p>'
    )

def _metric_yoy(col, label: str, value: str, delta_str=None, avg_delta_str=None):
    """커스텀 KPI 카드. delta_str=작년대비, avg_delta_str=평균대비 (평균대비가 왼쪽)."""
    _CARD = "background:#ffffff;border-radius:8px;padding:14px 18px 12px;border:1px solid #e5e7eb;min-height:130px"
    if delta_str is None and avg_delta_str is None:
        col.markdown(f"""
<div style="{_CARD}">
  <p style="color:#555;font-size:0.82rem;margin:0 0 6px 0;font-weight:500">{label}</p>
  <p style="color:#111;font-size:2.1rem;font-weight:700;margin:0;line-height:1">{value}</p>
</div>""", unsafe_allow_html=True)
        return
    # 평균대비(왼) | 작년대비(오) 2열 레이아웃
    left  = _delta_html("평균대비", avg_delta_str) if avg_delta_str is not None else ""
    right = _delta_html("작년대비", delta_str)     if delta_str     is not None else ""
    if left and right:
        inner = (
            f'<div style="display:flex;gap:16px;margin-top:4px">'
            f'<div>{left}</div><div>{right}</div>'
            f'</div>'
        )
    else:
        inner = left or right
    col.markdown(f"""
<div style="{_CARD}">
  <p style="color:#555;font-size:0.82rem;margin:0 0 6px 0;font-weight:500">{label}</p>
  <p style="color:#111;font-size:2.1rem;font-weight:700;margin:0 0 4px 0;line-height:1">{value}</p>
  {inner}
</div>""", unsafe_allow_html=True)

def _fmt_delta(diff, base, unit="건") -> str:
    s = "+" if diff >= 0 else "-"
    pct = abs(round(diff / base * 100, 1)) if base else 0
    if isinstance(diff, float):
        return f"{s}{abs(diff):.2f}{unit} ({pct}%)"
    return f"{s}{abs(diff):,}{unit} ({pct}%)"

def kpi_row(df: pd.DataFrame, prev_df: pd.DataFrame = None,
            all_years_data: dict = None, show_yearly_avg: bool = False):
    """KPI 카드 렌더링. show_yearly_avg=True 시 연평균 발생건수 카드 추가."""
    total = int(df["count"].sum())
    avg   = round(float(df["count"].mean()), 2)
    max_c = int(df["count"].max())
    rc    = df.groupby("route")["count"].sum()
    top_r = rc.idxmax() if not rc.empty else "—"

    delta_total = delta_avg = None
    if prev_df is not None and not prev_df.empty:
        pt = int(prev_df["count"].sum())
        pa = round(float(prev_df["count"].mean()), 2)
        if pt > 0:
            delta_total = _fmt_delta(total - pt, pt)
        if pa > 0:
            delta_avg = _fmt_delta(round(avg - pa, 2), pa)

    avg_delta_total = avg_delta_avg = avg_delta_max = None
    mean_total = None
    if all_years_data and len(all_years_data) > 1:
        yr_totals  = [int(d["count"].sum())  for d in all_years_data.values()]
        yr_maxs    = [int(d["count"].max())  for d in all_years_data.values()]
        mean_total = round(sum(yr_totals) / len(yr_totals), 2)
        all_concat = pd.concat(list(all_years_data.values()), ignore_index=True)
        mean_avg   = round(float(all_concat["count"].mean()), 2)
        mean_max   = round(sum(yr_maxs)   / len(yr_maxs),   2)
        if mean_total:
            avg_delta_total = _fmt_delta(total - mean_total, mean_total)
        if mean_avg:
            avg_delta_avg = _fmt_delta(round(avg - mean_avg, 2), mean_avg)
        if mean_max:
            avg_delta_max = _fmt_delta(max_c - mean_max, mean_max)

    if show_yearly_avg and mean_total is not None:
        c1, c2, c3, c4, c5 = st.columns(5)
        _metric_yoy(c1, "총 발생건수",        f"{total:,}건",        delta_total)
        _metric_yoy(c2, "연평균 발생건수",    f"{mean_total:,.1f}건")
        _metric_yoy(c3, "구간 평균 발생건수", f"{avg}건",             delta_avg)
        _metric_yoy(c4, "최다 발생건",        f"{max_c:,}건",         None,        avg_delta_max)
        _metric_yoy(c5, "최고위험 노선",      top_r)
    else:
        c1, c2, c3, c4 = st.columns(4)
        _metric_yoy(c1, "총 발생건수",        f"{total:,}건", delta_total, avg_delta_total)
        _metric_yoy(c2, "구간 평균 발생건수", f"{avg}건",     delta_avg,   avg_delta_avg)
        _metric_yoy(c3, "최다 발생건",        f"{max_c:,}건", None,        avg_delta_max)
        _metric_yoy(c4, "최고위험 노선",      top_r)

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
    fig.update_traces(
        hovertemplate="노선: %{y}<br>발생건수: %{x:,}건<extra></extra>"
    )
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
    fig.update_traces(
        hovertemplate="본부: %{label}<br>발생건수: %{value:,}건<br>비율: %{percent}<extra></extra>"
    )
    fig.update_layout(
        paper_bgcolor=DARK_BG, font=FONT,
        legend=dict(orientation="h", yanchor="top", y=-0.05),
        margin=dict(l=10, r=10, t=10, b=40), height=360,
    )
    return fig

def detail_table(df: pd.DataFrame, key_prefix: str, enable_selection: bool = False):
    """검색·필터(연쇄)·테이블·CSV 다운로드 블록."""
    # ── 필터 헤더 라벨 ────────────────────────────────────────────────
    lc1, lc2, lc3, lc4, lc5 = st.columns([2, 1.4, 1.4, 1.4, 1])
    lc1.caption("검색")
    lc2.caption("본부")
    lc3.caption("지사")
    lc4.caption("노선")
    lc5.caption("최소 건수")

    cf1, cf2, cf3, cf4, cf5 = st.columns([2, 1.4, 1.4, 1.4, 1])

    with cf1:
        search = st.text_input("검색", placeholder="노선·구간·방향 검색…",
                               label_visibility="collapsed",
                               key=f"{key_prefix}_search")
    with cf2:
        reg_opts = ["전체 본부"] + sorted(df["region"].dropna().unique().tolist())
        sel_reg  = st.selectbox("본부", reg_opts, label_visibility="collapsed",
                                key=f"{key_prefix}_reg")

    # 본부 → 지사 연쇄
    tmp_reg = df if sel_reg == "전체 본부" else df[df["region"] == sel_reg]

    with cf3:
        br_list = sorted(tmp_reg["branch"].dropna().unique().tolist()) if "branch" in tmp_reg.columns else []
        br_opts = ["전체 지사"] + br_list
        sel_br  = st.selectbox("지사", br_opts, label_visibility="collapsed",
                               key=f"{key_prefix}_br")

    # 본부+지사 → 노선 연쇄
    tmp_br = tmp_reg if sel_br == "전체 지사" else tmp_reg[tmp_reg["branch"] == sel_br]

    with cf4:
        rt_opts = ["전체 노선"] + sorted(tmp_br["route"].dropna().unique().tolist())
        sel_rt  = st.selectbox("노선", rt_opts, label_visibility="collapsed",
                               key=f"{key_prefix}_rt")

    with cf5:
        min_cnt = st.number_input("최소 건수", 0, int(df["count"].max()), 0,
                                  label_visibility="collapsed",
                                  key=f"{key_prefix}_cnt")

    # ── 필터 적용 ─────────────────────────────────────────────────────
    fdf = df.copy()
    if search:
        search_cols = [c for c in ["route","section","direction","region","branch"] if c in fdf.columns]
        mask = fdf[search_cols].apply(
            lambda col: col.astype(str).str.contains(search, case=False, na=False)
        ).any(axis=1)
        fdf = fdf[mask]
    if sel_reg != "전체 본부":
        fdf = fdf[fdf["region"] == sel_reg]
    if sel_br != "전체 지사":
        fdf = fdf[fdf["branch"] == sel_br]
    if sel_rt != "전체 노선":
        fdf = fdf[fdf["route"] == sel_rt]
    if min_cnt > 0:
        fdf = fdf[fdf["count"] >= min_cnt]

    want_cols  = ["year","region","branch","route","section","direction","count"]
    rename_map = {
        "year":"연도","region":"본부","branch":"지사","route":"노선명",
        "section":"구간","direction":"방향","count":"발생건수",
    }
    avail_cols = [c for c in want_cols if c in fdf.columns]
    disp = fdf[avail_cols].rename(columns=rename_map)
    if "연도" in disp.columns:
        disp["연도"] = disp["연도"].astype(str) + "년"
    if "발생건수" in disp.columns:
        disp["발생건수"] = disp["발생건수"].astype(str) + "건"
    disp.index = range(1, len(disp) + 1)
    if enable_selection:
        sel_key   = f"{key_prefix}_sel"
        n_rows    = len(disp)

        # 전체 선택 / 전체 취소 버튼
        b1, b2, _ = st.columns([1, 1, 6])
        if b1.button("전체 선택", key=f"{key_prefix}_all", use_container_width=True):
            st.session_state[sel_key] = [True]  * n_rows
            st.rerun()
        if b2.button("전체 취소", key=f"{key_prefix}_none", use_container_width=True):
            st.session_state[sel_key] = [False] * n_rows
            st.rerun()

        # 세션 상태에서 체크 목록 읽기 (행 수 바뀌면 초기화)
        saved = st.session_state.get(sel_key, [])
        if len(saved) != n_rows:
            saved = [False] * n_rows

        disp_sel = disp.copy()
        disp_sel.insert(0, "선택", saved)

        edited = st.data_editor(
            disp_sel,
            use_container_width=True,
            height=360,
            hide_index=False,
            disabled=[c for c in disp_sel.columns if c != "선택"],
            column_config={"선택": st.column_config.CheckboxColumn("선택", default=False)},
            key=f"{key_prefix}_df",
        )
        st.session_state[sel_key] = edited["선택"].tolist()

        st.caption(f"총 {len(disp):,}건 | 체크박스로 행을 선택하면 해당 위치만 지도에 표시됩니다.")
        csv_out = disp.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button("⬇ CSV 내보내기", data=csv_out,
                           file_name=f"roadkill_{key_prefix}.csv",
                           mime="text/csv", key=f"{key_prefix}_dl")

        mask = edited["선택"].values
        sel_df = fdf[mask] if mask.any() else None
        return fdf, sel_df

    # ── 선택 불필요한 탭(전체집계 등) ────────────────────────────────
    styled = (
        disp.style
        .set_properties(**{"text-align": "center", "color": "black"})
        .set_table_styles([
            {"selector": "th", "props": [("text-align", "center"), ("color", "black")]},
            {"selector": "td", "props": [("text-align", "center"), ("color", "black")]},
        ])
    )
    st.caption(f"총 {len(disp):,}건")
    st.dataframe(styled, use_container_width=True, height=360)
    csv_out = disp.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button("⬇ CSV 내보내기", data=csv_out,
                       file_name=f"roadkill_{key_prefix}.csv",
                       mime="text/csv", key=f"{key_prefix}_dl")
    return fdf

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
        # KPI - 최근 연도 (연도 필터 적용 전 전체 데이터 기준)
        latest_y  = max(all_data.keys())
        prev_y    = max((y for y in all_data if y < latest_y), default=None)
        latest_df = all_data[latest_y]
        prev_df_l = all_data.get(prev_y)
        st.subheader(f"📌 최근 연도 ({latest_y}년) 집계")
        kpi_row(latest_df, prev_df_l, all_years_data=all_data)
        st.divider()

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
        kpi_row(all_df, all_years_data=all_data, show_yearly_avg=True)
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
                hovertemplate="<b>총 발생건수</b><br>연도: %{x}<br>건수: %{y:,}건<extra></extra>",
            ))
            fig_t.add_trace(go.Scatter(
                x=tdf["연도"], y=tdf["구간 평균"], name="구간 평균",
                mode="lines+markers",
                line=dict(color="#4f8ef7", width=2, dash="dot"),
                marker=dict(size=8), yaxis="y2",
                hovertemplate="<b>구간 평균</b><br>연도: %{x}<br>평균: %{y:.2f}건<extra></extra>",
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
            import pandas as _pd
            matrix_full = all_df.groupby(["route","year"])["count"].sum().unstack()
            matrix_full.columns = [f"{c}년" for c in matrix_full.columns]
            matrix_full["합계"] = matrix_full.sum(axis=1, skipna=True)
            # 연도별 합계는 전체 노선 기준으로 먼저 계산
            total_row = matrix_full.sum(axis=0, skipna=True).rename("연도별 합계")
            # 상위 25개 노선만 표시
            matrix = matrix_full.sort_values("합계", ascending=False).head(25)
            year_cols = [c for c in matrix.columns if c != "합계"]
            matrix = _pd.concat([matrix, total_row.to_frame().T])
            styled = (
                matrix.style
                .background_gradient(cmap="RdYlBu_r", subset=(_pd.IndexSlice[matrix.index[:-1], year_cols]))
                .background_gradient(cmap="Oranges",  subset=(_pd.IndexSlice[matrix.index[:-1], ["합계"]]))
                .background_gradient(cmap="Oranges",  subset=(_pd.IndexSlice[["연도별 합계"], year_cols]), axis=None)
                .set_properties(**{"background-color": "white"}, subset=(_pd.IndexSlice[["연도별 합계"], ["합계"]]))
                .highlight_null(color="white")
                .set_properties(**{"font-weight": "bold"}, subset=(_pd.IndexSlice[["연도별 합계"], :]))
                .format(lambda v: "-" if _pd.isna(v) else f"{v:.0f}")
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
  <span style="background:#fdd0a2;color:#333;padding:1px 6px;border-radius:3px">■ 낮음</span>&nbsp;→&nbsp;
  <span style="background:#8c2d04;color:white;padding:1px 6px;border-radius:3px">■ 높음</span>
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
        kpi_row(yr_df, prev_df, all_years_data=all_data)
        st.divider()

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
            fig_s.update_traces(
                hovertemplate="구간: %{y}<br>발생건수: %{x:,}건<extra></extra>"
            )
            fig_s.update_layout(
                paper_bgcolor=DARK_BG, plot_bgcolor=DARK_BG, font=FONT,
                showlegend=False, coloraxis_showscale=False,
                yaxis=dict(autorange="reversed", gridcolor="rgba(0,0,0,0)"),
                xaxis=dict(gridcolor=GRID),
                margin=dict(l=10, r=10, t=10, b=10), height=360,
            )
            st.plotly_chart(fig_s, use_container_width=True, key="tab2_top10")

        st.divider()

        # 상세 테이블 + 지점 지도
        st.subheader(f"📋 {sel_year}년 상세 데이터")
        filtered_df, selected_df = detail_table(yr_df, str(sel_year), enable_selection=True)

        yr_min = int(yr_df["count"].min()) if not yr_df.empty else 0
        yr_max = int(yr_df["count"].max()) if not yr_df.empty else 1
        if selected_df is not None and not selected_df.empty:
            map_src = selected_df
        elif filtered_df is not None and not filtered_df.empty:
            map_src = filtered_df
        else:
            map_src = yr_df
        deck_all = make_map_lines(map_src, yr_min, yr_max)
        if deck_all:
            st.pydeck_chart(deck_all, use_container_width=True, key="tab2_map_all")
        else:
            st.info("지도에 표시할 데이터가 없습니다.")
        st.markdown("""
<div style="font-size:0.78rem;color:#8892a4;margin-top:4px">
  <b>색상 기준</b> &nbsp;|&nbsp;
  <span style="background:#22c55e;color:#111;padding:1px 8px;border-radius:3px">■ 낮음</span>&nbsp;→&nbsp;
  <span style="background:#eab308;color:#111;padding:1px 8px;border-radius:3px">■ 중간</span>&nbsp;→&nbsp;
  <span style="background:#ef4444;color:white;padding:1px 8px;border-radius:3px">■ 높음</span>
  &nbsp;(해당 연도 최고 발생건수 기준)
</div>""", unsafe_allow_html=True)


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

    # ── 업로드 실행 함수 ────────────────────────────────────────────────────
    def _do_upload(year: int, raw: bytes, orig_name: str = ""):
        df_new = parse_csv_bytes(raw, year)
        st.session_state.all_data[year] = df_new
        (DATA_DIR / f"{year}_roadkill.csv").write_bytes(raw)
        # 원본 파일명 세션 + 디스크에 보관
        if "filenames" not in st.session_state:
            st.session_state["filenames"] = {}
        if orig_name:
            st.session_state["filenames"][year] = orig_name
        import json as _json
        _fn_path = DATA_DIR / "filenames.json"
        try:
            _fn_path.write_text(
                _json.dumps({str(k): v for k, v in st.session_state["filenames"].items()},
                             ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass
        st.cache_data.clear()
        st.session_state.pop("confirm_overwrite", None)
        st.session_state.pop("confirm_new",       None)
        st.session_state.pop("pending_year",      None)
        st.session_state.pop("pending_bytes",     None)
        st.session_state.pop("pending_name",      None)
        st.success(f"✅ {year}년 데이터 {len(df_new):,}건 추가 완료! 다른 탭으로 이동하면 바로 반영됩니다.")
        st.rerun()

    if st.button("📤 업로드", type="primary", key="btn_upload"):
        if up_file is None:
            st.warning("⚠️ CSV 파일을 먼저 선택해주세요.")
        elif int(up_year) in all_data:
            # 이미 존재 → 덮어쓰기 확인
            st.session_state["pending_year"]      = int(up_year)
            st.session_state["pending_bytes"]     = up_file.read()
            st.session_state["pending_name"]      = up_file.name
            st.session_state["confirm_overwrite"] = True
        else:
            # 신규 연도 → 추가 확인
            st.session_state["pending_year"]  = int(up_year)
            st.session_state["pending_bytes"] = up_file.read()
            st.session_state["pending_name"]  = up_file.name
            st.session_state["confirm_new"]   = True

    # ── 중복 연도 덮어쓰기 확인 알림 ────────────────────────────────────────
    if st.session_state.get("confirm_overwrite"):
        dup_y = st.session_state["pending_year"]
        st.warning(
            f"⚠️ **{dup_y}년** 데이터가 이미 추가되어 있습니다.  \n"
            f"정말 덮어쓰시겠습니까?"
        )
        btn_yes, btn_no = st.columns([1, 1])
        with btn_yes:
            if st.button("✅ 예, 덮어쓰기", type="primary",
                         use_container_width=True, key="btn_overwrite_yes"):
                with st.spinner(f"{dup_y}년 데이터 덮어쓰기 중…"):
                    try:
                        _do_upload(dup_y, st.session_state["pending_bytes"],
                                   st.session_state.get("pending_name", ""))
                    except Exception as e:
                        st.error(f"❌ 오류: {e}")
        with btn_no:
            if st.button("❌ 취소", use_container_width=True, key="btn_overwrite_no"):
                st.session_state.pop("confirm_overwrite", None)
                st.session_state.pop("pending_year",      None)
                st.session_state.pop("pending_bytes",     None)
                st.rerun()

    # ── 신규 연도 추가 확인 알림 ────────────────────────────────────────────
    if st.session_state.get("confirm_new"):
        new_y = st.session_state["pending_year"]
        st.info(f"📂 **{new_y}년** 데이터를 추가합니다. 정말 추가하시겠습니까?")
        btn_ny, btn_nn = st.columns([1, 1])
        with btn_ny:
            if st.button("✅ 예, 추가", type="primary",
                         use_container_width=True, key="btn_new_yes"):
                with st.spinner(f"{new_y}년 데이터 처리 중…"):
                    try:
                        _do_upload(new_y, st.session_state["pending_bytes"],
                                   st.session_state.get("pending_name", ""))
                    except Exception as e:
                        st.error(f"❌ 오류: {e}")
        with btn_nn:
            if st.button("❌ 취소", use_container_width=True, key="btn_new_no"):
                st.session_state.pop("confirm_new",   None)
                st.session_state.pop("pending_year",  None)
                st.session_state.pop("pending_bytes", None)
                st.session_state.pop("pending_name",  None)
                st.rerun()

    st.divider()

    # ── 등록된 연도 목록 ─────────────────────────────────────────────────────
    st.markdown("### 📋 현재 등록된 연도 목록")
    if not all_data:
        st.info("등록된 데이터가 없습니다.")
    else:
        fn_meta = st.session_state.get("filenames", {})
        summary_rows = []
        for y in sorted(all_data.keys(), reverse=True):
            ydf = all_data[y]
            summary_rows.append({
                "연도":          f"{y}년",
                "총 발생건수":   f"{int(ydf['count'].sum()):,}건",
                "구간 수":       f"{len(ydf):,}개",
                "노선 수":       f"{ydf['route'].nunique()}개",
                "지역(본부) 수": f"{ydf['region'].nunique()}개",
                "파일명":        fn_meta.get(y, f"{y}_roadkill.csv"),
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
                st.session_state["confirm_delete"] = del_year

    if st.session_state.get("confirm_delete") is not None:
        d_y = st.session_state["confirm_delete"]
        st.warning(f"⚠️ **{d_y}년** 데이터를 삭제합니다. 정말 삭제하시겠습니까?")
        btn_dy, btn_dn = st.columns([1, 1])
        with btn_dy:
            if st.button("✅ 예, 삭제", type="primary",
                         use_container_width=True, key="btn_del_yes"):
                del st.session_state.all_data[d_y]
                p = DATA_DIR / f"{d_y}_roadkill.csv"
                if p.exists():
                    p.unlink()
                # 파일명 세션 + 디스크에서 제거
                st.session_state.get("filenames", {}).pop(d_y, None)
                import json as _json
                _fn_path = DATA_DIR / "filenames.json"
                try:
                    _fn_path.write_text(
                        _json.dumps({str(k): v for k, v in st.session_state.get("filenames", {}).items()},
                                     ensure_ascii=False),
                        encoding="utf-8"
                    )
                except Exception:
                    pass
                st.session_state.pop("confirm_delete", None)
                st.success(f"✅ {d_y}년 데이터가 삭제되었습니다.")
                st.rerun()
        with btn_dn:
            if st.button("❌ 취소", use_container_width=True, key="btn_del_no"):
                st.session_state.pop("confirm_delete", None)
                st.rerun()
