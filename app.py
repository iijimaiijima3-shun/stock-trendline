"""Streamlit stock trendline analysis app for TSE stocks."""
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from trendline import get_support_resistance_lines, score_uptrend
from screener import run_screener
from stock_names import search_by_name, get_name, TICKER_TO_NAME

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
        search_query = st.text_input(
            "銘柄コードまたは会社名で検索（例: 7203、トヨタ、ソニー）",
            value="",
            placeholder="銘柄コードか会社名を入力...",
        )
    with col_right:
        period_options = {"3ヶ月": "3mo", "6ヶ月": "6mo", "1年": "1y", "2年": "2y", "5年": "5y"}
        period_label = st.selectbox("期間", list(period_options.keys()), index=2)

    # Resolve ticker from search query
    selected_ticker = ""
    selected_name = ""

    if search_query:
        query = search_query.strip()

        # Pure numeric → add .T suffix
        if query.isdigit():
            selected_ticker = query + ".T"
            selected_name = get_name(selected_ticker)
        # Already has .T
        elif query.upper().endswith(".T"):
            selected_ticker = query.upper()
            selected_name = get_name(selected_ticker)
        else:
            # Search by name
            candidates = search_by_name(query)
            if len(candidates) == 1:
                selected_ticker, selected_name = candidates[0]
                st.info(f"検索結果: **{selected_name}** ({selected_ticker})")
            elif len(candidates) > 1:
                options = [f"{name}（{ticker}）" for ticker, name in candidates]
                choice = st.selectbox("候補から選んでください", options)
                idx = options.index(choice)
                selected_ticker, selected_name = candidates[idx]
            else:
                st.warning("該当する銘柄が見つかりませんでした。銘柄コード（例: 7203）で試してください。")

    col_w1, col_w2, col_w3 = st.columns(3)
    with col_w1:
        pivot_window = st.slider("ピボット感度（小=敏感、大=鈍感）", 3, 15, 5)
    with col_w2:
        n_lines = st.slider("トレンドライン本数", 1, 5, 3)
    with col_w3:
        show_volume = st.checkbox("出来高を表示", value=True)

    draw_disabled = not bool(selected_ticker)
    if st.button("チャートを描画", type="primary", use_container_width=True, disabled=draw_disabled):
        ticker = selected_ticker

        with st.spinner(f"{selected_name or ticker} のデータを取得中..."):
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

                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                current_price = float(df["Close"].iloc[-1])
                prev_price = float(df["Close"].iloc[-2])
                change_pct = (current_price - prev_price) / prev_price * 100

            except Exception as e:
                st.error(f"エラー: {e}")
                st.stop()

        name = selected_name or get_name(ticker)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("銘柄", name)
        m2.metric("現在値", f"¥{current_price:,.0f}")
        m3.metric("前日比", f"{change_pct:+.2f}%", delta=f"{change_pct:+.2f}%")
        metrics = score_uptrend(df)
        m4.metric("トレンドスコア", f"{metrics['score']:.1f}",
                  help="長期上昇トレンドの強さ。高いほど安定した右肩上がり")

        lines = get_support_resistance_lines(df, window=pivot_window, n_lines=n_lines)
        dates = df.index.tolist()

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=dates,
            open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
            name="ローソク足",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ))

        color_map = {"resistance": "#ef5350", "support": "#26a69a"}
        label_map = {"resistance": "抵抗線", "support": "支持線"}
        shown_labels: set = set()

        for line in lines:
            x0_date = dates[line["x0"]]
            ext_x1 = min(len(dates) - 1, line["x1"] + 20)
            ext_date = dates[ext_x1]
            ext_y1 = line["intercept"] + line["slope"] * ext_x1
            label = label_map[line["type"]]
            show_legend = label not in shown_labels
            shown_labels.add(label)

            fig.add_trace(go.Scatter(
                x=[x0_date, ext_date],
                y=[line["y0"], ext_y1],
                mode="lines",
                name=label,
                showlegend=show_legend,
                line=dict(color=color_map[line["type"]], width=2, dash="dot"),
                hovertemplate=f"{label}<br>R²={line['r2']:.2f}<br>傾き={line['slope_pct']:+.2f}%/日<extra></extra>",
            ))

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
            fig_vol = go.Figure(go.Bar(
                x=dates, y=df["Volume"],
                name="出来高", marker_color="#7986cb", opacity=0.6,
            ))
            fig_vol.update_layout(
                height=150, template="plotly_dark",
                margin=dict(t=10, b=10), xaxis_rangeslider_visible=False,
            )
            st.plotly_chart(fig, use_container_width=True)
            st.plotly_chart(fig_vol, use_container_width=True)
        else:
            st.plotly_chart(fig, use_container_width=True)

        if lines:
            st.subheader("検出されたトレンドライン")
            tl_rows = [
                {
                    "種別": label_map[l["type"]],
                    "R²（信頼度）": f"{l['r2']:.3f}",
                    "傾き（%/日）": f"{l['slope_pct']:+.3f}",
                    "タッチ点数": l["pivot_count"],
                }
                for l in lines
            ]
            st.dataframe(pd.DataFrame(tl_rows), use_container_width=True, hide_index=True)

        with st.expander("トレンドスコア詳細"):
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("年換算上昇率", f"{metrics['slope_pct']:+.1f}%")
            sc2.metric("R²（当てはまり）", f"{metrics['r2']:.3f}")
            sc3.metric("一貫性", f"{metrics['consistency']*100:.1f}%")
            st.caption("スコア = 年換算上昇率 × R² × 一貫性。長期で安定して右肩上がりの銘柄ほど高くなります。")


