"""Streamlit stock trendline analysis app for TSE stocks."""
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

from trendline import get_support_resistance_lines, score_uptrend
from screener import run_screener
from stock_names import search_by_name, get_name

st.set_page_config(
    page_title="株価トレンドライン分析",
    page_icon="📈",
    layout="wide",
)

st.title("📈 株価トレンドライン分析")


# ── Shared chart builder ───────────────────────────────────────────────────────
def build_chart(df: pd.DataFrame, ticker: str, name: str, pivot_window: int, n_lines: int, highlight_support: bool = False) -> go.Figure:
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

        # サポートライン接近モードでは支持線を太く強調
        width = 3 if (highlight_support and line["type"] == "support") else 2
        dash = "solid" if (highlight_support and line["type"] == "support") else "dot"

        fig.add_trace(go.Scatter(
            x=[x0_date, ext_date],
            y=[line["y0"], ext_y1],
            mode="lines",
            name=label,
            showlegend=show_legend,
            line=dict(color=color_map[line["type"]], width=width, dash=dash),
            hovertemplate=f"{label}<br>R²={line['r2']:.2f}<br>傾き={line['slope_pct']:+.3f}%/日<extra></extra>",
        ))

    fig.update_layout(
        title=f"{name} ({ticker})",
        xaxis_title="日付",
        yaxis_title="株価",
        xaxis_rangeslider_visible=False,
        height=400,
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(t=60, b=40),
    )
    return fig


def fetch_df(ticker: str, period: str) -> pd.DataFrame | None:
    try:
        df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return None


# ── Tab layout ─────────────────────────────────────────────────────────────────
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

    selected_ticker = ""
    selected_name = ""

    if search_query:
        query = search_query.strip()
        if query.isdigit():
            selected_ticker = query + ".T"
            selected_name = get_name(selected_ticker)
        elif query.upper().endswith(".T"):
            selected_ticker = query.upper()
            selected_name = get_name(selected_ticker)
        else:
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

    if st.button("チャートを描画", type="primary", use_container_width=True, disabled=not selected_ticker):
        with st.spinner(f"{selected_name or selected_ticker} のデータを取得中..."):
            df = fetch_df(selected_ticker, period_options[period_label])

        if df is None:
            st.error("データを取得できませんでした。")
            st.stop()

        name = selected_name or get_name(selected_ticker)
        current_price = float(df["Close"].iloc[-1])
        prev_price = float(df["Close"].iloc[-2])
        change_pct = (current_price - prev_price) / prev_price * 100
        metrics = score_uptrend(df)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("銘柄", name)
        m2.metric("現在値", f"¥{current_price:,.0f}")
        m3.metric("前日比", f"{change_pct:+.2f}%", delta=f"{change_pct:+.2f}%")
        m4.metric("トレンドスコア", f"{metrics['score']:.1f}",
                  help="長期上昇トレンドの強さ。高いほど安定した右肩上がり")

        fig = build_chart(df, selected_ticker, name, pivot_window, n_lines)

        if show_volume and "Volume" in df.columns:
            dates = df.index.tolist()
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

        with st.expander("トレンドスコア詳細"):
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("年換算上昇率", f"{metrics['slope_pct']:+.1f}%")
            sc2.metric("R²（当てはまり）", f"{metrics['r2']:.3f}")
            sc3.metric("一貫性", f"{metrics['consistency']*100:.1f}%")


