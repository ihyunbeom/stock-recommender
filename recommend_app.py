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
# TODAY = datetime.today()
# START_DATE = TODAY - timedelta(days=180)
# start_str = START_DATE.strftime('%Y%m%d')
# end_str = TODAY.strftime('%Y%m%d')
# 날짜 선택 위젯

# 상태 초기화 (최초 실행 시)
if '분석중' not in st.session_state:
    st.session_state['분석중'] = False

# 날짜 선택 (분석 중에는 비활성화)
TODAY = st.date_input("📅 분석 기준일 선택", datetime.today(), disabled=st.session_state['분석중'])

START_DATE = TODAY - timedelta(days=180)
start_str = START_DATE.strftime('%Y%m%d')
end_str = TODAY.strftime('%Y%m%d')

# 분석 시작 버튼
if st.button("🔍 분석 시작", disabled=st.session_state['분석중']):
    st.session_state['분석중'] = True  # 분석 시작 시 잠금
    
    st.success(f"{TODAY.strftime('%Y-%m-%d')} 기준으로 분석을 시작합니다.")

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
    
    with st.spinner("📊 종목 리스트 불러오는 중..."):
        stock_list = get_filtered_stock_list()
        market_kospi = stock.get_market_ticker_list(market='KOSPI')
        market_kosdaq = stock.get_market_ticker_list(market='KOSDAQ')
        swing_candidates = []
        status_text = st.empty()
        progress = st.progress(0)
        total = len(stock_list)
        log_box = st.empty()
        log_messages = []

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
                    log_messages.append(f"⛔ 데이터 없음: {name}")
                    continue

                df['거래대금'] = df['종가'] * df['거래량']
                if df.iloc[-1]['거래대금'] < MIN_AMOUNT:
                    log_messages.append(f"⛔ 거래대금 부족 ({int(MIN_AMOUNT / 1e8)}억 미만): {name}")
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
                df['CCI'] = ta.trend.cci(df['고가'], df['저가'], df['종가'], window=20)
                df['OBV'] = ta.volume.OnBalanceVolumeIndicator(df['종가'], df['거래량']).on_balance_volume()



                df = df.dropna()
                curr = df.iloc[-1]
                prev = df.iloc[-2]
                최고가52 = df['종가'].rolling(window=260).max().iloc[-1]

                # 거래량 3배 이상 상승 여부
                거래량_3배_이상 = any(
                    df['거래량'].iloc[i] >= df['거래량'].iloc[i - 1] * 3 for i in range(1, len(df))
                )
                if not 거래량_3배_이상:
                    log_messages.append(f"⛔ 거래량 급등 이력 없음: {name}")
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
                    '전략9': (
                            curr['거래량'] > df['거래량'].rolling(20).mean().iloc[-1] * 2 and
                            curr['거래량'] > df['거래량'].rolling(60).mean().iloc[-1]
                            ),
                    '전략10': curr['종가'] < curr['MA5'] * 0.9,
                    '전략11': curr['종가'] > prev['고가'] and curr['종가'] > curr['시가'] and prev['종가'] < prev['시가'],
                    '전략12': df['종가'].iloc[-2] < df['MA60'].iloc[-2] and curr['종가'] > curr['MA60'],
                    '전략13': curr['CCI'] > -100 and df['CCI'].iloc[-2] <= -100,
                    '전략14': curr['OBV'] > df['OBV'].iloc[-2]
                    
                }
                close = curr['종가']
                buy_price = df['MA5'].iloc[-1] * 0.995
                stop = int(buy_price * 0.95)
                target = int(buy_price * 1.12)
                등락률 = round(curr['하락률'], 2)

                # 현재가와 추천 매수가 차이가 크면 제외
                if abs(buy_price / close - 1) > 0.02:
                    log_messages.append(f"⛔ 현재가와 추천 매수가 차이가 2% 이상: {name}")
                    continue

                # 볼린저 상단 근처에 근접한 종목 제외
                if not pd.isna(df['BB_upper'].iloc[-1]) and close >= df['BB_upper'].iloc[-1] * 0.95:
                    log_messages.append(f"⛔ 볼린저 상단 근처: {name}")
                    continue

                
                # 매물대 위치 계산 (최근 30일 기준)
                recent_prices = df['종가'].tail(30)
                recent_volumes = df['거래량'].tail(30)
                price_bins = pd.cut(recent_prices, bins=10)
                volume_by_price = recent_volumes.groupby(price_bins, observed=False).sum()
                peak_bin = volume_by_price.idxmax()

                매물대_상단 = peak_bin.right
                매물대_하단 = peak_bin.left

                # 매물대 위치 판단
                if close >= 매물대_상단 * 1.05:
                    매물대_위치 = "상단 돌파 🚀"
                elif close >= 매물대_상단:
                    매물대_위치 = "상단 근접 🔼"
                elif close >= 매물대_하단:
                    매물대_위치 = "매물대 내부 ⚖️"
                else:
                    매물대_위치 = "하단 이하 ⚠️"


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
                    '매물대 위치': 매물대_위치,
                    **조건표시
                })
                
                log_box.text("\n".join(log_messages[-8:]))

            except Exception as e:
                log_messages.append(f"❗ 오류 발생: {name} - {e}")
                log_box.text("\n".join(log_messages[-8:]))
                continue

    # UI 종료 후 결과 출력
    log_box.empty()
    status_text.empty()
    progress.empty()

    if swing_candidates:
        df_result = pd.DataFrame(swing_candidates)
        # 전략 중 하나라도 '✅'인 종목만 필터링
        전략컬럼 = ['전략1', '전략2', '전략3', '전략4', '전략5', '전략6', '전략7', '전략8', '전략9', '전략10', '전략11', '전략12', '전략13', '전략14' ]
        df_result = df_result[df_result[전략컬럼].apply(lambda row: '✅' in row.values, axis=1)]
        
        # 전략 개수 계산 후 정렬
        df_result["전략 개수"] = df_result[전략컬럼].apply(lambda row: sum(val == '✅' for val in row), axis=1)
        df_result = df_result.sort_values(by="전략 개수", ascending=False)

        # 컬럼 순서 재조정 (전략 개수를 전략들보다 앞으로)
        df_result = df_result[['종목명', '시장', '시가총액', '현재가', '등락률(%)', '매수가 (현재가 기준)', '손절가', '목표가', '매물대 위치', '전략 개수'] + 전략컬럼]

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
        - 전략9: 20일 평균의 2배 이상이며 60일 평균도 초과한 거래량 급증 신호
        - 전략10: 종가가 5일선보다 10% 이상 낮음 (과매도 구간)
        - 전략11: 상승 장악형 캔들 출현 (전일 음봉 → 당일 양봉 & 돌파)
        - 전략12: 전일 종가가 60일선 아래, 당일 종가가 다시 회복
        - 전략13: CCI -100 이하에서 -100 이상으로 반등
        - 전략14: OBV가 전일 대비 상승 (수급 유입 신호)
        """)

            
        st.dataframe(df_result.reset_index(drop=True), use_container_width=True)

        # 시너지 조합 정의
        시너지_조합 = {
            "전략1 + 전략4": ['전략1', '전략4'],
            "전략3 + 전략5 + 전략13": ['전략3', '전략5', '전략13'],
            "전략6 + 전략4": ['전략6', '전략4'],
            "전략7 + 전략1 + 전략12": ['전략7', '전략1', '전략12'],
            "전략8 + 전략9": ['전략8', '전략9'],
            "전략4 + 전략9 + 전략14": ['전략4', '전략9', '전략14'],
            "전략2 + 전략10": ['전략2', '전략10']
        }

        시너지_설명 = {
            "전략1 + 전략4": "이동평균선 돌파와 MACD 골든크로스가 동시에 발생하면 상승 추세 초기일 가능성이 높습니다.",
            "전략3 + 전략5 + 전략13": "볼린저 하단 반등, RSI 반등, CCI 반등이 동시에 발생하면 저점 반등의 강력한 신호로 해석됩니다.",
            "전략6 + 전략4": "과매도 구간 접근 후 MACD 반등 신호는 저점 반등의 가능성을 보여줍니다.",
            "전략7 + 전략1 + 전략12": "단기(5일) 및 중기(20일, 60일) 추세 전환이 동시에 나타나는 강한 상승 시그널입니다.",
            "전략8 + 전략9": "52주 신고가를 돌파하고 거래량이 폭증한 종목은 강세장의 대표주로 떠오를 가능성이 높습니다.",
            "전략4 + 전략9 + 전략14": "MACD 골든크로스와 20·60일 평균을 초과한 거래량, OBV 상승이 동시에 나타나면 강력한 수급 기반의 추세 전환 신호로 해석됩니다.",
            "전략2 + 전략10": "20일선 아래 눌림목에서 이격도 과매도까지 겹치면 단기 반등을 노릴 수 있는 기회입니다."
        }

        # 시너지 조합 분석 및 표시
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

    st.session_state['분석중'] = False  # 분석 완료되면 다시 활성화
