import streamlit as st
import pandas as pd
import numpy as np
from pykrx import stock
from datetime import datetime, timedelta
import ta
import time

st.set_page_config(page_title="스윙 전략 종목 추천기", layout="wide")
st.title("📈 스윙 전략 종목 추천기 (8가지 전략 적용)")
st.info("⚠️ 본 전략은 보통주만 대상으로 하며, **우선주는 자동 제외**됩니다.")
st.info("⚠️ 기본 조건 : 거래대금 5~10억 이상, 거래량 급등(3배) 이력이 있는 종목, 볼랜저 상단 5%이하, 매수가 기준 현재가 차이 2%이하 ")

# 날짜 설정
TODAY = datetime.today()
START_DATE = TODAY - timedelta(days=180)
start_str = START_DATE.strftime('%Y%m%d')
end_str = TODAY.strftime('%Y%m%d')

MIN_MARKET_CAP = 300_000_000_000  # 3000억

@st.cache_data
def get_filtered_stock_list():
    today_str = TODAY.strftime('%Y%m%d')
    cap_df = stock.get_market_cap_by_ticker(today_str).reset_index()
    cap_df['Name'] = cap_df['티커'].apply(stock.get_market_ticker_name)
    cap_df = cap_df.rename(columns={'티커': 'Code', '시가총액': 'MarketCap'})
    cap_df = cap_df[cap_df['MarketCap'] >= MIN_MARKET_CAP]
    cap_df = cap_df[~cap_df['Name'].str.contains(r'(?:우$|\d우[B|C]?$)', regex=True)]
    return cap_df[['Code', 'Name', 'MarketCap']].reset_index(drop=True)

stock_list = get_filtered_stock_list()
market_kospi = stock.get_market_ticker_list(market='KOSPI')
market_kosdaq = stock.get_market_ticker_list(market='KOSDAQ')
swing_candidates = []

status_text = st.empty()
progress = st.progress(0)
total = len(stock_list)

with st.spinner("종목 분석 중..."):
    for i, row in enumerate(stock_list.itertuples(index=False)):
        code, name, market_cap = row.Code, row.Name, row.MarketCap
        market_type = '코스피' if code in market_kospi else '코스닥'
        MIN_AMOUNT = 10_000_000_000 if market_type == '코스피' else 5_000_000_000

        status_text.text(f"종목 분석 중... ⏳ ({name})")
        progress.progress((i + 1) / total)

        try:
            df = stock.get_market_ohlcv_by_date(start_str, end_str, code)
            if df is None or df.empty or len(df) < 60:
                continue

            df['거래대금'] = df['종가'] * df['거래량']
            if df.iloc[-1]['거래대금'] < MIN_AMOUNT:
                continue

            df['MA5'] = df['종가'].rolling(window=5).mean()
            df['MA20'] = df['종가'].rolling(window=20).mean()
            df['MA40'] = df['종가'].rolling(window=40).mean()
            df['MA60'] = df['종가'].rolling(window=60).mean()
            df['RSI'] = ta.momentum.RSIIndicator(df['종가']).rsi()
            bb = ta.volatility.BollingerBands(df['종가'])
            df['BB_lower'] = bb.bollinger_lband()
            df['BB_upper'] = bb.bollinger_hband()
            df['MACD'] = ta.trend.MACD(df['종가']).macd()
            df['Signal'] = ta.trend.MACD(df['종가']).macd_signal()
            df['전일종가'] = df['종가'].shift(1)
            df['하락률'] = (df['종가'] - df['전일종가']) / df['전일종가'] * 100

            df = df.dropna()
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            최고가52 = df['종가'].rolling(window=260).max().iloc[-1]

            # 거래량 3배 이상 상승 여부
            거래량_3배_이상 = any(
                df['거래량'].iloc[i] >= df['거래량'].iloc[i - 1] * 3 for i in range(1, len(df))
            )
            if not 거래량_3배_이상:
                continue
            

            조건 = {
                '전략1': curr['MA5'] > curr['MA20'] and prev['MA5'] <= prev['MA20'],
                '전략2': curr['종가'] > curr['MA20'] and df['종가'].iloc[-2] < df['MA20'].iloc[-2],
                '전략3': curr['종가'] > curr['BB_lower'] and df['종가'].iloc[-2] < df['BB_lower'].iloc[-2],
                '전략4': curr['MACD'] > curr['Signal'] and prev['MACD'] <= prev['Signal'],
                '전략5': curr['RSI'] > 35 and df['RSI'].iloc[-2] <= 30,
                '전략6': curr['종가'] <= curr['BB_lower'] * 1.05,
                '전략7': curr['MA5'] > curr['MA60'] and prev['MA5'] <= prev['MA60'],
                '전략8': curr['종가'] >= 최고가52,
                
            }

            close = curr['종가']
            buy_price = df['MA5'].iloc[-1] * 0.995
            stop = int(buy_price * 0.95)
            target = int(buy_price * 1.12)
            등락률 = round(curr['하락률'], 2)

            # 현재가와 추천 매수가 차이가 크면 제외
            if abs(buy_price / close - 1) > 0.02:
                continue

            # 볼린저 상단 근처에 근접한 종목 제외
            if not pd.isna(df['BB_upper'].iloc[-1]) and close >= df['BB_upper'].iloc[-1] * 0.95:
                continue



            조건표시 = {key: '✅' if val else '' for key, val in 조건.items()}

            swing_candidates.append({
                '종목명': f"{name} ({code})",
                '시장': market_type,
                '시가총액': f"{market_cap / 1e12:.1f}조" if market_cap >= 1e12 else f"{int(market_cap / 1e8):,}억",
                '현재가': f"{int(close):,}",
                '등락률(%)': f"{등락률:+.2f}%",
                '매수가 (현재가 기준)': f"{int(buy_price):,} ({(buy_price / close - 1) * 100:+.1f}%)",
                '손절가': f"{stop:,}",
                '목표가': f"{target:,}",
                **조건표시
            })

        except:
            continue

