"""Streamlit stock trendline analysis app for TSE stocks."""
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

from trendline import get_support_resistance_lines, score_uptrend
from screener import run_screener
from stock_names import search_by_name, get_name
from bookmarks import load_bookmarks, add_bookmark, remove_bookmark

st.set_page_config(
    page_title="株価トレンドライン分析",
    page_icon="📈",
    layout="wide",
)

st.title("📈 株価トレンドライン分析")

# Chart config: pan on drag (no box-select zoom), keep scroll/button zoom
CHART_CONFIG = {
    "scrollZoom": True,
    "modeBarButtonsToRemove": ["select2d", "lasso2d"],
    "displaylogo": False,
}


# ── Shared helpers ─────────────────────────────────────────────────────────────
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


def build_chart(
    df: pd.DataFrame,
    ticker: str,
    name: str,
    pivot_window: int = 5,
    n_lines: int = 3,
    highlight_support: bool = False,
    height: int = 420,
) -> go.Figure:
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

        is_support_highlighted = highlight_support and line["type"] == "support"
        fig.add_trace(go.Scatter(
            x=[x0_date, ext_date],
            y=[line["y0"], ext_y1],
            mode="lines",
            name=label,
            showlegend=show_legend,
            line=dict(
                color=color_map[line["type"]],
                width=3 if is_support_highlighted else 2,
                dash="solid" if is_support_highlighted else "dot",
            ),
            hovertemplate=f"{label}<br>R²={line['r2']:.2f}<br>傾き={line['slope_pct']:+.3f}%/日<extra></extra>",
        ))

    fig.update_layout(
        title=f"{name}（{ticker}）",
        xaxis_title="日付",
        yaxis_title="株価",
        xaxis_rangeslider_visible=False,
        dragmode="pan",
        height=height,
        template="plotly_dark",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(t=60, b=40),
    )
    return fig


def render_stock_chart(ticker: str, name: str, period: str, pivot_window: int, n_lines: int,
                       highlight_support: bool = False, show_volume: bool = False):
    """Download data and render chart + metrics. Returns df or None."""
    with st.spinner(f"{name} のデータを取得中..."):
        df = fetch_df(ticker, period)
    if df is None:
        st.error("データを取得できませんでした。")
        return None

    current_price = float(df["Close"].iloc[-1])
    prev_price = float(df["Close"].iloc[-2])
    change_pct = (current_price - prev_price) / prev_price * 100
    metrics = score_uptrend(df)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("現在値", f"¥{current_price:,.0f}")
    m2.metric("前日比", f"{change_pct:+.2f}%", delta=f"{change_pct:+.2f}%")
    m3.metric("年換算上昇率", f"{metrics['slope_pct']:+.1f}%")
    m4.metric("トレンドスコア", f"{metrics['score']:.1f}")

    fig = build_chart(df, ticker, name, pivot_window, n_lines, highlight_support)
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

    if show_volume and "Volume" in df.columns:
        fig_vol = go.Figure(go.Bar(
            x=df.index.tolist(), y=df["Volume"],
            name="出来高", marker_color="#7986cb", opacity=0.6,
        ))
        fig_vol.update_layout(
            height=130, template="plotly_dark",
            margin=dict(t=10, b=10), xaxis_rangeslider_visible=False,
            dragmode="pan",
        )
        st.plotly_chart(fig_vol, use_container_width=True, config=CHART_CONFIG)

    return df, metrics


# ── Tabs ───────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🔍 銘柄分析", "⭐ 銘柄おすすめ", "🔖 お気に入り"])


