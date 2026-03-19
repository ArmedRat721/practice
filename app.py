# app.py

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="AIV 생명 보호 실드", layout="wide")

st.title("🛡️ AIV 생명 보호 실드 대시보드")

# -----------------------------
# 데이터 로드 (업로드 or 기본 데이터)
# -----------------------------
uploaded_file = st.file_uploader("📂 CSV 파일 업로드", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
else:
    data = {
        "지역": ["서울", "경기", "인천", "강원", "전북", "경북", "전남"],
        "확진자": [98503, 63552, 37195, 7787, 9606, 11174, 6202],
        "사망자": [4196, 3787, 2183, 858, 950, 1063, 581],
        "치명률": [4.26, 5.96, 5.87, 11.02, 9.89, 9.52, 9.37],
        "유형": ["도시", "도시", "도시", "지방", "지방", "지방", "지방"],
        "보급률": [95, 93, 91, 78, 76, 79, 74],
        "R값": [3.8, 3.5, 3.4, 1.9, 2.0, 2.1, 1.7]
    }
    df = pd.DataFrame(data)

# -----------------------------
# KPI
# -----------------------------
st.subheader("📊 핵심 지표")

col1, col2, col3 = st.columns(3)

col1.metric("총 확진자", f"{df['확진자'].sum():,}")
col2.metric("총 사망자", f"{df['사망자'].sum():,}")
col3.metric("평균 치명률", f"{df['치명률'].mean():.2f}%")

# -----------------------------
# 필터
# -----------------------------
st.sidebar.header("🔎 필터")
region_type = st.sidebar.multiselect("지역 유형 선택", df["유형"].unique(), default=df["유형"].unique())

filtered_df = df[df["유형"].isin(region_type)]

# -----------------------------
# 지역별 치명률
# -----------------------------
st.subheader("📍 지역별 치명률")

fig1, ax1 = plt.subplots()
ax1.bar(filtered_df["지역"], filtered_df["치명률"])
ax1.set_ylabel("치명률 (%)")
ax1.set_title("지역별 치명률")
st.pyplot(fig1)

# -----------------------------
# 도시 vs 지방
# -----------------------------
st.subheader("🏙️ 도시 vs 지방 비교")

grouped = filtered_df.groupby("유형")["치명률"].mean()

fig2, ax2 = plt.subplots()
ax2.bar(grouped.index, grouped.values)
ax2.set_ylabel("평균 치명률 (%)")
ax2.set_title("도시 vs 지방")
st.pyplot(fig2)

# -----------------------------
# 보급률 vs R값 (Scatter)
# -----------------------------
st.subheader("📡 보급률 vs 감염재생산지수(R)")

fig3, ax3 = plt.subplots()
ax3.scatter(filtered_df["보급률"], filtered_df["R값"])

for i in range(len(filtered_df)):
    ax3.text(filtered_df["보급률"].iloc[i], filtered_df["R값"].iloc[i], filtered_df["지역"].iloc[i])

ax3.set_xlabel("보급률 (%)")
ax3.set_ylabel("R값")
ax3.set_title("보급률 vs R값 관계")

st.pyplot(fig3)

# -----------------------------
# 정책 시뮬레이션
# -----------------------------
st.subheader("🧪 정책 효과 시뮬레이션")

reduction = st.slider("치명률 감소율 (%)", 0, 50, 20)

sim_df = filtered_df.copy()
sim_df["예상 치명률"] = sim_df["치명률"] * (1 - reduction / 100)

fig4, ax4 = plt.subplots()
ax4.bar(sim_df["지역"], sim_df["치명률"], label="현재")
ax4.bar(sim_df["지역"], sim_df["예상 치명률"], alpha=0.5, label="정책 적용 후")
ax4.legend()
ax4.set_title("정책 적용 전/후 치명률 비교")

st.pyplot(fig4)

# -----------------------------
# 전략 설명
# -----------------------------
st.subheader("🧠 정책 전략")

tab1, tab2 = st.tabs(["전략 1", "전략 2"])

with tab1:
    st.markdown("""
    ### 🚑 모바일 ICU
    - 의료 접근 시간 단축
    - 중증 환자 현장 치료
    - 지방 치명률 감소 핵심 전략
    """)

with tab2:
    st.markdown("""
    ### 👴 고위험군 보호
    - 65세 이상 집중 관리
    - 6시간 내 항바이러스제 투약
    - 방문 검진 + 핫라인
    """)

# -----------------------------
# 데이터 테이블
# -----------------------------
st.subheader("📋 데이터")

st.dataframe(filtered_df)
