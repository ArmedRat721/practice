# app.py
 
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib as mpl
import platform
import os
 
# ─────────────────────────────────────────
# 한글 폰트 설정 (글자 깨짐 방지)
# ─────────────────────────────────────────
def set_korean_font():
    system = platform.system()
    if system == "Windows":
        font_name = "Malgun Gothic"
    elif system == "Darwin":
        font_name = "AppleGothic"
    else:
        # Linux (Streamlit Cloud 등): NanumGothic 우선 시도
        candidates = [
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
        font_path = next((p for p in candidates if os.path.exists(p)), None)
        if font_path:
            fe = fm.FontEntry(fname=font_path, name="KoreanFont")
            fm.fontManager.ttflist.insert(0, fe)
            font_name = "KoreanFont"
        else:
            font_name = "DejaVu Sans"
 
    mpl.rcParams["font.family"] = font_name
    mpl.rcParams["axes.unicode_minus"] = False  # 마이너스 기호 깨짐 방지
 
set_korean_font()
 
# ─────────────────────────────────────────
# 페이지 설정 & 커스텀 CSS
# ─────────────────────────────────────────
st.set_page_config(
    page_title="AIV 생명 보호 실드",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)
 
st.markdown("""
<style>
    /* 전체 배경 */
    .stApp { background-color: #0f172a; }
 
    /* 사이드바 */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
        border-right: 1px solid #334155;
    }
 
    /* 메인 타이틀 */
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #f1f5f9;
        letter-spacing: -0.5px;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1rem;
        color: #94a3b8;
        margin-bottom: 2rem;
    }
 
    /* 섹션 헤더 */
    .section-header {
        font-size: 1.1rem;
        font-weight: 700;
        color: #e2e8f0;
        border-left: 4px solid #3b82f6;
        padding-left: 10px;
        margin: 1.8rem 0 1rem 0;
    }
 
    /* KPI 카드 */
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #1e293b, #263347);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    [data-testid="metric-container"] label {
        color: #94a3b8 !important;
        font-size: 0.85rem !important;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #f1f5f9 !important;
        font-size: 1.8rem !important;
        font-weight: 800 !important;
    }
 
    /* 데이터프레임 */
    [data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
    }
 
    /* 탭 */
    .stTabs [data-baseweb="tab"] {
        color: #94a3b8;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        color: #3b82f6 !important;
        border-bottom-color: #3b82f6 !important;
    }
 
    /* 슬라이더 */
    .stSlider [data-baseweb="slider"] { color: #3b82f6; }
 
    /* 업로더 */
    [data-testid="stFileUploader"] {
        background: #1e293b;
        border: 2px dashed #334155;
        border-radius: 10px;
        padding: 0.5rem;
    }
    [data-testid="stFileUploader"]:hover { border-color: #3b82f6; }
</style>
""", unsafe_allow_html=True)
 
# ─────────────────────────────────────────
# 그래프 공통 스타일
# ─────────────────────────────────────────
DARK_BG   = "#1e293b"
DARK_GRID = "#334155"
TEXT_CLR  = "#e2e8f0"
ACCENT    = "#3b82f6"
ACCENT2   = "#10b981"
ACCENT3   = "#f59e0b"
 
def apply_dark_style(fig, ax, title=""):
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(DARK_BG)
    ax.tick_params(colors=TEXT_CLR, labelsize=10)
    ax.xaxis.label.set_color(TEXT_CLR)
    ax.yaxis.label.set_color(TEXT_CLR)
    ax.title.set_color(TEXT_CLR)
    ax.title.set_fontsize(13)
    ax.title.set_fontweight("bold")
    for spine in ax.spines.values():
        spine.set_edgecolor(DARK_GRID)
    ax.yaxis.grid(True, color=DARK_GRID, linewidth=0.7, linestyle="--")
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, pad=12)
 
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
        "확진자": [98503, 63552, 37195, 7787, 9606, 11174, 6202],
        "사망자": [4196,  3787,  2183,  858,  950,  1063,  581],
        "치명률": [4.26,  5.96,  5.87,  11.02, 9.89, 9.52, 9.37],
        "유형":   ["도시", "도시", "도시", "지방", "지방", "지방", "지방"],
        "보급률": [95, 93, 91, 78, 76, 79, 74],
        "R값":    [3.8, 3.5, 3.4, 1.9, 2.0, 2.1, 1.7],
    }
    df = pd.DataFrame(data)
 
# ─────────────────────────────────────────
# 사이드바 필터
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
    st.markdown("#### ℹ️ 정보")
    st.caption("AIV 생명 보호 실드 정책 보고서\n데이터 기반 대시보드 v1.0")
 
filtered_df = df[df["유형"].isin(region_type)]
 
# ─────────────────────────────────────────
# KPI
# ─────────────────────────────────────────
st.markdown('<div class="section-header">📊 핵심 지표</div>', unsafe_allow_html=True)
 
c1, c2, c3, c4 = st.columns(4)
c1.metric("총 확진자",   f"{filtered_df['확진자'].sum():,}명")
c2.metric("총 사망자",   f"{filtered_df['사망자'].sum():,}명")
c3.metric("평균 치명률", f"{filtered_df['치명률'].mean():.2f}%")
c4.metric("평균 R값",    f"{filtered_df['R값'].mean():.2f}")
 
