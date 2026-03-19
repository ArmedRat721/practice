import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import platform

# -----------------------------
# 한글 폰트 설정
# -----------------------------
if platform.system() == 'Windows':
    plt.rc('font', family='Malgun Gothic')  # 윈도우
elif platform.system() == 'Darwin':
    plt.rc('font', family='AppleGothic')    # 맥
else:
    plt.rc('font', family='NanumGothic')    # 리눅스 (streamlit cloud 등)

plt.rcParams['axes.unicode_minus'] = False  # 마이너스 깨짐 방지

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="AIV 생명 보호 실드", layout="wide")
st.title("🛡️ AIV 생명 보호 실드 대시보드")

# -----------------------------
# 데이터
# -----------------------------
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
# 그래프 예시
# -----------------------------
st.subheader("📍 지역별 치명률")

fig, ax = plt.subplots()
ax.bar(df["지역"], df["치명률"])
ax.set_title("지역별 치명률")
ax.set_ylabel("치명률 (%)")

st.pyplot(fig)