# ── Tab 2: Screener ───────────────────────────────────────────────────────────
with tab2:
    st.markdown("### 銘柄スクリーナー")

    sc_col1, sc_col2, sc_col3 = st.columns(3)
    with sc_col1:
        sc_period_map = {"1年": "1y", "2年": "2y", "3年": "3y"}
        sc_period_label = st.selectbox("分析期間", list(sc_period_map.keys()), index=1, key="sc_period")
    with sc_col2:
        top_n = st.slider("表示件数", 5, 30, 15, key="sc_top")
    with sc_col3:
        screen_mode = st.radio(
            "表示モード",
            ["📈 長期上昇トレンド上位", "🎯 サポートライン接近銘柄"],
            horizontal=True,
        )

    # Support proximity threshold (shown only in support mode)
    support_threshold = 5.0
    if "サポートライン" in screen_mode:
        support_threshold = st.slider(
            "サポートラインからの距離（%以内）",
            min_value=1, max_value=20, value=5,
            help="現在値がサポートラインから何%以内の銘柄を表示するか",
        )

    if st.button("スクリーニング実行", type="primary", use_container_width=True):
        with st.spinner("銘柄をスキャン中（1〜2分かかります）..."):
            result_df = run_screener(period=sc_period_map[sc_period_label])

        if result_df.empty:
            st.warning("結果が見つかりませんでした。")
            st.stop()

        if "サポートライン" in screen_mode:
            # Filter: price within threshold% above support
            filtered = result_df[
                (result_df["support_dist"] >= 0) &
                (result_df["support_dist"] <= support_threshold) &
                (result_df["score"] > 0)
            ].copy()
            filtered = filtered.sort_values("support_dist").reset_index(drop=True)
            filtered.index += 1
            display_df = filtered.head(top_n)

            st.subheader(f"🎯 サポートライン接近銘柄（{support_threshold}%以内）上位 {len(display_df)} 件")
            st.caption("長期上昇トレンド中かつ現在値がサポートラインに近い＝買い場の候補です。")

            if display_df.empty:
                st.info(f"サポートラインから{support_threshold}%以内の銘柄は現在見つかりませんでした。閾値を広げてみてください。")
            else:
                fig_bar = go.Figure(go.Bar(
                    x=display_df["support_dist"],
                    y=display_df["name"],
                    orientation="h",
                    marker_color="#ffa726",
                    text=[f"{v:.1f}%" for v in display_df["support_dist"]],
                    textposition="outside",
                ))
                fig_bar.update_layout(
                    height=max(300, len(display_df) * 30),
                    template="plotly_dark",
                    xaxis_title="サポートラインからの距離（%）",
                    yaxis=dict(autorange="reversed"),
                    margin=dict(l=200),
                )
                st.plotly_chart(fig_bar, use_container_width=True)

                show_cols = display_df[["ticker", "name", "current_price", "support_dist", "slope_pct", "score"]].copy()
                show_cols.columns = ["コード", "銘柄名", "現在値(円)", "サポートまで(%)", "年換算上昇率(%)", "スコア"]
                st.dataframe(show_cols, use_container_width=True)

        else:
            display_df = result_df.sort_values("score", ascending=False).head(top_n)

            st.subheader(f"📈 トレンドスコア上位 {len(display_df)} 銘柄")

            fig_bar = go.Figure(go.Bar(
                x=display_df["score"],
                y=display_df["name"],
                orientation="h",
                marker_color="#26a69a",
                text=display_df["score"].round(1).astype(str),
                textposition="outside",
            ))
            fig_bar.update_layout(
                height=max(300, len(display_df) * 30),
                template="plotly_dark",
                xaxis_title="トレンドスコア",
                yaxis=dict(autorange="reversed"),
                margin=dict(l=200),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            show_cols = display_df[["ticker", "name", "current_price", "slope_pct", "r2", "consistency", "score"]].copy()
            show_cols.columns = ["コード", "銘柄名", "現在値(円)", "年換算上昇率(%)", "R²", "一貫性(%)", "スコア"]
            st.dataframe(show_cols, use_container_width=True)

            st.caption("スコア = 年換算上昇率(%) × R²（安定性） × 一貫性（上昇日割合）")

        st.info("気になる銘柄は「銘柄分析」タブでコードか会社名を入力するとトレンドラインが確認できます。")