# ─────────────────────────────────────────
# 그래프 행 1: 치명률 & 도시 vs 지방
# ─────────────────────────────────────────
st.markdown('<div class="section-header">📍 지역별 분석</div>', unsafe_allow_html=True)
 
col_a, col_b = st.columns(2)
 
with col_a:
    fig1, ax1 = plt.subplots(figsize=(6, 4))
    colors = [ACCENT if t == "도시" else ACCENT2 for t in filtered_df["유형"]]
    bars = ax1.bar(filtered_df["지역"], filtered_df["치명률"], color=colors,
                   width=0.6, edgecolor="none")
    for bar in bars:
        ax1.text(bar.get_x() + bar.get_width() / 2,
                 bar.get_height() + 0.1,
                 f"{bar.get_height():.1f}%",
                 ha="center", va="bottom", color=TEXT_CLR, fontsize=9)
    ax1.set_ylabel("치명률 (%)", color=TEXT_CLR)
    apply_dark_style(fig1, ax1, "지역별 치명률")
    # 범례
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=ACCENT, label="도시"),
                       Patch(facecolor=ACCENT2, label="지방")]
    ax1.legend(handles=legend_elements, facecolor=DARK_BG, edgecolor=DARK_GRID,
               labelcolor=TEXT_CLR, fontsize=9)
    fig1.tight_layout()
    st.pyplot(fig1)
 
with col_b:
    grouped = filtered_df.groupby("유형")["치명률"].mean()
    fig2, ax2 = plt.subplots(figsize=(6, 4))
    bar_colors = [ACCENT if t == "도시" else ACCENT2 for t in grouped.index]
    bars2 = ax2.bar(grouped.index, grouped.values, color=bar_colors,
                    width=0.4, edgecolor="none")
    for bar in bars2:
        ax2.text(bar.get_x() + bar.get_width() / 2,
                 bar.get_height() + 0.1,
                 f"{bar.get_height():.2f}%",
                 ha="center", va="bottom", color=TEXT_CLR, fontsize=10)
    ax2.set_ylabel("평균 치명률 (%)", color=TEXT_CLR)
    apply_dark_style(fig2, ax2, "도시 vs 지방 평균 치명률")
    fig2.tight_layout()
    st.pyplot(fig2)
 
# ─────────────────────────────────────────
# 그래프 행 2: 산점도
# ─────────────────────────────────────────
st.markdown('<div class="section-header">📡 보급률 vs 감염재생산지수(R)</div>', unsafe_allow_html=True)
 
fig3, ax3 = plt.subplots(figsize=(9, 4))
scatter_colors = [ACCENT if t == "도시" else ACCENT2 for t in filtered_df["유형"]]
sc = ax3.scatter(filtered_df["보급률"], filtered_df["R값"],
                 c=scatter_colors, s=120, zorder=5, edgecolors="#0f172a", linewidths=1.2)
 
for i in range(len(filtered_df)):
    ax3.text(
        filtered_df["보급률"].iloc[i] + 0.3,
        filtered_df["R값"].iloc[i] + 0.03,
        filtered_df["지역"].iloc[i],
        color=TEXT_CLR, fontsize=10,
    )
 
ax3.set_xlabel("보급률 (%)", color=TEXT_CLR)
ax3.set_ylabel("R값", color=TEXT_CLR)
apply_dark_style(fig3, ax3, "보급률 vs R값 관계")
from matplotlib.patches import Patch
leg3 = [Patch(facecolor=ACCENT, label="도시"), Patch(facecolor=ACCENT2, label="지방")]
ax3.legend(handles=leg3, facecolor=DARK_BG, edgecolor=DARK_GRID,
           labelcolor=TEXT_CLR, fontsize=9)
fig3.tight_layout()
st.pyplot(fig3)
 
# ─────────────────────────────────────────
# 정책 시뮬레이션
# ─────────────────────────────────────────
st.markdown('<div class="section-header">🧪 정책 효과 시뮬레이션</div>', unsafe_allow_html=True)
 
reduction = st.slider("치명률 감소율 적용 (%)", 0, 50, 20, format="%d%%")
 
sim_df = filtered_df.copy()
sim_df["예상 치명률"] = sim_df["치명률"] * (1 - reduction / 100)
 
fig4, ax4 = plt.subplots(figsize=(9, 4))
x = range(len(sim_df))
width = 0.35
 
ax4.bar([i - width/2 for i in x], sim_df["치명률"],
        width=width, color=ACCENT, label="현재 치명률", edgecolor="none")
ax4.bar([i + width/2 for i in x], sim_df["예상 치명률"],
        width=width, color=ACCENT3, label=f"정책 적용 후 (−{reduction}%)", edgecolor="none")
 
ax4.set_xticks(list(x))
ax4.set_xticklabels(sim_df["지역"].tolist(), color=TEXT_CLR)
ax4.set_ylabel("치명률 (%)", color=TEXT_CLR)
ax4.legend(facecolor=DARK_BG, edgecolor=DARK_GRID, labelcolor=TEXT_CLR, fontsize=9)
apply_dark_style(fig4, ax4, "정책 적용 전/후 치명률 비교")
fig4.tight_layout()
st.pyplot(fig4)
 
# ─────────────────────────────────────────
# 정책 전략
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
 
# ─────────────────────────────────────────
# 데이터 테이블
# ─────────────────────────────────────────
st.markdown('<div class="section-header">📋 원시 데이터</div>', unsafe_allow_html=True)
st.dataframe(filtered_df, use_container_width=True, height=280)
