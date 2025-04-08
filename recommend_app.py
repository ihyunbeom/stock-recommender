import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timedelta
from pykrx import stock

st.title("📈 단타 전략 종목 추천기 - 돌파 & 눌림목 전략")

# 날짜 설정
today = datetime.today()
start_date = today - timedelta(days=30)
start_str = start_date.strftime('%Y%m%d')
end_str = today.strftime('%Y%m%d')

# 종목 리스트 불러오기
@st.cache_data
def get_stock_list():
    codes = stock.get_market_ticker_list(market="ALL")
    names = [stock.get_market_ticker_name(code) for code in codes]
    df = pd.DataFrame({"Code": codes, "Name": names})
    return df.head(2000)  # 속도 위해 상위 100개만

stock_list = get_stock_list()
breakout_list = []
pullback_list = []

status_text = st.empty()
progress = st.progress(0)
total = len(stock_list)

with st.spinner("종목 분석 중..."):
    for i, row in enumerate(stock_list.itertuples(index=False)):
        code = row.Code
        name = row.Name

        status_text.text(f"종목 분석 중... 잠시만 기다려 주세요 ⏳ ({name})")
        progress.progress((i + 1) / total)

        try:
            df = stock.get_market_ohlcv_by_date(start_str, end_str, code)
            df = df.dropna()
            if len(df) < 20:
                continue

            df['MA20'] = df['종가'].rolling(window=20).mean()
            df = df.dropna()
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            high3 = df.iloc[-4]['고가']
            vol_avg = df['거래량'][-5:].mean()

            # 돌파 전략 조건
            if (
                prev['종가'] >= prev['고가'] * 0.9 and
                prev['거래량'] >= vol_avg * 1.5 and
                prev['종가'] > prev['시가']
            ):
                entry_price = round(prev['고가'] * 1.005, 2)
                stop_loss = round(prev['종가'] * 0.97, 2)
                target_price = round(prev['고가'] * 1.05, 2)

                breakout_list.append({
                    '종목명': name,
                    '전략': '돌파',
                    '현재가': curr['종가'],
                    '매수가': entry_price,
                    '손절가': stop_loss,
                    '목표가': target_price,
                    '기준일': df.index[-2].strftime('%Y-%m-%d')
                })

            # 눌림목 전략 조건
            if (
                high3 * 0.9 <= curr['종가'] <= high3 * 0.95 and
                abs(curr['종가'] - curr['MA20']) / curr['MA20'] < 0.02 and
                curr['거래량'] < vol_avg
            ):
                entry_price = round(curr['종가'] * 1.005, 2)
                stop_loss = round(curr['MA20'] * 0.98, 2)
                target_price = round(high3, 2)

                pullback_list.append({
                    '종목명': name,
                    '전략': '눌림목',
                    '현재가': curr['종가'],
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
