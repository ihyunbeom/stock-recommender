import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from pykrx import stock

st.set_page_config(page_title="단타 전략 종목 추천기", layout="wide")
st.title("📈 단타 전략 종목 추천기 - 돌파 & 눌림목 전략")

# 날짜 설정
today = datetime.today()
start_date = today - timedelta(days=60)
start_str = start_date.strftime('%Y%m%d')
end_str = today.strftime('%Y%m%d')

# 시가총액 상위 300개 종목
@st.cache_data
def get_stock_list():
    today_str = datetime.today().strftime('%Y%m%d')
    cap_df = stock.get_market_cap_by_ticker(today_str)
    cap_df = cap_df.reset_index()
    cap_df['Name'] = cap_df['티커'].apply(stock.get_market_ticker_name)
    cap_df = cap_df.rename(columns={'티커': 'Code', '시가총액': 'MarketCap'})
    cap_df = cap_df.sort_values(by='MarketCap', ascending=False)
    return cap_df[['Code', 'Name']].head(500)

stock_list = get_stock_list()
breakout_list, pullback_list = [], []

status_text = st.empty()
progress = st.progress(0)
log_box = st.empty()
log_messages = []
total = len(stock_list)

# 최소 거래대금 10억 이상
min_amount = 10_000_000_000

with st.spinner("종목 분석 중..."):
    for i, row in enumerate(stock_list.itertuples(index=False)):
        code, name = row.Code, row.Name

        status_text.text(f"종목 분석 중... ⏳ ({name})")
        progress.progress((i + 1) / total)

        try:
            df = stock.get_market_ohlcv_by_date(start_str, end_str, code)
            if df is None or df.empty:
                log_messages.append(f"⛔ 데이터 없음: {name}")
                continue
            
            # 거래량 또는 거래대금이 0인 날이 많다면 거래 정지 가능성 있음
            if df['거래량'][-3:].sum() == 0:
                continue

            df = df.dropna()
            if len(df) < 25:
                log_messages.append(f"⛔ 데이터 부족 (<25일): {name}")
                continue

            df['MA20'] = df['종가'].rolling(window=20).mean()
            df = df.dropna()
            if len(df) < 3:
                log_messages.append(f"⛔ MA20 이후 usable 데이터 부족: {name}")
                continue

            # ✅ 거래대금 계산 추가
            df['거래대금'] = df['종가'] * df['거래량']

            # ✅ 거래 정지 필터 (10억 미만 제거)
            if df.iloc[-1]['거래대금'] < 10_000_000_000:
                continue

            curr = df.iloc[-1]
            prev = df.iloc[-2]
            high3 = df.iloc[-4]['고가']
            vol_avg = df['거래량'].iloc[-6:-1].mean()

            # 돌파 전략
            cond1 = prev['종가'] >= prev['고가'] * 0.9
            cond2 = prev['거래량'] >= vol_avg * 1.4
            cond3 = prev['종가'] > prev['시가']
            if cond1 and cond2 and cond3:
                breakout_list.append({
                    '종목명': name,
                    '전략': '돌파',
                    '현재가': curr['종가'],
                    '매수가': round(prev['고가'] * 1.005, 2),
                    '손절가': round(prev['종가'] * 0.97, 2),
                    '목표가': round(prev['고가'] * 1.05, 2),
                    '기준일': df.index[-2].strftime('%Y-%m-%d')
                })

            # 눌림목 전략
            cond4 = high3 * 0.9 <= curr['종가'] <= high3 * 0.95
            cond5 = abs(curr['종가'] - curr['MA20']) / curr['MA20'] < 0.02
            cond6 = curr['거래량'] < vol_avg
            if cond4 and cond5 and cond6:
                pullback_list.append({
                    '종목명': name,
                    '전략': '눌림목',
                    '현재가': curr['종가'],
                    '매수가': round(curr['종가'] * 1.005, 2),
                    '손절가': round(curr['MA20'] * 0.98, 2),
                    '목표가': round(high3, 2),
                    '기준일': df.index[-1].strftime('%Y-%m-%d')
                })

            log_box.text("\n".join(log_messages[-8:]))

        except Exception as e:
            log_messages.append(f"❗ 오류 발생: {name} - {e}")
            log_box.text("\n".join(log_messages[-8:]))
            continue

# 분석 종료 후 UI 정리
log_box.empty()
status_text.empty()
progress.empty()

# 결과 출력
if breakout_list or pullback_list:
    st.success(f"✅ 총 {len(breakout_list) + len(pullback_list)}개 종목이 전략 조건을 통과했습니다.")
    if breakout_list:
        st.subheader("📌 돌파 전략 추천 종목")
        st.caption("전일 고가 부근에서 강하게 마감하고 거래량이 증가한 종목을 다음 날 돌파 매수하는 전략입니다.")
        st.dataframe(pd.DataFrame(breakout_list))
    if pullback_list:
        st.subheader("📌 눌림목 전략 추천 종목")
        st.caption("최근 고점 대비 5~10% 조정을 받았고 20일선 부근에서 지지 후 반등 가능성이 있는 종목을 포착합니다.")
        st.dataframe(pd.DataFrame(pullback_list))
else:
    st.warning("😥 조건에 맞는 종목이 없습니다. 다시 시도해보세요.")
