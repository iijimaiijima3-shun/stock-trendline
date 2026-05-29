"""Trendline detection and scoring utilities."""
import numpy as np
import pandas as pd
from scipy.stats import linregress


def find_pivot_highs(prices: pd.Series, window: int = 5) -> pd.Series:
    """Return boolean Series marking local high pivots."""
    highs = pd.Series(False, index=prices.index)
    for i in range(window, len(prices) - window):
        if prices.iloc[i] == prices.iloc[i - window : i + window + 1].max():
            highs.iloc[i] = True
    return highs


def find_pivot_lows(prices: pd.Series, window: int = 5) -> pd.Series:
    """Return boolean Series marking local low pivots."""
    lows = pd.Series(False, index=prices.index)
    for i in range(window, len(prices) - window):
        if prices.iloc[i] == prices.iloc[i - window : i + window + 1].min():
            lows.iloc[i] = True
    return lows


def fit_trendline(x: np.ndarray, y: np.ndarray):
    """Fit a line through given points and return (slope, intercept, r2)."""
    slope, intercept, r, _, _ = linregress(x, y)
    return slope, intercept, r**2


def get_support_resistance_lines(df: pd.DataFrame, window: int = 5, n_lines: int = 3):
    """
    Detect the top N support and resistance trendlines.

    Returns list of dicts with keys: type, x0, y0, x1, y1, r2, slope_pct
    """
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    x_all = np.arange(len(df))

    pivot_high_mask = find_pivot_highs(high, window)
    pivot_low_mask = find_pivot_lows(low, window)

    pivot_high_idx = np.where(pivot_high_mask)[0]
    pivot_low_idx = np.where(pivot_low_mask)[0]

    lines = []

    def extract_lines(pivot_idx, series, line_type, min_points=3):
        if len(pivot_idx) < min_points:
            return []
        result = []
        # Sliding window over pivot combinations to find best-fit lines
        for start in range(len(pivot_idx) - min_points + 1):
            subset_idx = pivot_idx[start:]
            if len(subset_idx) < min_points:
                break
            x = subset_idx.astype(float)
            y = series.iloc[subset_idx].values.astype(float)
            slope, intercept, r2 = fit_trendline(x, y)
            if r2 < 0.7:
                continue
            slope_pct = slope / (intercept if intercept != 0 else 1) * 100
            result.append(
                dict(
                    type=line_type,
                    x0=int(subset_idx[0]),
                    y0=float(intercept + slope * subset_idx[0]),
                    x1=int(subset_idx[-1]),
                    y1=float(intercept + slope * subset_idx[-1]),
                    slope=slope,
                    intercept=intercept,
                    r2=r2,
                    slope_pct=slope_pct,
                    pivot_count=len(subset_idx),
                )
            )
        result.sort(key=lambda d: (-d["r2"], -d["pivot_count"]))
        return result[:n_lines]

    lines += extract_lines(pivot_high_idx, high, "resistance")
    lines += extract_lines(pivot_low_idx, low, "support")
    return lines


def score_uptrend(df: pd.DataFrame, period_days: int = 252) -> dict:
    """
    Score how strongly a stock is in a long-term uptrend.

    Returns dict with: slope_pct, r2, consistency, score
    """
    if len(df) < period_days // 2:
        return dict(slope_pct=0, r2=0, consistency=0, score=0)

    close = df["Close"].tail(period_days)
    x = np.arange(len(close))
    y = close.values.astype(float)

    slope, intercept, r2 = fit_trendline(x, y)

    # Consistency: fraction of days close > regression line
    fitted = intercept + slope * x
    consistency = float((y > fitted).mean())

    # Annualized slope as % of starting price
    start_price = float(fitted[0]) if fitted[0] != 0 else 1.0
    slope_pct = float(slope * 252 / start_price * 100)

    # Combined score: weight slope, r2, consistency
    score = max(0.0, slope_pct) * r2 * consistency

    return dict(slope_pct=slope_pct, r2=float(r2), consistency=consistency, score=float(score))
