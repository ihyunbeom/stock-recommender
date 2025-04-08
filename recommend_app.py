import pandas as pd
import numpy as np
import streamlit as st
import FinanceDataReader as fdr
from datetime import datetime, timedelta

st.title("📈 단타 전략 종목 추천기 - 돌파 & 눌림목 전략")

# 날짜 설정
today = datetime.today()
start_date = today - timedelta(days=30)
start_str = start_date.strftime('%Y-%m-%d')

# 종목 리스트 불러오기
@st.cache_data
def get_stock_list():
    df = fdr.StockListing('KRX')
    df = df.sort_values(by='Marcap', ascending=False)
    return df[['Code', 'Name']].head(1000)

stock_list = get_stock_list()
breakout_list = []
pullback_list = []
status_text = st.empty()  # 여기에 종목 이름이 실시간으로 뜰 거야
progress = st.progress(0)
total = len(stock_list)

with st.spinner("종목 분석 중..."):
    for i, (_, row) in enumerate(stock_list.iterrows()):
        code = row['Code']
        name = row['Name']

        # 실시간 종목명 업데이트
        status_text.text(f"종목 분석 중... 잠시만 기다려 주세요 ⏳ ({name})")

        # 진행률 업데이트
        progress.progress((i + 1) / total)

        try:
            df = fdr.DataReader(code, start=start_str)
            
            # 거래 정지 종목 필터링 (경고 없는 버전)
            if df['Close'].iloc[-1] == 0 or df['Volume'].iloc[-1] == 0:
                continue
            
            # 3일 이상 연속 데이터가 없는 경우
            if len(df.dropna()) < 5:
                continue

            if len(df) < 20:
                continue

            df['MA20'] = df['Close'].rolling(window=20).mean()
            df = df.dropna()

            curr = df.iloc[-1]
            prev = df.iloc[-2]
            prev2 = df.iloc[-3]
            vol_avg = df['Volume'][-5:].mean()

            # ✅ 돌파 전략 조건
            if (
                prev['Close'] >= prev['High'] * 0.9 and
                prev['Volume'] >= vol_avg * 1.5 and
                prev['Close'] > prev['Open']
            ):
                entry_price = round(prev['High'] * 1.005, 2)
                stop_loss = round(prev['Close'] * 0.97, 2)
                target_price = round(prev['High'] * 1.05, 2)

                breakout_list.append({
                    '종목명': name,
                    '전략': '돌파',
                    '현재가': curr['Close'],
                    '매수가': entry_price,
                    '손절가': stop_loss,
                    '목표가': target_price,
                    '기준일': df.index[-2].strftime('%Y-%m-%d')
                })

            # ✅ 눌림목 전략 조건
            high3 = df.iloc[-4]['High']
            if (
                high3 * 0.9 <= curr['Close'] <= high3 * 0.95 and
                abs(curr['Close'] - curr['MA20']) / curr['MA20'] < 0.02 and
                curr['Volume'] < vol_avg
            ):
                entry_price = round(curr['Close'] * 1.005, 2)
                stop_loss = round(df.iloc[-1]['MA20'] * 0.98, 2)
                target_price = round(high3, 2)

                pullback_list.append({
                    '종목명': name,
                    '전략': '눌림목',
                    '현재가': curr['Close'],
                    '매수가': entry_price,
                    '손절가': stop_loss,
                    '목표가': target_price,
                    '기준일': df.index[-1].strftime('%Y-%m-%d')
                })

        except Exception as e:
            continue

# 결과 표시
if breakout_list or pullback_list:
    st.success(f"✅ 총 {len(breakout_list) + len(pullback_list)}개 종목이 조건에 부합했습니다.")

    if breakout_list:
        st.subheader("🔥 돌파 전략 추천 종목")
        st.dataframe(pd.DataFrame(breakout_list))

    if pullback_list:
        st.subheader("🌀 눌림목 전략 추천 종목")
        st.dataframe(pd.DataFrame(pullback_list))
else:
    st.warning("😥 조건에 맞는 종목이 없습니다. 내일 다시 시도해보세요.")
