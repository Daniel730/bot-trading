import sys
import pandas as pd
import numpy as np
import yfinance as yf
from statsmodels.tsa.stattools import coint, adfuller

def analyze_pair(ticker_a, ticker_b):
    print(f"--- Analyzing Pair: {ticker_a} / {ticker_b} ---")
    
    # 1. Fetch Data (1y)
    print(f"Fetching 1y data for {ticker_a} and {ticker_b}...")
    data = yf.download([ticker_a, ticker_b], period="1y", interval="1d", progress=False)['Close']
    
    if data.empty or ticker_a not in data.columns or ticker_b not in data.columns:
        print("Error: Could not fetch data for both tickers.")
        return

    data = data.dropna()
    
    # 2. Correlation
    corr = data[ticker_a].corr(data[ticker_b])
    print(f"Correlation (1y): {corr:.4f}")
    
    # 3. Cointegration (Engle-Granger)
    score, p_value, _ = coint(data[ticker_a], data[ticker_b])
    print(f"Cointegration p-value: {p_value:.4f}")
    
    if p_value < 0.05:
        print("✓ Cointegrated (p < 0.05). Excellent for arbitrage.")
    elif p_value < 0.10:
        print("⚠ Weakly Cointegrated (0.05 < p < 0.10). Use caution.")
    else:
        print("✗ Not Cointegrated (p > 0.10). Risky for arbitrage.")

    # 4. ADF Test for Stationarity of the Spread
    # Simple spread: A - (beta * B)
    # Using OLS for beta estimation
    import statsmodels.api as sm
    X = data[ticker_b]
    X = sm.add_constant(X)
    model = sm.OLS(data[ticker_a], X).fit()
    beta = model.params[ticker_b]
    alpha = model.params['const']
    spread = data[ticker_a] - (beta * data[ticker_b] + alpha)
    
    adf_p = adfuller(spread)[1]
    print(f"Spread ADF p-value: {adf_p:.4f}")
    print(f"Estimated Hedge Ratio (Beta): {beta:.4f}")
    
    if adf_p < 0.05:
        print("✓ Spread is stationary. Mean reversion confirmed.")
    else:
        print("✗ Spread is non-stationary. Likely to drift.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/cli_analyze.py TICKER_A TICKER_B")
        sys.exit(1)
    
    analyze_pair(sys.argv[1].upper(), sys.argv[2].upper())
