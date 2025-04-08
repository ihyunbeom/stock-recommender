import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from pykrx import stock

st.set_page_config(page_title="단타 전략 종목 추천기", layout="wide")
st.title("📈 단타 전략 종목 추천기 - 돌파 & 눌림목 전략")

# 날짜 설정
today = datetime.today()
start_date = today - timedelta(days=180)  # 6개월
start_str = start_date.strftime('%Y%m%d')
end_str = today.strftime('%Y%m%d')

# 필터 기준
MIN_MARKET_CAP = 300_000_000_000  # 3000억
MIN_AMOUNT = 10_000_000_000       # 거래대금 10억

# 시가총액 3000억 이상 종목만 추출
@st.cache_data
def get_filtered_stock_list():
    today_str = datetime.today().strftime('%Y%m%d')
    cap_df = stock.get_market_cap_by_ticker(today_str)
    cap_df = cap_df.reset_index()
    cap_df['Name'] = cap_df['티커'].apply(stock.get_market_ticker_name)
    cap_df = cap_df.rename(columns={'티커': 'Code', '시가총액': 'MarketCap'})
    cap_df = cap_df[cap_df['MarketCap'] >= MIN_MARKET_CAP]
    return cap_df[['Code', 'Name', 'MarketCap']].reset_index(drop=True)

stock_list = get_filtered_stock_list()
breakout_list, pullback_list = [], []

status_text = st.empty()
progress = st.progress(0)
log_box = st.empty()
log_messages = []
total = len(stock_list)

with st.spinner("종목 분석 중..."):
    for i, row in enumerate(stock_list.itertuples(index=False)):
        code, name, market_cap = row.Code, row.Name, row.MarketCap

        status_text.text(f"종목 분석 중... ⏳ ({name})")
        progress.progress((i + 1) / total)

        try:
            df = stock.get_market_ohlcv_by_date(start_str, end_str, code)
            if df is None or df.empty:
                log_messages.append(f"⛔ 데이터 없음: {name}")
                continue

            df = df.dropna()
            if len(df) < 25:
                log_messages.append(f"⛔ 데이터 부족 (<25일): {name}")
                continue

            df['거래대금'] = df['종가'] * df['거래량']
            if df.iloc[-1]['거래대금'] < MIN_AMOUNT:
                log_messages.append(f"⛔ 거래대금 부족 (10억 미만): {name}")
                continue

            df['MA20'] = df['종가'].rolling(window=20).mean()
            df = df.dropna()
            if len(df) < 3:
                log_messages.append(f"⛔ MA20 이후 usable 데이터 부족: {name}")
                continue

            # ✅ 거래량 급등 이력 확인
            volume_spike = (df['거래량'] > df['거래량'].shift(1) * 3).any()
            volume_spike_flag = "✅ 예" if volume_spike else "❌ 아니오"

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
                    '시가총액': f"{int(market_cap / 1e8):,}억",
                    '거래량 급등 이력': volume_spike_flag,
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
                    '시가총액': f"{int(market_cap / 1e8):,}억",
                    '거래량 급등 이력': volume_spike_flag,
                    '기준일': df.index[-1].strftime('%Y-%m-%d')
                })

            log_box.text("\n".join(log_messages[-8:]))

        except Exception as e:
            log_messages.append(f"❗ 오류 발생: {name} - {e}")
            log_box.text("\n".join(log_messages[-8:]))
            continue

# UI 정리
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