# ── Tab 2: Screener ───────────────────────────────────────────────────────────
with tab2:
    st.markdown("### 銘柄スクリーナー")

    sc_col1, sc_col2, sc_col3 = st.columns(3)
    with sc_col1:
        sc_period_map = {"1年": "1y", "2年": "2y", "3年": "3y"}
        sc_period_label = st.selectbox("分析期間", list(sc_period_map.keys()), index=1, key="sc_period")
    with sc_col2:
        top_n = st.slider("表示件数", 5, 20, 10, key="sc_top")
    with sc_col3:
        screen_mode = st.radio(
            "表示モード",
            ["📈 長期上昇トレンド上位", "🎯 サポートライン接近銘柄"],
            horizontal=True,
        )

    support_threshold = 5.0
    chart_period = "1y"
    if "サポートライン" in screen_mode:
        sp_col1, sp_col2 = st.columns(2)
        with sp_col1:
            support_threshold = st.slider(
                "サポートラインからの距離（%以内）", 1, 20, 5,
                help="現在値がサポートラインから何%以内の銘柄を表示するか",
            )
        with sp_col2:
            chart_period_label = st.selectbox("チャート表示期間", ["6ヶ月", "1年", "2年"], index=1)
            chart_period = {"6ヶ月": "6mo", "1年": "1y", "2年": "2y"}[chart_period_label]

    if st.button("スクリーニング実行", type="primary", use_container_width=True):
        with st.spinner("銘柄をスキャン中（1〜2分かかります）..."):
            st.session_state["screener_result"] = run_screener(period=sc_period_map[sc_period_label])
            st.session_state["screener_mode"] = screen_mode
            st.session_state["screener_threshold"] = support_threshold
            st.session_state["screener_chart_period"] = chart_period
            st.session_state["screener_top_n"] = top_n

    # ── Display results (persisted in session_state) ──
    if "screener_result" in st.session_state:
        result_df = st.session_state["screener_result"]
        mode = st.session_state.get("screener_mode", screen_mode)
        threshold = st.session_state.get("screener_threshold", support_threshold)
        c_period = st.session_state.get("screener_chart_period", chart_period)
        c_top_n = st.session_state.get("screener_top_n", top_n)

        if result_df.empty:
            st.warning("結果が見つかりませんでした。")
            st.stop()

        if "サポートライン" in mode:
            filtered = result_df[
                (result_df["support_dist"] >= 0) &
                (result_df["support_dist"] <= threshold) &
                (result_df["score"] > 0)
            ].sort_values("support_dist").head(c_top_n)

            st.subheader(f"🎯 サポートライン接近銘柄（{threshold}%以内）— {len(filtered)} 件")
            st.caption("長期上昇トレンド中かつ現在値がサポートラインに近い＝買い場の候補です。支持線は実線で強調表示しています。")

            if filtered.empty:
                st.info(f"サポートラインから{threshold}%以内の銘柄は現在見つかりませんでした。閾値を広げてみてください。")
            else:
                # Summary table
                show_cols = filtered[["ticker", "name", "current_price", "support_dist", "slope_pct", "score"]].copy()
                show_cols.columns = ["コード", "銘柄名", "現在値(円)", "サポートまで(%)", "年換算上昇率(%)", "スコア"]
                st.dataframe(show_cols, use_container_width=True, hide_index=True)

                st.markdown("---")
                st.markdown("#### 各銘柄のチャート（支持線：緑の実線）")

                # Render a chart per stock
                for _, row in filtered.iterrows():
                    ticker = row["ticker"]
                    name = row["name"]
                    dist = row["support_dist"]

                    with st.expander(f"📊 {name}（{ticker}）― サポートまで {dist:.1f}%", expanded=True):
                        with st.spinner(f"{name} のチャートを描画中..."):
                            df = fetch_df(ticker, c_period)

                        if df is None:
                            st.warning("データを取得できませんでした。")
                            continue

                        current_price = float(df["Close"].iloc[-1])
                        prev_price = float(df["Close"].iloc[-2])
                        change_pct = (current_price - prev_price) / prev_price * 100

                        mc1, mc2, mc3 = st.columns(3)
                        mc1.metric("現在値", f"¥{current_price:,.0f}")
                        mc2.metric("前日比", f"{change_pct:+.2f}%", delta=f"{change_pct:+.2f}%")
                        mc3.metric("年換算上昇率", f"{row['slope_pct']:+.1f}%")

                        fig = build_chart(df, ticker, name, pivot_window=5, n_lines=3, highlight_support=True)
                        st.plotly_chart(fig, use_container_width=True)

        else:
            display_df = result_df.sort_values("score", ascending=False).head(c_top_n)
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
            st.dataframe(show_cols, use_container_width=True, hide_index=True)
            st.caption("スコア = 年換算上昇率(%) × R²（安定性） × 一貫性（上昇日割合）")
