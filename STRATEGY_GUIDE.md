# Strategy Guide & Quantitative Specifications

Every strategy in the platform is represented as an immutable, versioned `StrategyConfig` (`core/strategies/registry.py`). Free-form natural language descriptions are never permitted to bypass the structured rule engine.

## Strategy Lifecycle

```
DRAFT ──▶ BACKTESTING ──▶ VALIDATION ──▶ PAPER_TRADING ──▶ APPROVED_FOR_REVIEW
                               │               │
                               ▼               ▼
                           REJECTED         RETIRED
```
- **Immutability Rule**: Once a strategy version enters `PAPER_TRADING`, attempting to overwrite it raises `PermissionError`. Parameter refinements must create a new incremented version (`v2`, `v3`, etc.) starting in `DRAFT`.

---

## Supported Strategy Families

### 1. Momentum / Trend Following (`MOMENTUM_TREND`) — Baseline 1 (`strat_momentum_trend`)
- **Observable Phenomenon**: Institutional accumulation in sector leaders creates persistent intermediate-term price momentum accompanied by above-average volume.
- **Holding Period**: 4–12 trading days.
- **Entry Rules**:
  - `Close > SMA(20) > SMA(50)`
  - 20-day Relative Strength vs `SPY` (`rs_vs_spy_20d`) $\ge 1.8\%$
  - 20-day return $\ge 2.5\%$
  - Volume confirmation: `Volume / SMA(Volume, 20)` $\ge 1.05\times$
  - `RSI(14)` between $52.0$ and $78.0$
  - Market regime filter: `SPY Close >= SPY SMA(50)`
- **Exit Rules**:
  - Initial stop-loss at $2.0 \times \text{ATR}(14)$ below entry
  - Trailing stop at $2.4 \times \text{ATR}(14)$ below highest high since entry
  - Take-profit target at $3.8 \times \text{ATR}(14)$ above entry
  - Trend invalidation exit if `Close < SMA(20)` after minimum holding period (4 days)
  - Time-stop at maximum holding period (12 trading days)

### 2. Post-Earnings Announcement Drift (`PEAD`) — Baseline 2 (`strat_pead_drift`)
- **Observable Phenomenon**: Under-reaction of analyst consensus and gradual institutional rebalancing following material quarterly earnings beats and guidance raises.
- **Holding Period**: 4–10 trading days.
- **Point-in-Time Guardrail**: After-Market-Close (`AMC`) announcements on Day $T$ are only visible starting Day $T+1$; Before-Market-Open (`BMO`) announcements on Day $T$ are visible on Day $T$.
- **Entry Rules**:
  - Quarterly EPS surprise $\ge +5.0\%$
  - YoY revenue growth $\ge +8.0\%$
  - Guidance revision delta $\ge +0.5\%$
  - Volume expansion $\ge 1.35\times$ 20-day average volume within 4 days of announcement
- **Exit Rules**:
  - Stop-loss at $2.0 \times \text{ATR}(14)$, trailing stop at $2.2 \times \text{ATR}(14)$, take-profit at $3.6 \times \text{ATR}(14)$, max hold 10 days.

### 3. Volatility Consolidation & Breakout (`BREAKOUT`) — Baseline 3 (`strat_volatility_breakout`)
- **Observable Phenomenon**: Supply exhaustion during multi-day tight range consolidation followed by institutional demand expansion breaking above 20-day resistance.
- **Holding Period**: 3–11 trading days.
- **Entry Rules**:
  - `Close > Prior 20-Day High` (`high_20d_prior`)
  - Prior 10-day consolidation range $\le 14.0\%$
  - Volume expansion $\ge 1.30\times$ 20-day average volume
  - `Close > SMA(50)` and `SPY Close >= SPY SMA(50)`
- **Exit Rules**:
  - Stop-loss at $1.8 \times \text{ATR}(14)$, trailing stop at $2.2 \times \text{ATR}(14)$, take-profit at $3.5 \times \text{ATR}(14)$, or close below `SMA(20)`.

### 4. Short-Term Mean Reversion (`MEAN_REVERSION`)
- **Entry Rules**: `RSI(14) <= 36.0`, `Close <= 1.01 * LowerBollingerBand(20, 2.0)`, and long-term uptrend filter `Close > 0.95 * SMA(200)`.
- **Exit Rules**: `RSI(14) >= 62.0`, $2.0 \times \text{ATR}(14)$ stop-loss, or 3–8 day holding window.

### 5. Sector Rotation / Relative Strength (`SECTOR_ROTATION`)
- **Entry Rules**: Stock belongs to top-2 ranked GICS sector by 20-day momentum, stock `rs_vs_spy_20d >= 3.0%`, and `Close > SMA(20) > SMA(50)`.
- **Exit Rules**: $2.0 \times \text{ATR}(14)$ stop-loss, $2.3 \times \text{ATR}(14)$ trailing stop, or 5–14 day holding window.

### 6. Structural Breakdown & Relative-Weakness Short (`BEARISH_BREAKDOWN`) — `strat_bearish_breakdown`
- **Observable Phenomenon**: Institutional distribution below 20-day support in laggards underperforming `SPY` creates multi-day downside continuation swings across bear and dispersion regimes.
- **Entry Rules (`ENTRY_SHORT`)**:
  - Asset verified `is_shortable=True` (`easy_to_borrow` prioritized) and outside 3-day pre-earnings blackout.
  - `Close < SMA(50)`, breaking near/below prior 15–20 day support (`low_20d_prior`), `rs_vs_spy_20d <= -3.0%`, `26.0 <= RSI(14) <= 54.0`, and `Volume >= 1.15x` 20-day average.
  - Each of the 3 Alpaca Paper Pods also runs a non-overlapping Short sub-mandate (`Pod #1`: 20d Low Breakdown; `Pod #2`: Downtrend Bear-Rally Exhaustion `RSI >= 60`; `Pod #3`: Bearish Catalyst / Negative PEAD Drift).
- **Exit Rules (`EXIT_SHORT`)**:
  - Hard buy-to-cover stop at `Entry + 1.8x ATR(14)`, downward breakeven/profit ratchets at `-1.0R` and `-1.65R`, take-profit at `Entry - 3.4x ATR(14)`, oversold cover at `RSI(14) <= 26.0`, or short-squeeze cover on `AI Catalyst >= +0.50`.


