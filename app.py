"""Streamlit stock trendline analysis app for TSE stocks."""
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

from trendline import get_support_resistance_lines, score_uptrend
from screener import run_screener

st.set_page_config(
    page_title="株価トレンドライン分析",
    page_icon="📈",
    layout="wide",
)

st.title("📈 株価トレンドライン分析")

tab1, tab2 = st.tabs(["🔍 銘柄分析", "⭐ 銘柄おすすめ"])


# ── Tab 1: Individual stock analysis ──────────────────────────────────────────
with tab1:
    col_left, col_right = st.columns([3, 1])

    with col_left:
        ticker_input = st.text_input(
            "銘柄コードを入力（例: 7203 → トヨタ、AAPL → Apple）",
            value="7203",
            placeholder="銘柄コード",
        )
    with col_right:
        period_options = {"3ヶ月": "3mo", "6ヶ月": "6mo", "1年": "1y", "2年": "2y", "5年": "5y"}
        period_label = st.selectbox("期間", list(period_options.keys()), index=2)

    col_w1, col_w2, col_w3 = st.columns(3)
    with col_w1:
        pivot_window = st.slider("ピボット感度（小=敏感、大=鈍感）", 3, 15, 5)
    with col_w2:
        n_lines = st.slider("トレンドライン本数", 1, 5, 3)
    with col_w3:
        show_volume = st.checkbox("出来高を表示", value=True)

    if st.button("チャートを描画", type="primary", use_container_width=True):
        ticker = ticker_input.strip()
        if ticker.isdigit():
            ticker = ticker + ".T"

        with st.spinner(f"{ticker} のデータを取得中..."):
            try:
                df = yf.download(
                    ticker,
                    period=period_options[period_label],
                    auto_adjust=True,
                    progress=False,
                )
                if df.empty:
                    st.error("データを取得できませんでした。銘柄コードを確認してください。")
                    st.stop()

                # Flatten MultiIndex columns if present
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                info = {}
                try:
                    info = yf.Ticker(ticker).info
                except Exception:
                    pass

                name = info.get("longName") or info.get("shortName") or ticker
                current_price = float(df["Close"].iloc[-1])
                prev_price = float(df["Close"].iloc[-2])
                change_pct = (current_price - prev_price) / prev_price * 100

            except Exception as e:
                st.error(f"エラー: {e}")
                st.stop()

        # Metrics row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("銘柄", name)
        m2.metric("現在値", f"¥{current_price:,.0f}" if ".T" in ticker else f"${current_price:,.2f}")
        m3.metric("前日比", f"{change_pct:+.2f}%", delta=f"{change_pct:+.2f}%")

        metrics = score_uptrend(df)
        m4.metric(
            "トレンドスコア",
            f"{metrics['score']:.1f}",
            help="長期上昇トレンドの強さ。スコアが高いほど安定した右肩上がり",
        )

        # Trendlines
        lines = get_support_resistance_lines(df, window=pivot_window, n_lines=n_lines)
        dates = df.index.tolist()

        # Build chart
        fig = go.Figure()

        # Candlestick
        fig.add_trace(
            go.Candlestick(
                x=dates,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name="ローソク足",
                increasing_line_color="#26a69a",
                decreasing_line_color="#ef5350",
            )
        )

        # Draw trendlines
        color_map = {"resistance": "#ef5350", "support": "#26a69a"}
        label_map = {"resistance": "抵抗線", "support": "支持線"}
        shown_labels: set = set()

        for line in lines:
            x0_date = dates[line["x0"]]
            x1_date = dates[line["x1"]]
            label = label_map[line["type"]]
            show_legend = label not in shown_labels
            shown_labels.add(label)

            # Extend line to chart edges
            # Extrapolate to the last date
            ext_x1 = min(len(dates) - 1, line["x1"] + 20)
            ext_date = dates[ext_x1]
            ext_y1 = line["intercept"] + line["slope"] * ext_x1

            fig.add_trace(
                go.Scatter(
                    x=[x0_date, ext_date],
                    y=[line["y0"], ext_y1],
                    mode="lines",
                    name=label,
                    showlegend=show_legend,
                    line=dict(color=color_map[line["type"]], width=2, dash="dot"),
                    hovertemplate=f"{label}<br>R²={line['r2']:.2f}<br>傾き={line['slope_pct']:+.2f}%/日<extra></extra>",
                )
            )

        fig.update_layout(
            title=f"{name} ({ticker})",
            xaxis_title="日付",
            yaxis_title="株価",
            xaxis_rangeslider_visible=False,
            height=550,
            template="plotly_dark",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        )

        if show_volume and "Volume" in df.columns:
            fig_vol = go.Figure(
                go.Bar(
                    x=dates,
                    y=df["Volume"],
                    name="出来高",
                    marker_color="#7986cb",
                    opacity=0.6,
                )
            )
            fig_vol.update_layout(
                height=150,
                template="plotly_dark",
                margin=dict(t=10, b=10),
                xaxis_rangeslider_visible=False,
            )
            st.plotly_chart(fig, use_container_width=True)
            st.plotly_chart(fig_vol, use_container_width=True)
        else:
            st.plotly_chart(fig, use_container_width=True)

        # Trendline detail table
        if lines:
            st.subheader("検出されたトレンドライン")
            tl_rows = []
            for line in lines:
                tl_rows.append(
                    {
                        "種別": label_map[line["type"]],
                        "R²（信頼度）": f"{line['r2']:.3f}",
                        "傾き（%/日）": f"{line['slope_pct']:+.3f}",
                        "タッチ点数": line["pivot_count"],
                    }
                )
            st.dataframe(pd.DataFrame(tl_rows), use_container_width=True, hide_index=True)

        # Uptrend detail
        with st.expander("トレンドスコア詳細"):
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("年換算上昇率", f"{metrics['slope_pct']:+.1f}%")
            sc2.metric("R²（当てはまり）", f"{metrics['r2']:.3f}")
            sc3.metric("一貫性", f"{metrics['consistency']*100:.1f}%")
            st.caption(
                "スコア = 年換算上昇率 × R² × 一貫性。長期で安定して右肩上がりの銘柄ほど高くなります。"
            )