# ══════════════════════════════════════════════════════════════════════════════
# Tab 1: Individual analysis
# ══════════════════════════════════════════════════════════════════════════════
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
                st.info(f"検索結果: **{selected_name}**（{selected_ticker}）")
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

    btn_col1, btn_col2 = st.columns([3, 1])
    with btn_col1:
        draw_clicked = st.button("チャートを描画", type="primary", use_container_width=True,
                                 disabled=not selected_ticker)
    with btn_col2:
        bm_clicked = st.button("🔖 お気に入りに追加", use_container_width=True,
                               disabled=not selected_ticker)

    if bm_clicked and selected_ticker:
        add_bookmark(selected_ticker, selected_name or get_name(selected_ticker))
        st.success(f"**{selected_name or selected_ticker}** をお気に入りに追加しました。")

    if draw_clicked and selected_ticker:
        name = selected_name or get_name(selected_ticker)
        result = render_stock_chart(
            selected_ticker, name,
            period_options[period_label],
            pivot_window, n_lines,
            show_volume=show_volume,
        )


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2: Screener
# ══════════════════════════════════════════════════════════════════════════════
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

    if "screener_result" in st.session_state:
        result_df: pd.DataFrame = st.session_state["screener_result"]
        mode = st.session_state.get("screener_mode", screen_mode)
        threshold = st.session_state.get("screener_threshold", support_threshold)
        c_period = st.session_state.get("screener_chart_period", chart_period)
        c_top_n = st.session_state.get("screener_top_n", top_n)

        if result_df.empty:
            st.warning("結果が見つかりませんでした。")
        elif "サポートライン" in mode:
            # ── サポートライン接近 × 上昇トレンド品質の複合スコア
            filtered = result_df[
                (result_df["support_dist"] >= 0) &
                (result_df["support_dist"] <= threshold) &
                (result_df["score"] > 0)
            ].copy()

            if filtered.empty:
                st.info(f"サポートラインから{threshold}%以内の銘柄は現在見つかりませんでした。閾値を広げてみてください。")
            else:
                # composite = トレンドスコア / (1 + 距離%)  → 近いほど・上昇が安定なほど高い
                filtered["composite"] = filtered["score"] / (1 + filtered["support_dist"])
                filtered = filtered.sort_values("composite", ascending=False).head(c_top_n).reset_index(drop=True)
                filtered.index += 1

                st.subheader(f"🎯 サポートライン接近 × 上昇品質ランキング — {len(filtered)} 件")
                st.caption(
                    "**右肩上がりの安定度**と**サポートラインへの近さ**を掛け合わせてランキング。"
                    "上位ほど「安定した上昇トレンド中でかつ買い場に近い」銘柄です。支持線は緑の実線で表示。"
                )

                show_cols = filtered[["ticker", "name", "current_price", "support_dist", "slope_pct", "r2", "composite"]].copy()
                show_cols.columns = ["コード", "銘柄名", "現在値(円)", "サポートまで(%)", "年換算上昇率(%)", "R²", "総合スコア"]
                show_cols["総合スコア"] = show_cols["総合スコア"].round(2)
                st.dataframe(show_cols, use_container_width=True, hide_index=True)

                st.markdown("---")
                for _, row in filtered.iterrows():
                    ticker = row["ticker"]
                    name = row["name"]
                    dist = row["support_dist"]

                    with st.expander(f"📊 {name}（{ticker}）― サポートまで {dist:.1f}%", expanded=True):
                        bm_key = f"bm_{ticker}"
                        if st.button("🔖 お気に入りに追加", key=bm_key):
                            add_bookmark(ticker, name)
                            st.success(f"**{name}** をお気に入りに追加しました。")

                        mc1, mc2, mc3, mc4 = st.columns(4)
                        mc1.metric("現在値", f"¥{row['current_price']:,.0f}")
                        mc2.metric("年換算上昇率", f"{row['slope_pct']:+.1f}%")
                        mc3.metric("R²（安定性）", f"{row['r2']:.3f}")
                        mc4.metric("サポートまで", f"{dist:.1f}%")

                        with st.spinner(f"{name} のチャートを描画中..."):
                            df = fetch_df(ticker, c_period)
                        if df is not None:
                            fig = build_chart(df, ticker, name, pivot_window=5, n_lines=3, highlight_support=True)
                            st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)

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
                dragmode="pan",
            )
            st.plotly_chart(fig_bar, use_container_width=True, config=CHART_CONFIG)

            show_cols = display_df[["ticker", "name", "current_price", "slope_pct", "r2", "consistency", "score"]].copy()
            show_cols.columns = ["コード", "銘柄名", "現在値(円)", "年換算上昇率(%)", "R²", "一貫性(%)", "スコア"]
            st.dataframe(show_cols, use_container_width=True, hide_index=True)
            st.caption("スコア = 年換算上昇率(%) × R²（安定性） × 一貫性（上昇日割合）")


# ══════════════════════════════════════════════════════════════════════════════
# Tab 3: Bookmarks / Favorites
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### 🔖 お気に入り銘柄")

    bookmarks = load_bookmarks()

    if not bookmarks:
        st.info("お気に入りがまだありません。「銘柄分析」タブまたはスクリーナーの「🔖 お気に入りに追加」ボタンで登録できます。")
    else:
        fav_period_options = {"3ヶ月": "3mo", "6ヶ月": "6mo", "1年": "1y", "2年": "2y", "5年": "5y"}
        opt_col1, opt_col2 = st.columns([2, 2])
        with opt_col1:
            fav_period = st.selectbox("期間", list(fav_period_options.keys()), index=2, key="fav_period")
        with opt_col2:
            fav_pivot = st.slider("ピボット感度", 3, 15, 5, key="fav_pivot")

        # Clickable table — row selection triggers chart display
        bm_rows = [{"会社名": n, "銘柄コード": t} for t, n in bookmarks.items()]
        bm_df = pd.DataFrame(bm_rows)
        bm_tickers = list(bookmarks.keys())

        st.caption("👇 行をクリックするとチャートが表示されます")
        selection = st.dataframe(
            bm_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="fav_table",
        )

        selected_rows = selection.selection.rows if selection.selection else []

        # Delete button row
        del_col1, del_col2 = st.columns([4, 1])
        with del_col2:
            if selected_rows and st.button("🗑️ 選択を削除", use_container_width=True, key="fav_del"):
                del_ticker = bm_tickers[selected_rows[0]]
                del_name = bookmarks[del_ticker]
                remove_bookmark(del_ticker)
                st.success(f"**{del_name}** をお気に入りから削除しました。")
                st.rerun()

        # Auto-render chart for selected row
        if selected_rows:
            idx = selected_rows[0]
            fav_ticker = bm_tickers[idx]
            fav_name = bookmarks[fav_ticker]
            st.markdown(f"---\n#### {fav_name}（{fav_ticker}）")
            render_stock_chart(
                fav_ticker, fav_name,
                fav_period_options[fav_period],
                pivot_window=fav_pivot,
                n_lines=3,
                show_volume=True,
            )