status_text.empty()
progress.empty()

if swing_candidates:
    df_result = pd.DataFrame(swing_candidates)
    # 전략 중 하나라도 '✅'인 종목만 필터링
    전략컬럼 = ['전략1', '전략2', '전략3', '전략4', '전략5', '전략6', '전략7', '전략8' ]
    df_result = df_result[df_result[전략컬럼].apply(lambda row: '✅' in row.values, axis=1)]
    
    df_result = df_result[['종목명', '시장', '시가총액', '현재가', '등락률(%)', '매수가 (현재가 기준)', '손절가', '목표가'] + 전략컬럼]

    st.success(f"✅ 총 {len(df_result)}개 종목이 전략 조건 중 하나 이상을 만족합니다. 🗓️ 분석 기준일: {TODAY.strftime('%Y-%m-%d')}")
    st.success("🎯매수가 : 5일 평균 종가의 +0.5% ⚠️손절가 : 매수가 -5% 🏆목표가 : 매수가 +12% ")
    st.subheader("📌 스윙 전략 추천 종목")

    st.markdown("""
📌 **전략 조건**:
- 전략1: 5일선이 20일선을 돌파
- 전략2: 20일선 아래에서 회복
- 전략3: 볼린저 하단선 이탈 후 복귀
- 전략4: MACD > Signal (이전에는 반대)
- 전략5: RSI 30 이하 → 35 이상으로 반등
- 전략6: 종가가 볼린저 하단선의 5% 이내
- 전략7: 5일선이 60일선을 돌파 (중기 추세 전환 시점)
- 전략8: 52주 최고가 갱신
""")
        
    st.dataframe(df_result.reset_index(drop=True), use_container_width=True)

    # 시너지 조합 정의
    시너지_조합 = {
        "전략1 + 전략4": ['전략1', '전략4'],
        "전략2 + 전략3 + 전략5": ['전략2', '전략3', '전략5'],
        "전략6 + 전략4": ['전략6', '전략4'],
        "전략7 + 전략1": ['전략7', '전략1'],
        "전략8 + 전략1": ['전략8', '전략1']
    }

    시너지_설명 = {
        "전략1 + 전략4": "이동평균선 돌파와 MACD 골든크로스가 동시에 발생하면 상승 추세 초기일 가능성이 높습니다.",
        "전략2 + 전략3 + 전략5": "되돌림 구간에서 RSI와 볼린저 반등이 함께 나타나면 저점 반등 가능성이 큽니다.",
        "전략6 + 전략4": "과매도 구간 접근 후 MACD 반등 신호는 저점 반등의 가능성을 보여줍니다.",
        "전략7 + 전략1": "5일선이 60일선을 돌파하면서 20일선까지 돌파하면 추세 전환의 강도가 높습니다.",
        "전략8 + 전략1": "52주 신고가를 돌파한 강세 종목이 추가 돌파 흐름을 이어갈 수 있습니다."
    }

    for 조합명, 조합전략 in 시너지_조합.items():
        df_combo = df_result[df_result[조합전략].apply(lambda row: all(val == '✅' for val in row.values), axis=1)]
    
        st.subheader(f"🚀 시너지 조합: {조합명}")
        st.markdown(f"🔎 **설명**: {시너지_설명.get(조합명, '')}")

        if not df_combo.empty:
            st.dataframe(df_combo.reset_index(drop=True), use_container_width=True)            
        else:
            st.info('해당 구간에 해당하는 종목이 없습니다.')
else:
    st.warning("😥 조건에 맞는 종목이 없습니다. 다시 시도해보세요.")
