"""Scan a watchlist of TSE stocks and rank by uptrend score."""
import yfinance as yf
import pandas as pd
from trendline import score_uptrend

# Top ~100 liquid TSE Prime market stocks (ticker.T format)
TSE_WATCHLIST = [
    "7203.T",  # トヨタ自動車
    "6758.T",  # ソニーグループ
    "8306.T",  # 三菱UFJフィナンシャル
    "9984.T",  # ソフトバンクグループ
    "6861.T",  # キーエンス
    "8316.T",  # 三井住友フィナンシャル
    "4063.T",  # 信越化学工業
    "9432.T",  # 日本電信電話
    "6954.T",  # ファナック
    "8035.T",  # 東京エレクトロン
    "7974.T",  # 任天堂
    "4502.T",  # 武田薬品工業
    "6367.T",  # ダイキン工業
    "9433.T",  # KDDI
    "4519.T",  # 中外製薬
    "6098.T",  # リクルートホールディングス
    "7267.T",  # 本田技研工業
    "2914.T",  # 日本たばこ産業
    "6501.T",  # 日立製作所
    "8801.T",  # 三井不動産
    "6702.T",  # 富士通
    "3382.T",  # セブン&アイ・ホールディングス
    "4543.T",  # テルモ
    "6301.T",  # 小松製作所
    "5108.T",  # ブリヂストン
    "8802.T",  # 三菱地所
    "6503.T",  # 三菱電機
    "9020.T",  # 東日本旅客鉄道
    "9021.T",  # 西日本旅客鉄道
    "4901.T",  # 富士フイルム
    "8411.T",  # みずほフィナンシャルグループ
    "7751.T",  # キヤノン
    "6971.T",  # 京セラ
    "4568.T",  # 第一三共
    "2802.T",  # 味の素
    "7832.T",  # バンダイナムコホールディングス
    "9022.T",  # 東海旅客鉄道
    "6902.T",  # 株式会社デンソー
    "6752.T",  # パナソニック
    "4307.T",  # 野村総合研究所
    "8031.T",  # 三井物産
    "8058.T",  # 三菱商事
    "8053.T",  # 住友商事
    "2413.T",  # エムスリー
    "6645.T",  # オムロン
    "4183.T",  # 三井化学
    "9104.T",  # 商船三井
    "9101.T",  # 日本郵船
    "5401.T",  # 日本製鉄
    "6479.T",  # ミネベアミツミ
    "6178.T",  # 日本郵政
    "3659.T",  # ネクソン
    "4661.T",  # オリエンタルランド
    "7309.T",  # シマノ
    "6762.T",  # TDK
    "4911.T",  # 資生堂
    "9613.T",  # NTTデータグループ
    "3401.T",  # 帝人
    "6301.T",  # 小松製作所
    "4704.T",  # トレンドマイクロ
    "7741.T",  # HOYA
    "2433.T",  # 博報堂DYホールディングス
    "6506.T",  # 安川電機
    "9766.T",  # コナミグループ
    "7270.T",  # SUBARU
    "4452.T",  # 花王
    "7201.T",  # 日産自動車
    "5020.T",  # ENEOS
    "8309.T",  # 三井住友トラスト
    "7733.T",  # オリンパス
    "6326.T",  # クボタ
    "4005.T",  # 住友化学
    "9602.T",  # 東宝
    "8252.T",  # 丸井グループ
    "3861.T",  # 王子HD
    "2501.T",  # サッポロHD
    "2503.T",  # キリンHD
    "2502.T",  # アサヒグループ
    "9107.T",  # 川崎汽船
]


def run_screener(period: str = "2y", min_score: float = 0.5) -> pd.DataFrame:
    """Download data for watchlist and return ranked DataFrame."""
    results = []
    tickers = list(dict.fromkeys(TSE_WATCHLIST))  # deduplicate
    data = yf.download(tickers, period=period, auto_adjust=True, progress=False)

    for ticker in tickers:
        try:
            if "Close" in data.columns.get_level_values(0):
                close_col = data["Close"][ticker].dropna()
                high_col = data["High"][ticker].dropna()
                low_col = data["Low"][ticker].dropna()
            else:
                continue

            if len(close_col) < 60:
                continue

            df = pd.DataFrame({"Close": close_col, "High": high_col, "Low": low_col})
            metrics = score_uptrend(df)

            info = yf.Ticker(ticker).fast_info
            name = ticker
            try:
                name = yf.Ticker(ticker).info.get("longName", ticker)
            except Exception:
                pass

            results.append(
                dict(
                    ticker=ticker,
                    name=name,
                    slope_pct=round(metrics["slope_pct"], 1),
                    r2=round(metrics["r2"], 3),
                    consistency=round(metrics["consistency"] * 100, 1),
                    score=round(metrics["score"], 2),
                    current_price=round(float(close_col.iloc[-1]), 0),
                )
            )
        except Exception:
            continue

    df_result = pd.DataFrame(results)
    if df_result.empty:
        return df_result
    df_result = df_result[df_result["slope_pct"] > 0]
    df_result = df_result.sort_values("score", ascending=False).reset_index(drop=True)
    df_result.index += 1
    return df_result
