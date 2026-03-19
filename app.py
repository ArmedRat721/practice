# app.py
# Plotly + Google Fonts(Noto Sans KR) → 한글 깨짐 완전 해결

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# ─────────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────────
st.set_page_config(
    page_title="AIV 생명 보호 실드",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────
# Google Fonts + CSS 주입
# Noto Sans KR을 웹폰트로 직접 로드 → 서버 폰트 무관
# ─────────────────────────────────────────
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;800&display=swap" rel="stylesheet">

<style>
    /* 전체 앱 폰트 */
    html, body, [class*="css"] {
        font-family: 'Noto Sans KR', sans-serif !important;
    }

    .stApp { background-color: #f8fafc; }

    [data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid #e2e8f0;
    }

    .main-title {
        font-family: 'Noto Sans KR', sans-serif;
        font-size: 2rem;
        font-weight: 800;
        color: #1e293b;
        letter-spacing: -0.5px;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-family: 'Noto Sans KR', sans-serif;
        font-size: 0.95rem;
        color: #64748b;
        margin-bottom: 1.8rem;
    }
    .section-header {
        font-family: 'Noto Sans KR', sans-serif;
        font-size: 1.05rem;
        font-weight: 700;
        color: #1e293b;
        border-left: 4px solid #3b82f6;
        padding-left: 10px;
        margin: 1.8rem 0 1rem 0;
    }

    [data-testid="metric-container"] {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    [data-testid="metric-container"] label {
        color: #64748b !important;
        font-size: 0.85rem !important;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #1e293b !important;
        font-size: 1.7rem !important;
        font-weight: 800 !important;
    }

    .stTabs [aria-selected="true"] {
        color: #3b82f6 !important;
        border-bottom-color: #3b82f6 !important;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
# Plotly 공통 폰트·레이아웃
# "Noto Sans KR"을 직접 지정
# ─────────────────────────────────────────
KR_FONT = "Noto Sans KR"
ACCENT  = "#3b82f6"
ACCENT2 = "#10b981"
ACCENT3 = "#f59e0b"
TEXT    = "#1e293b"
GRID    = "#e2e8f0"

def base_layout(title=""):
    return dict(
        title=dict(text=title, font=dict(family=KR_FONT, size=15, color=TEXT), x=0.02),
        font=dict(family=KR_FONT, size=12, color=TEXT),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        margin=dict(l=50, r=20, t=55, b=45),
        xaxis=dict(showgrid=False, linecolor=GRID, tickfont=dict(family=KR_FONT, size=12)),
        yaxis=dict(gridcolor=GRID, gridwidth=1, linecolor=GRID, tickfont=dict(family=KR_FONT, size=12)),
        legend=dict(font=dict(family=KR_FONT, size=12), bgcolor="rgba(255,255,255,0.9)",
                    bordercolor=GRID, borderwidth=1),
        hoverlabel=dict(font=dict(family=KR_FONT)),
    )

# ─────────────────────────────────────────
# 타이틀
# ─────────────────────────────────────────
st.markdown('<div class="main-title">🛡️ AIV 생명 보호 실드 대시보드</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">감염병 대응 현황 및 정책 효과 시뮬레이션</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────────
uploaded_file = st.file_uploader("📂 CSV 파일 업로드 (없으면 기본 데이터 사용)", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
else:
    data = {
        "지역":   ["서울", "경기", "인천", "강원", "전북", "경북", "전남"],
        "확진자": [98503, 63552, 37195, 7787,  9606,  11174, 6202],
        "사망자": [4196,  3787,  2183,  858,   950,   1063,  581],
        "치명률": [4.26,  5.96,  5.87,  11.02, 9.89,  9.52,  9.37],
        "유형":   ["도시", "도시", "도시", "지방", "지방", "지방", "지방"],
        "보급률": [95, 93, 91, 78, 76, 79, 74],
        "R값":    [3.8, 3.5, 3.4, 1.9, 2.0, 2.1, 1.7],
    }
    df = pd.DataFrame(data)

# ─────────────────────────────────────────
# 사이드바
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔎 필터 설정")
    st.markdown("---")
    region_type = st.multiselect(
        "지역 유형 선택",
        df["유형"].unique(),
        default=df["유형"].unique(),
    )
    st.markdown("---")
    st.caption("AIV 생명 보호 실드 정책 보고서\n데이터 기반 대시보드 v1.0")

filtered_df = df[df["유형"].isin(region_type)]

# ─────────────────────────────────────────
# 1. 핵심 지표 (KPI)
# ─────────────────────────────────────────
st.markdown('<div class="section-header">📊 핵심 지표</div>', unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
c1.metric("총 확진자",   f"{filtered_df['확진자'].sum():,}명")
c2.metric("총 사망자",   f"{filtered_df['사망자'].sum():,}명")
c3.metric("평균 치명률", f"{filtered_df['치명률'].mean():.2f}%")
c4.metric("평균 R값",    f"{filtered_df['R값'].mean():.2f}")

# ─────────────────────────────────────────
# 2. 데이터 테이블
# ─────────────────────────────────────────
st.markdown('<div class="section-header">📋 데이터</div>', unsafe_allow_html=True)
st.dataframe(filtered_df, use_container_width=True, height=260)

# ─────────────────────────────────────────
# 3. 지역별 분석 차트
# ─────────────────────────────────────────
st.markdown('<div class="section-header">📍 지역별 분석</div>', unsafe_allow_html=True)

col_a, col_b = st.columns(2)

with col_a:
    colors = [ACCENT if t == "도시" else ACCENT2 for t in filtered_df["유형"]]
    fig1 = go.Figure()
    fig1.add_trace(go.Bar(
        x=filtered_df["지역"],
        y=filtered_df["치명률"],
        marker_color=colors,
        text=[f"{v:.1f}%" for v in filtered_df["치명률"]],
        textposition="outside",
        textfont=dict(family=KR_FONT, size=11, color=TEXT),
        hovertemplate="%{x}: %{y:.2f}%<extra></extra>",
    ))
    fig1.update_layout(**base_layout("지역별 치명률"),
                       yaxis_title="치명률 (%)",
                       showlegend=False)
    st.plotly_chart(fig1, use_container_width=True)

with col_b:
    grouped = filtered_df.groupby("유형")["치명률"].mean().reset_index()
    bar_colors = [ACCENT if t == "도시" else ACCENT2 for t in grouped["유형"]]
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        x=grouped["유형"],
        y=grouped["치명률"],
        marker_color=bar_colors,
        text=[f"{v:.2f}%" for v in grouped["치명률"]],
        textposition="outside",
        textfont=dict(family=KR_FONT, size=12, color=TEXT),
        hovertemplate="%{x}: %{y:.2f}%<extra></extra>",
        width=0.4,
    ))
    fig2.update_layout(**base_layout("도시 vs 지방 평균 치명률"),
                       yaxis_title="평균 치명률 (%)",
                       showlegend=False)
    st.plotly_chart(fig2, use_container_width=True)

# ─────────────────────────────────────────
# 4. 산점도
# ─────────────────────────────────────────
st.markdown('<div class="section-header">📡 보급률 vs 감염재생산지수(R)</div>', unsafe_allow_html=True)

fig3 = go.Figure()
for utype, color in [("도시", ACCENT), ("지방", ACCENT2)]:
    sub = filtered_df[filtered_df["유형"] == utype]
    fig3.add_trace(go.Scatter(
        x=sub["보급률"],
        y=sub["R값"],
        mode="markers+text",
        name=utype,
        marker=dict(color=color, size=14, line=dict(color="white", width=1.5)),
        text=sub["지역"],
        textposition="top right",
        textfont=dict(family=KR_FONT, size=12, color=TEXT),
        hovertemplate="%{text}<br>보급률: %{x}%<br>R값: %{y}<extra></extra>",
    ))
fig3.update_layout(**base_layout("보급률 vs R값 관계"),
                   xaxis_title="보급률 (%)",
                   yaxis_title="R값")
st.plotly_chart(fig3, use_container_width=True)

# ─────────────────────────────────────────
# 5. 정책 시뮬레이션
# ─────────────────────────────────────────
st.markdown('<div class="section-header">🧪 정책 효과 시뮬레이션</div>', unsafe_allow_html=True)

reduction = st.slider("치명률 감소율 적용 (%)", 0, 50, 20, format="%d%%")

sim_df = filtered_df.copy()
sim_df["예상 치명률"] = sim_df["치명률"] * (1 - reduction / 100)

fig4 = go.Figure()
fig4.add_trace(go.Bar(
    name="현재 치명률",
    x=sim_df["지역"],
    y=sim_df["치명률"],
    marker_color=ACCENT,
    hovertemplate="%{x} 현재: %{y:.2f}%<extra></extra>",
))
fig4.add_trace(go.Bar(
    name=f"정책 적용 후 (−{reduction}%)",
    x=sim_df["지역"],
    y=sim_df["예상 치명률"],
    marker_color=ACCENT3,
    hovertemplate="%{x} 예상: %{y:.2f}%<extra></extra>",
))
fig4.update_layout(**base_layout("정책 적용 전/후 치명률 비교"),
                   barmode="group",
                   yaxis_title="치명률 (%)")
st.plotly_chart(fig4, use_container_width=True)

# ─────────────────────────────────────────
# 6. 정책 전략
# ─────────────────────────────────────────
st.markdown('<div class="section-header">🧠 정책 전략</div>', unsafe_allow_html=True)

tab1, tab2 = st.tabs(["🚑 전략 1 — 모바일 ICU", "👴 전략 2 — 고위험군 보호"])

with tab1:
    st.markdown("""
    #### 🚑 모바일 ICU 운영
    - **의료 접근 시간 단축**: 골든타임 내 현장 대응
    - **중증 환자 현장 치료**: 이송 부담 최소화
    - **지방 치명률 감소 핵심 전략**: 의료 공백 지역 집중 배치
    """)

with tab2:
    st.markdown("""
    #### 👴 고위험군 집중 보호
    - **65세 이상 집중 관리**: 맞춤형 모니터링 체계
    - **6시간 내 항바이러스제 투약**: 신속 처방 프로토콜
    - **방문 검진 + 24시간 핫라인**: 능동적 건강 관리 지원
    """)
