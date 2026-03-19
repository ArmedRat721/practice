import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="AIV 생명 보호 실드 대시보드", layout="wide")

st.title("🛡️ AIV 생명 보호 실드 정책 대시보드")

# -----------------------------
# 데이터 (보고서 기반 샘플)
# -----------------------------
data = {
    "지역": ["서울", "경기", "인천", "강원", "전북", "경북", "전남"],
    "확진자": [98503, 63552, 37195, 7787, 9606, 11174, 6202],
    "사망자": [4196, 3787, 2183, 858, 950, 1063, 581],
    "치명률": [4.26, 5.96, 5.87, 11.02, 9.89, 9.52, 9.37],
    "유형": ["도시", "도시", "도시", "지방", "지방", "지방", "지방"]
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
# 지역별 치명률
# -----------------------------
st.subheader("📍 지역별 치명률 비교")

fig, ax = plt.subplots()
ax.bar(df["지역"], df["치명률"])
ax.set_ylabel("치명률 (%)")
ax.set_title("지역별 치명률")

st.pyplot(fig)

# -----------------------------
# 도시 vs 지방 비교
# -----------------------------
st.subheader("🏙️ 도시 vs 지방 치명률 비교")

grouped = df.groupby("유형")["치명률"].mean()

fig2, ax2 = plt.subplots()
ax2.bar(grouped.index, grouped.values)
ax2.set_ylabel("평균 치명률 (%)")
ax2.set_title("도시 vs 지방")

st.pyplot(fig2)

# -----------------------------
# 전략 요약
# -----------------------------
st.subheader("🧠 정책 전략 요약")

tab1, tab2 = st.tabs(["전략 1", "전략 2"])

with tab1:
    st.markdown("""
    ### 🚑 모바일 ICU
    
    - 의료 접근 시간 단축 (8.4시간 → 3시간 목표)
    - 중증 환자 현장 치료 가능
    - 의료 취약 지역 우선 배치
    """)

with tab2:
    st.markdown("""
    ### 👴 고위험군 집중 관리
    
    - 65세 이상 집중 모니터링
    - 확진 후 6시간 내 항바이러스제 투약
    - 방문 검진 및 실버 핫라인 운영
    """)

# -----------------------------
# 데이터 테이블
# -----------------------------
st.subheader("📋 상세 데이터")

st.dataframe(df)
