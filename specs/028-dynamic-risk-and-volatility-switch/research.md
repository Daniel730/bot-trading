# Research: L2 Order Book Entropy & Dynamic Risk

**Feature Branch**: `028-dynamic-risk-and-volatility-switch`  
**Created**: 2026-04-06

## 1. Shannon Entropy for Market Volatility

Traditional volatility (Standard Deviation) is lagging. To detect *impending* volatility, we use Shannon Entropy on the L2 Order Book depth.

### The Formula:
$$H(L2) = -\sum_{i=1}^{n} P(p_i) \log P(p_i)$$

Where $P(p_i)$ is the normalized volume at price level $i$:
$$P(p_i) = \frac{V_i}{\sum_{j=1}^{n} V_j}$$

### Interpretation:
- **Low Entropy (H < 0.2)**: Highly concentrated liquidity. Stable prices expected.
- **High Entropy (H > 0.8)**: Fragmented liquidity, flickering orders. High probability of a price jump or toxic flow.
- **Entropy Imbalance**: If $H_{bid} \gg H_{ask}$, it indicates selling pressure and bid-side instability.

## 2. Dynamic Position Sizing (Performance Scaling)

We scale the Kelly Criterion size ($f^*$) by a Performance Multiplier ($M$):

$$ActualSize = f^* \times M$$

Where $M$ is derived from the current Sharpe Ratio ($S$) and Maximum Drawdown ($D$):

$$M = \max(0, \min(1, \frac{S}{1.0})) \times (1 - \frac{D}{D_{limit}})$$

If $D \ge 15\%$, $M$ becomes 0 (Absolute Stop).

## 3. Baselining Strategy (DEV_MODE)

Using crypto pairs (BTC-USD, ETH-USD) in `DEV_MODE` allows us to capture:
- **Flash Crashes**: Identify the entropy spike signature *before* the price drop.
- **Toxic Flow**: Identify when large orders are being "hunted" (Entropy oscillation).

These signatures will be used to set the `TOXIC_ENTROPY_THRESHOLD` in the Python orchestrator.