# ── Tab 2: Screener ───────────────────────────────────────────────────────────
with tab2:
    st.markdown("### 長期右肩上がり銘柄スクリーナー")
    st.caption("東証プライム主要銘柄をスキャンして、トレンドスコアが高い順にランキングします。")

    sc_col1, sc_col2 = st.columns(2)
    with sc_col1:
        sc_period_label = st.selectbox(
            "分析期間", ["1年", "2年", "3年"], index=1, key="sc_period"
        )
        sc_period_map = {"1年": "1y", "2年": "2y", "3年": "3y"}
    with sc_col2:
        top_n = st.slider("表示件数", 5, 30, 15, key="sc_top")

    if st.button("スクリーニング実行", type="primary", use_container_width=True):
        with st.spinner("銘柄をスキャン中（1〜2分かかります）..."):
            result_df = run_screener(period=sc_period_map[sc_period_label])

        if result_df.empty:
            st.warning("結果が見つかりませんでした。")
        else:
            display_df = result_df.head(top_n).copy()

            st.subheader(f"トレンドスコア上位 {min(top_n, len(display_df))} 銘柄")

            # Bar chart of scores
            fig_bar = go.Figure(
                go.Bar(
                    x=display_df["score"],
                    y=display_df["name"].str[:20],
                    orientation="h",
                    marker_color="#26a69a",
                    text=display_df["score"].astype(str),
                    textposition="outside",
                )
            )
            fig_bar.update_layout(
                height=max(300, top_n * 28),
                template="plotly_dark",
                xaxis_title="トレンドスコア",
                yaxis=dict(autorange="reversed"),
                margin=dict(l=200),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            # Table
            styled = display_df[["ticker", "name", "current_price", "slope_pct", "r2", "consistency", "score"]].copy()
            styled.columns = ["コード", "銘柄名", "現在値(円)", "年換算上昇率(%)", "R²", "一貫性(%)", "スコア"]
            st.dataframe(styled, use_container_width=True)

            st.caption(
                "スコア = 年換算上昇率(%) × R²（トレンドの安定性） × 一貫性（上昇日の割合）\n"
                "スコアが高いほど長期で安定した右肩上がりの銘柄です。"
            )

            # Quick link: click ticker to pre-fill tab1
            st.info("気になる銘柄は「銘柄分析」タブでコードを入力するとトレンドラインが確認できます。")
