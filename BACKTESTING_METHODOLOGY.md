# Backtesting Methodology & Statistical Validation Framework

## 1. Engine Selection & Design Decision

We evaluated **QuantConnect LEAN**, **Backtrader**, **VectorBT**, and a **custom deterministic event-driven Python engine**:
- **QuantConnect LEAN** requires the .NET runtime/Docker CLI and heavy external compilation.
- **VectorBT** relies on vectorized array broadcasting that makes dynamic portfolio-level risk vetoes (e.g., 30% sector caps, pairwise correlation checks across open positions, and 15% drawdown kill-switches) difficult to enforce chronologically without look-ahead leakage.
- **Decision**: We implemented a **custom deterministic, chronological bar-by-bar event-driven backtesting engine** (`core/backtesting/engine.py`) sharing the exact same `StrategySignalEngine` and `PortfolioRiskManager` used by the `PaperTradingEngine`.

---

## 2. Strict Chronological Execution (Zero Look-Ahead Bias)

On each simulated trading day $T$:
1. **Market Open ($T$)**: Pending `LONG` and `SHORT` exit and entry signals generated at Day $T-1$ close are executed against Day $T$'s actual opening price (`adj_open`) plus half-spread (`2.5 bps`), market impact slippage (`3.0 bps`), and per-share commissions (`$0.005/sh`, min `$1.00`, plus SEC fees on sells). Short positions enforce zero-leverage 100%-cash-collateralized margin.
2. **Intraday & Corporate Actions ($T$)**: Long positions collect cash dividends on ex-dates while short positions pay short dividend liabilities and accrue daily stock-borrow fee drag (`50 bps/yr`), track `highest_price_since_entry` / `lowest_price_since_entry`, and forcibly liquidate delisted stocks on their final trading bar.
3. **Market Close ($T$)**: Portfolio equity and drawdown are marked-to-market. Causal indicators up to Day $T$ and point-in-time `BMO`/`AMC` earnings are evaluated to queue signals for Day $T+1$ open.

---

## 3. Dataset Splits & Walk-Forward Validation

Every candidate strategy is evaluated across three non-overlapping temporal partitions:
- **In-Sample Development**: `2023-03-01` to `2024-02-29`
- **Validation & Parameter Selection**: `2024-03-01` to `2024-09-30`
- **Untouched Out-of-Sample (OOS) Testing**: `2024-10-01` to `2025-06-30`

Additionally, the engine runs:
- **4-Window Rolling Walk-Forward Validation** (`run_walk_forward_validation`) to measure consistency across Bull, Sideways, and Correction regimes.
- **Transaction Cost Stress Testing** (`1x`, `2x`, and `3x` spread/slippage/commission multipliers).
- **Monte Carlo Trade-Sequence Reshuffling** (`200` bootstrap permutations) to estimate 95th-percentile maximum drawdown.

---

## 4. Strategy Promotion Criteria (`StrategyEvaluationAgent`)

A strategy is **never** classified as promotable merely because its headline return is positive. It must pass all 9 configurable gates (`infrastructure/configuration/settings.py`):
1. **Positive Out-of-Sample Net Return**: $\text{OOS Net Return} > 0.0\%$
2. **Sharpe Ratio**: $\text{Sharpe} \ge 1.0$
3. **Profit Factor**: $\text{Profit Factor} \ge 1.3$
4. **Maximum Drawdown**: $\text{Max DD} \le 15.0\%$
5. **Minimum Sample Size**: $\text{Trade Count} \ge 15$
6. **Walk-Forward Consistency**: $\ge 60\%$ of walk-forward folds profitable
7. **Transaction Cost Robustness**: Positive net return under $2\times$ stressed transaction costs
8. **Benchmark Competitiveness**: Competitive risk-adjusted return against `SPY`
9. **Return Concentration Guardrail**: Single largest winning trade must not account for $> 65\%$ of total net profit

