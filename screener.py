"""Scan a watchlist of TSE stocks and rank by uptrend score or support proximity."""
import yfinance as yf
import pandas as pd
import numpy as np
from trendline import score_uptrend, get_support_resistance_lines
from stock_names import TICKER_TO_NAME, get_name

TSE_WATCHLIST = list(dict.fromkeys(TICKER_TO_NAME.keys()))


def _nearest_support_distance(df: pd.DataFrame) -> float:
    """
    Return how far (%) the current price is above the nearest support line.
    Positive = above support, negative = below (broken support).
    Returns 999 if no support found.
    """
    try:
        lines = get_support_resistance_lines(df, window=5, n_lines=3)
        support_lines = [l for l in lines if l["type"] == "support"]
        if not support_lines:
            return 999.0

        current_price = float(df["Close"].iloc[-1])
        last_idx = len(df) - 1

        distances = []
        for line in support_lines:
            # Extrapolate support level to today
            support_level = line["intercept"] + line["slope"] * last_idx
            if support_level > 0:
                dist_pct = (current_price - support_level) / support_level * 100
                distances.append(dist_pct)

        if not distances:
            return 999.0

        # Return the smallest positive distance (closest support above which price sits)
        positives = [d for d in distances if d >= 0]
        if positives:
            return round(min(positives), 2)
        return round(min(distances, key=abs), 2)
    except Exception:
        return 999.0


def run_screener(period: str = "2y") -> pd.DataFrame:
    """Download data for watchlist and return DataFrame with uptrend score and support proximity."""
    results = []
    tickers = TSE_WATCHLIST
    data = yf.download(tickers, period=period, auto_adjust=True, progress=False)

    for ticker in tickers:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                close_col = data["Close"][ticker].dropna()
                high_col = data["High"][ticker].dropna()
                low_col = data["Low"][ticker].dropna()
            else:
                continue

            if len(close_col) < 60:
                continue

            df = pd.DataFrame({"Close": close_col, "High": high_col, "Low": low_col})
            metrics = score_uptrend(df)
            support_dist = _nearest_support_distance(df)

            results.append(
                dict(
                    ticker=ticker,
                    name=get_name(ticker),
                    slope_pct=round(metrics["slope_pct"], 1),
                    r2=round(metrics["r2"], 3),
                    consistency=round(metrics["consistency"] * 100, 1),
                    score=round(metrics["score"], 2),
                    current_price=round(float(close_col.iloc[-1]), 0),
                    support_dist=support_dist,
                )
            )
        except Exception:
            continue

    df_result = pd.DataFrame(results)
    if df_result.empty:
        return df_result
    df_result = df_result[df_result["slope_pct"] > 0]
    df_result = df_result.reset_index(drop=True)
    df_result.index += 1
    return df_result
