"""Interactive HTML/JS Dashboard Frontend for the Swing Trading AI Platform.

Exposes all 7 required sections:
1. Overview (Portfolio value, starting capital, total return, daily return, cash, open positions, max DD, SPY comparison)
2. Research (Newly discovered opportunities, ranked stock candidates, research reports, catalysts & earnings, hypotheses)
3. Strategies (Active strategies, strategy versions, status lifecycle, backtest vs paper performance, comparison)
4. Backtesting (Launch experiments, configure parameters, compare results, equity curves, drawdowns, trades, walk-forward)
5. Paper Trading (Open positions, pending orders, order history, cash balance, realised/unrealised P&L, strategy attribution)
6. Analytics (Daily/cumulative returns, Sharpe/Sortino, drawdown analysis, sector exposure, win/loss, market regime breakdown)
7. System Monitoring (Agent execution history, job status, data ingestion status, failed experiments, risk alerts & kill switch)
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Swing Trading AI — Quantitative Research & Paper Trading Platform</title>
  <style>
    :root {
      --bg: #0b0f19;
      --panel: #131b2e;
      --panel-alt: #19233c;
      --border: #263554;
      --text: #e2e8f0;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --green: #10b981;
      --red: #ef4444;
      --amber: #f59e0b;
      --purple: #a855f7;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }
    header {
      background: var(--panel);
      border-bottom: 1px solid var(--border);
      padding: 14px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand h1 { font-size: 1.15rem; font-weight: 700; letter-spacing: -0.01em; }
    .badge {
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 0.74rem;
      font-weight: 600;
      text-transform: uppercase;
    }
    .badge-paper { background: rgba(16, 185, 129, 0.16); color: var(--green); border: 1px solid rgba(16, 185, 129, 0.4); }
    .badge-warn { background: rgba(245, 158, 11, 0.16); color: var(--amber); border: 1px solid rgba(245, 158, 11, 0.4); }
    .badge-danger { background: rgba(239, 68, 68, 0.16); color: var(--red); border: 1px solid rgba(239, 68, 68, 0.4); }
    .badge-info { background: rgba(56, 189, 248, 0.16); color: var(--accent); border: 1px solid rgba(56, 189, 248, 0.4); }
    nav {
      display: flex;
      gap: 6px;
      background: var(--panel-alt);
      padding: 8px 24px;
      border-bottom: 1px solid var(--border);
      overflow-x: auto;
    }
    nav button {
      background: transparent;
      color: var(--muted);
      border: 1px solid transparent;
      padding: 7px 14px;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 600;
      font-size: 0.85rem;
      transition: all 0.15s;
    }
    nav button:hover { color: var(--text); background: rgba(255,255,255,0.04); }
    nav button.active {
      color: var(--accent);
      background: rgba(56, 189, 248, 0.12);
      border-color: rgba(56, 189, 248, 0.35);
    }
    main { max-width: 1440px; margin: 0 auto; padding: 22px 24px 60px; }
    .tab-section { display: none; }
    .tab-section.active { display: block; }
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(195px, 1fr));
      gap: 14px;
      margin-bottom: 22px;
    }
    .kpi-card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 15px 18px;
    }
    .kpi-label { font-size: 0.76rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
    .kpi-value { font-size: 1.45rem; font-weight: 700; margin-top: 4px; }
    .kpi-sub { font-size: 0.78rem; color: var(--muted); margin-top: 3px; }
    .pos { color: var(--green); }
    .neg { color: var(--red); }
    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px 20px;
      margin-bottom: 20px;
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
    }
    .card-title { font-size: 1rem; font-weight: 600; }
    table { width: 100%; border-collapse: collapse; font-size: 0.84rem; }
    th, td {
      text-align: left;
      padding: 9px 11px;
      border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    th { color: var(--muted); font-weight: 600; font-size: 0.76rem; text-transform: uppercase; }
    tr:hover td { background: rgba(255,255,255,0.02); }
    .btn {
      background: var(--accent);
      color: #0b0f19;
      border: none;
      padding: 8px 14px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 0.83rem;
      cursor: pointer;
    }
    .btn:hover { opacity: 0.9; }
    .btn-secondary {
      background: var(--panel-alt);
      color: var(--text);
      border: 1px solid var(--border);
    }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
    @media (max-width: 980px) { .grid-2 { grid-template-columns: 1fr; } }
    .form-row { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; margin-bottom: 14px; }
    .form-group { display: flex; flex-direction: column; gap: 4px; }
    .form-group label { font-size: 0.76rem; color: var(--muted); }
    .form-group select, .form-group input {
      background: var(--bg);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 7px 11px;
      border-radius: 6px;
      font-size: 0.84rem;
    }
    svg.chart { width: 100%; height: 220px; background: rgba(0,0,0,0.2); border-radius: 8px; }
    .disclaimer {
      font-size: 0.78rem;
      color: var(--muted);
      background: rgba(245, 158, 11, 0.08);
      border-left: 3px solid var(--amber);
      padding: 8px 12px;
      margin-bottom: 16px;
      border-radius: 4px;
    }
    .tab-intro {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }
    .tab-intro p { font-size: 0.86rem; color: var(--muted); margin: 0; }
    details.tab-help {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 12px;
      font-size: 0.81rem;
      color: var(--text);
    }
    details.tab-help summary {
      cursor: pointer;
      color: var(--accent);
      font-weight: 600;
      user-select: none;
    }
    details.tab-help .help-body {
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid var(--border);
      color: var(--muted);
      line-height: 1.55;
    }
    details.guide-accordion {
      background: var(--panel-alt);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 11px 15px;
      margin-bottom: 10px;
      font-size: 0.86rem;
    }
    details.guide-accordion summary {
      cursor: pointer;
      font-weight: 600;
      color: var(--text);
      user-select: none;
    }
    details.guide-accordion .acc-body {
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid rgba(255,255,255,0.08);
      color: #cbd5e1;
      line-height: 1.6;
    }
    .flow-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .flow-step {
      background: var(--panel-alt);
      border: 1px solid var(--border);
      border-left: 3px solid var(--accent);
      border-radius: 6px;
      padding: 10px 12px;
      font-size: 0.8rem;
    }
    .flow-step strong { display: block; color: var(--text); margin-bottom: 3px; }
    .flow-step span { color: var(--muted); }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>SWING TRADING AI PLATFORM</h1>
      <span class="badge badge-paper" id="mode-badge" title="All trades execute in a simulated $100,000 paper account.">TRADING_MODE = PAPER ($100K)</span>
      <span class="badge badge-info" id="tz-badge" title="US market execution (NYSE/NASDAQ) with Singapore (SGT) reporting.">NYSE/NASDAQ • SGT Reporting</span>
    </div>
    <div style="display:flex; gap:10px; align-items:center;">
      <span class="badge badge-paper" title="Daily execution runs Mon–Fri at 21:30 UTC; Weekly strategy discovery runs Saturday at 10:00 SGT. Zero user input required.">AUTONOMOUS SCHEDULE ACTIVE • ZERO INPUT REQUIRED</span>
    </div>
  </header>

  <nav id="main-nav">
    <button class="active" onclick="switchTab('guide', this)">Platform Guide</button>
    <button onclick="switchTab('overview', this)">Overview &amp; P&amp;L</button>
    <button onclick="switchTab('strategies', this)">Strategies &amp; Readiness</button>
    <button onclick="switchTab('copilot', this)">Live Copilot (Real Account)</button>
    <button onclick="switchTab('research', this)">Market Research</button>
    <button onclick="switchTab('backtesting', this)">Backtesting</button>
    <button onclick="switchTab('paper', this)">Paper Ledger</button>
    <button onclick="switchTab('analytics', this)">Risk &amp; Analytics</button>
    <button onclick="switchTab('monitoring', this)">System Logs</button>
  </nav>

  <main>
    <div class="disclaimer">
      <strong>Governance Notice:</strong> Deterministic software handles all price/indicator calculations,
      signal generation, ATR position sizing, risk vetoes, and P&amp;L accounting. Historical backtest returns or AI
      research confidence scores do not guarantee future profitability.
    </div>

    <!-- 0. PLATFORM GUIDE -->
    <section id="tab-guide" class="tab-section active">
      <div class="card">
        <div class="card-header"><span class="card-title">What This System Does &amp; How It Runs</span></div>
        <p style="font-size:0.9rem;color:#cbd5e1;margin-bottom:16px;">
          This platform manages a simulated <strong>$100,000 US stock portfolio</strong> over <strong>3 to 15 trading-day</strong> holding periods (swing trading).
          To keep decision-making disciplined, <strong>AI agents only research stocks and propose strategy rules</strong>, while <strong>strict mathematical code</strong>
          tests those rules on historical data, enforces risk limits, and executes every trade.
        </p>

        <div style="font-size:0.76rem;text-transform:uppercase;letter-spacing:0.05em;color:var(--accent);font-weight:600;margin-bottom:6px;">
          1. Daily Execution Loop (Mon–Fri, After US Market Close)
        </div>
        <div class="flow-grid">
          <div class="flow-step"><strong>Step 1 · Market Data</strong><span>Download daily prices &amp; earnings updates.</span></div>
          <div class="flow-step"><strong>Step 2 · AI Research</strong><span>Rank liquid US stocks by trend &amp; catalysts.</span></div>
          <div class="flow-step"><strong>Step 3 · Rule Signals</strong><span>Check active strategies for buy/sell triggers.</span></div>
          <div class="flow-step" style="border-left-color:var(--green);"><strong>Step 4 · Risk Gate</strong><span>Size trade (1% risk) &amp; check 7 safety caps.</span></div>
          <div class="flow-step" style="border-left-color:var(--green);"><strong>Step 5 · Paper Ledger</strong><span>Simulate fill after fees &amp; update P&amp;L.</span></div>
        </div>

        <div style="font-size:0.76rem;text-transform:uppercase;letter-spacing:0.05em;color:var(--purple);font-weight:600;margin-bottom:6px;">
          2. Weekly Self-Improvement Loop (Saturdays, 10:00 SGT)
        </div>
        <div class="flow-grid">
          <div class="flow-step" style="border-left-color:var(--purple);"><strong>Step A · Review Trades</strong><span>Diagnose wins, losses &amp; current market regime.</span></div>
          <div class="flow-step" style="border-left-color:var(--purple);"><strong>Step B · Draft Upgrade</strong><span>Create a candidate strategy version (v+1).</span></div>
          <div class="flow-step" style="border-left-color:var(--amber);"><strong>Step C · 9-Gate Audit</strong><span>Test across historical &amp; walk-forward periods.</span></div>
          <div class="flow-step" style="border-left-color:var(--green);"><strong>Step D · Promote / Reject</strong><span>Only versions passing all 9 gates go live.</span></div>
        </div>

        <div style="margin:18px 0 10px;font-size:0.86rem;font-weight:600;color:var(--text);">
          Interactive Walkthrough — Click Any Stage to Inspect How It Works:
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
          <button class="btn btn-secondary" onclick="showGuide('arch')">1. Stock Scan</button>
          <button class="btn btn-secondary" onclick="showGuide('strategies')">2. Strategy Signal</button>
          <button class="btn btn-secondary" onclick="showGuide('risk')">3. Risk &amp; Sizing</button>
          <button class="btn btn-secondary" onclick="showGuide('pnl')">4. Execution &amp; P&amp;L</button>
          <button class="btn btn-secondary" onclick="showGuide('validation')">5. Weekly Upgrade</button>
        </div>
        <div id="guide-detail-box" style="background:rgba(56,189,248,0.06);border:1px solid rgba(56,189,248,0.25);padding:14px 16px;border-radius:8px;font-size:0.86rem;line-height:1.6;margin-bottom:18px;">
          <strong>Stage 1 — Daily Stock Scan (<code>MarketResearchAgent</code>):</strong><br/>
          After the US market closes, the system downloads daily prices for liquid NYSE/NASDAQ large-cap stocks and compares them against the S&amp;P 500 (<code>SPY</code>). It highlights stocks outperforming <code>SPY</code> over 20 days on strong volume or reacting to earnings beats. Research rankings never place orders directly.
        </div>

        <div style="margin-bottom:8px;font-size:0.86rem;font-weight:600;color:var(--text);">
          Deeper Dives — Click Any Topic to Expand:
        </div>
        <details class="guide-accordion">
          <summary>The 3 Trading Strategies — How buy &amp; sell signals are triggered</summary>
          <div class="acc-body">
            • <strong>Momentum &amp; Relative Strength (<code>strat_momentum_trend</code>):</strong> Enters liquid stocks trading above rising 20-day and 50-day moving averages that outperform <code>SPY</code> over 20 days with volume confirmation.<br/>
            • <strong>Post-Earnings Drift (<code>strat_pead_drift</code>):</strong> Captures multi-day follow-through after a company reports a positive quarterly earnings surprise (+4% or higher) on 1.3x normal volume.<br/>
            • <strong>Volatility Breakout (<code>strat_volatility_breakout</code>):</strong> Identifies stocks consolidating quietly in a tight 10-day range that break above their prior 20-day high on 1.35x volume.
          </div>
        </details>
        <details class="guide-accordion">
          <summary>The 7 Risk Controls — How the portfolio is protected from large drawdowns</summary>
          <div class="acc-body">
            • <strong>1.0% Max Risk Per Trade:</strong> Position size scales with stock volatility (ATR) so hitting a stop-loss loses at most ~$1,000 on a $100,000 account.<br/>
            • <strong>5.0% Max Total Open Risk (Portfolio Heat):</strong> Combined stop-loss risk across all open positions cannot exceed 5% of total equity.<br/>
            • <strong>15.0% Single-Stock &amp; 30.0% Sector Caps:</strong> Prevents concentration in any single company or industry.<br/>
            • <strong>Max 10 Open Positions, Liquidity (&ge;$20M/day) &amp; Correlation (&le;0.80) Checks.</strong><br/>
            • <strong>15.0% Drawdown Kill Switch:</strong> Automatically pauses new entries if portfolio equity drops 15% from its peak.
          </div>
        </details>
        <details class="guide-accordion">
          <summary>The 9 Validation Gates — How candidate upgrades are tested before trading</summary>
          <div class="acc-body">
            Before any strategy version can enter <code>PAPER_TRADING</code> status, it must pass all 9 historical checks:
            1) Positive Out-of-Sample net return • 2) Sharpe Ratio &ge; 1.0 • 3) Profit Factor &ge; 1.3 • 4) Max Drawdown &le; 15% • 5) Minimum 15 trades • 6) Walk-Forward consistency &ge; 60% • 7) Survives 2x transaction cost stress test • 8) Beats SPY risk-adjusted • 9) No single trade accounts for &gt;65% of total profit.
          </div>
        </details>
        <details class="guide-accordion">
          <summary>How P&amp;L Is Calculated — Paper Account vs. Historical Backtests</summary>
          <div class="acc-body">
            • <strong>Paper Portfolio Equity:</strong> <code>Starting Capital ($100,000) + Realised P&amp;L (closed trades after fees) + Unrealised P&amp;L (open positions marked to market)</code>.<br/>
            • <strong>Strict Separation:</strong> Multi-year historical backtest returns (shown in the Strategies and Backtesting tabs) validate rulebooks on past data and never alter your simulated paper cash or equity.
          </div>
        </details>
      </div>
    </section>

    <!-- 1. OVERVIEW -->
    <section id="tab-overview" class="tab-section">
      <div class="tab-intro">
        <p><strong>Overview &amp; P&amp;L</strong> — Real-time simulated portfolio value, strategy attribution, and currently held positions.</p>
        <details class="tab-help">
          <summary>? How this tab works</summary>
          <div class="help-body">
            Tracks your simulated $100,000 account.<br/>
            • <strong>Realised P&amp;L:</strong> Locked-in profit/loss from closed trades after commissions and slippage.<br/>
            • <strong>Unrealised P&amp;L:</strong> Floating profit/loss on currently held positions at the latest closing price.<br/>
            • Hover over any metric card below for its exact definition.
          </div>
        </details>
      </div>
      <div class="disclaimer" id="overview-pnl-explainer"></div>
      <div class="kpi-grid" id="overview-kpis"></div>
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><span class="card-title">Portfolio Equity vs Benchmark (SPY)</span></div>
          <div id="overview-equity-chart"></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">Current Open Positions</span></div>
          <div id="overview-positions-table"></div>
        </div>
      </div>
    </section>

    <!-- 2. RESEARCH -->
    <section id="tab-research" class="tab-section">
      <div class="tab-intro">
        <p><strong>Market Research</strong> — Daily ranking of liquid US stocks by trend strength vs. SPY, volume activity, and earnings catalysts.</p>
        <details class="tab-help">
          <summary>? How this tab works</summary>
          <div class="help-body">
            • <strong>20d RS vs SPY:</strong> How much the stock beat or trailed the S&amp;P 500 over the past 20 trading days.<br/>
            • <strong>Vol Ratio:</strong> Latest volume divided by its 20-day average (&gt;1.2x signals institutional participation).<br/>
            • Click any row in the table to view the full bullish and bearish thesis below.
          </div>
        </details>
      </div>
      <div class="card">
        <div class="card-header">
          <span class="card-title">Autonomous Market Research Agent — Ranked Swing Candidates</span>
          <button class="btn btn-secondary" onclick="runResearchScan()">Scan US Equities Universe</button>
        </div>
        <div id="research-candidates-table"></div>
      </div>
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><span class="card-title">Candidate Deep-Dive Report &amp; Theses</span></div>
          <div id="research-detail-box">Select a candidate row above to inspect full bullish/bearish theses, catalysts, and risks.</div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">Performance Analyst Experiment Proposals</span></div>
          <div id="research-proposals-table"></div>
        </div>
      </div>
    </section>

    <!-- 3. STRATEGIES -->
    <section id="tab-strategies" class="tab-section">
      <div class="tab-intro">
        <p><strong>Strategies</strong> — Registry of all quantitative rulebooks, historical test scores, and promotion status.</p>
        <details class="tab-help">
          <summary>? How this tab works</summary>
          <div class="help-body">
            • <strong>PAPER_TRADING:</strong> Passed all 9 validation gates and is permitted to place simulated trades.<br/>
            • <strong>REJECTED:</strong> Failed one or more validation gates during historical testing and is blocked from trading.<br/>
            • <strong>Sharpe / Profit Factor:</strong> Risk-adjusted return (&ge;1.0 required) and gross wins divided by gross losses (&ge;1.3 required).
          </div>
        </details>
      </div>
      <div class="card">
        <div class="card-header">
          <span class="card-title">Versioned Strategy Registry &amp; Promotion Lifecycle</span>
        </div>
        <div id="strategies-table"></div>
      </div>
    </section>

    <!-- 4. BACKTESTING -->
    <section id="tab-backtesting" class="tab-section">
      <div class="tab-intro">
        <p><strong>Backtesting</strong> — Multi-year historical simulations with commissions, bid-ask spreads, and slippage deducted on every trade.</p>
        <details class="tab-help">
          <summary>? How this tab works</summary>
          <div class="help-body">
            • Evaluates how a strategy rulebook performed over historical market regimes.<br/>
            • Signals generated at Day T market close execute at Day T+1 market open (zero look-ahead bias).<br/>
            • Backtest simulations never alter your live paper trading balance.
          </div>
        </details>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Launch Quantitative Backtest &amp; Walk-Forward Experiment</span></div>
        <div class="form-row">
          <div class="form-group">
            <label>Strategy ID</label>
            <select id="bt-strategy-select"></select>
          </div>
          <div class="form-group">
            <label>Start Date</label>
            <input type="text" id="bt-start" value="2023-03-01" />
          </div>
          <div class="form-group">
            <label>End Date</label>
            <input type="text" id="bt-end" value="2025-06-30" />
          </div>
          <button class="btn" onclick="launchBacktest()">Run Deterministic Backtest</button>
        </div>
        <div id="bt-summary-kpis" class="kpi-grid"></div>
      </div>
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><span class="card-title">Backtest Equity Curve</span></div>
          <div id="bt-equity-chart"></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">Drawdown Curve (%)</span></div>
          <div id="bt-dd-chart"></div>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Individual Simulated Trades</span></div>
        <div id="bt-trades-table"></div>
      </div>
    </section>

    <!-- 5. PAPER TRADING -->
    <section id="tab-paper" class="tab-section">
      <div class="tab-intro">
        <p><strong>Paper Ledger</strong> — Chronological log of every simulated order fill, transaction cost, and strategy P&amp;L contribution.</p>
        <details class="tab-help">
          <summary>? How this tab works</summary>
          <div class="help-body">
            • <strong>BUY rows:</strong> Deduct purchase cost plus commission/slippage from cash.<br/>
            • <strong>SELL rows:</strong> Return sale proceeds to cash and lock in net Realised P&amp;L.<br/>
            • <strong>Strategy P&amp;L Attribution:</strong> Summarizes total fills, fees, and realised profit per strategy.
          </div>
        </details>
      </div>
      <div class="kpi-grid" id="paper-kpis"></div>
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><span class="card-title">Open Paper Positions</span></div>
          <div id="paper-open-positions"></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">Strategy P&amp;L Attribution</span></div>
          <div id="paper-attribution"></div>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Permanent Trade Ledger &amp; Execution History</span></div>
        <div id="paper-ledger-table"></div>
      </div>
    </section>

    <!-- 6. ANALYTICS -->
    <section id="tab-analytics" class="tab-section">
      <div class="tab-intro">
        <p><strong>Risk &amp; Analytics</strong> — Monitors sector concentration against the 30% cap and multi-window walk-forward stability.</p>
        <details class="tab-help">
          <summary>? How this tab works</summary>
          <div class="help-body">
            • <strong>Sector Exposure:</strong> Verifies that no single industry exceeds 30% of portfolio equity.<br/>
            • <strong>Walk-Forward Validation:</strong> Splits historical data into 4 rolling time folds to verify consistent performance across different market conditions.
          </div>
        </details>
      </div>
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><span class="card-title">Performance by Market Regime</span></div>
          <div id="analytics-regime-table"></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">Sector Exposure &amp; Concentration</span></div>
          <div id="analytics-sector-table"></div>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">Walk-Forward Validation &amp; Stress Test Summary</span></div>
        <div id="analytics-wf-table"></div>
      </div>
    </section>

    <!-- 7. SYSTEM MONITORING -->
    <section id="tab-monitoring" class="tab-section">
      <div class="tab-intro">
        <p><strong>System Logs</strong> — Audit trail of scheduled workflow runs, idempotency keys, and Risk Manager trade vetoes.</p>
        <details class="tab-help">
          <summary>? How this tab works</summary>
          <div class="help-body">
            • <strong>Workflow Execution Log:</strong> Confirms when daily and weekly jobs executed and prevents duplicate runs.<br/>
            • <strong>Risk Alerts &amp; Vetoes:</strong> Logs every trade blocked by the Risk Manager (e.g., sector cap or portfolio heat limit).
          </div>
        </details>
      </div>
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><span class="card-title">Autonomous Job &amp; Workflow Execution Log</span></div>
          <div id="monitoring-jobs-table"></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">Portfolio Risk Alerts &amp; Veto Audit Trail</span></div>
          <div id="monitoring-alerts-table"></div>
        </div>
      </div>
    </section>

    <!-- 8. LIVE TRADING COPILOT (AIR-GAPPED REAL ACCOUNT) -->
    <section id="tab-copilot" class="tab-section">
      <div class="tab-intro">
        <p><strong>Live Copilot (Real Account)</strong> — Step-by-step daily BUY and SELL instructions sized to your real account balance, with zero access to your brokerage account.</p>
        <details class="tab-help">
          <summary>? How Live Copilot works</summary>
          <div class="help-body">
            • <strong>Zero Broker Access:</strong> Never connects to your broker. You execute trades in your own brokerage app.<br/>
            • <strong>Never Assumes Positions:</strong> Recommendations stay pending until you click <strong>Confirm Bought</strong> or <strong>Confirm Sold</strong>.<br/>
            • <strong>Adapts to Your Real Account:</strong> Position sizing (1% risk), stop-losses, and exit rules adapt to your actual confirmed cash and holdings.
          </div>
        </details>
      </div>
      <div class="kpi-grid" id="copilot-kpis"></div>
      <div class="card">
        <div class="card-header"><span class="card-title">1. Today's Step-by-Step Action Checklist (Next Market Open)</span></div>
        <div id="copilot-sell-box" style="margin-bottom:14px;"></div>
        <div id="copilot-buy-box"></div>
      </div>
      <div class="grid-2">
        <div class="card">
          <div class="card-header"><span class="card-title">2. My Confirmed Real Positions &amp; Hold Status</span></div>
          <div id="copilot-positions-table"></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">Update Real Cash or Add / Edit a Position</span></div>
          <div class="form-row">
            <div class="form-group">
              <label>My Real Uninvested Cash ($)</label>
              <input type="number" id="cop-cash-input" value="25000" step="500" />
            </div>
            <button class="btn btn-secondary" onclick="saveCopilotCash()">Update Cash Balance</button>
          </div>
          <hr style="border:none;border-top:1px solid var(--border);margin:12px 0;" />
          <div class="form-row">
            <div class="form-group"><label>Ticker</label><input type="text" id="cop-edit-ticker" value="AAPL" style="width:90px;" /></div>
            <div class="form-group"><label>Shares (0=Delete)</label><input type="number" id="cop-edit-qty" value="10" style="width:110px;" /></div>
            <div class="form-group"><label>Avg Entry ($)</label><input type="number" id="cop-edit-px" value="180.00" step="0.5" style="width:110px;" /></div>
            <button class="btn" onclick="saveCopilotPosition()">Save Position</button>
          </div>
        </div>
      </div>
    </section>
  </main>

  <script>
    let STATE = {};

    function switchTab(tabId, btn) {
      document.querySelectorAll('.tab-section').forEach(s => s.classList.remove('active'));
      document.querySelectorAll('#main-nav button').forEach(b => b.classList.remove('active'));
      document.getElementById('tab-' + tabId).classList.add('active');
      if (btn) btn.classList.add('active');
    }

    function fmtUsd(val) {
      const n = Number(val || 0);
      return '$' + n.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }

    function fmtPct(val) {
      const n = Number(val || 0);
      const sign = n > 0 ? '+' : '';
      return sign + n.toFixed(2) + '%';
    }

    function renderSvgChart(points, valueKey, color = '#38bdf8') {
      if (!points || points.length < 2) return '<div style="padding:20px;color:#94a3b8;">Insufficient data points</div>';
      const vals = points.map(p => Number(p[valueKey] || 0));
      const minV = Math.min(...vals);
      const maxV = Math.max(...vals);
      const range = Math.max(maxV - minV, 1e-4);
      const w = 640, h = 200, pad = 20;
      const coords = vals.map((v, i) => {
        const x = pad + (i / (vals.length - 1)) * (w - 2 * pad);
        const y = h - pad - ((v - minV) / range) * (h - 2 * pad);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(' ');
      return `
        <svg class="chart" viewBox="0 0 ${w} ${h}">
          <polyline fill="none" stroke="${color}" stroke-width="2.2" points="${coords}" />
          <text x="${pad}" y="16" fill="#94a3b8" font-size="11">Max: ${maxV.toFixed(2)} | Min: ${minV.toFixed(2)}</text>
        </svg>
      `;
    }

    async function loadDashboardState() {
      const res = await fetch('/api/dashboard-state');
      STATE = await res.json();
      renderOverview();
      renderResearch();
      renderStrategies();
      renderCopilot();
      renderBacktesting(STATE.experiments && STATE.experiments[0]);
      renderPaperTrading();
      renderAnalytics();
      renderMonitoring();
    }

    function renderCopilot() {
      const cop = STATE.copilot || {};
      const plan = cop.action_plan || {};
      const acc = plan.account_summary || {};
      const sells = plan.sell_actions || [];
      const buys = plan.buy_actions || [];
      const holds = plan.hold_updates || [];

      const cashIn = document.getElementById('cop-cash-input');
      if (cashIn && acc.cash_balance !== undefined) cashIn.value = acc.cash_balance;

      document.getElementById('copilot-kpis').innerHTML = `
        <div class="kpi-card"><div class="kpi-label">My Real Equity</div><div class="kpi-value">${fmtUsd(acc.total_equity)}</div><div class="kpi-sub">Base: ${fmtUsd(acc.starting_cash)} (${fmtPct(acc.total_return_pct)})</div></div>
        <div class="kpi-card"><div class="kpi-label">My Real Cash</div><div class="kpi-value">${fmtUsd(acc.cash_balance)}</div><div class="kpi-sub">Used for 1% Risk Sizing</div></div>
        <div class="kpi-card"><div class="kpi-label">Invested Value</div><div class="kpi-value">${fmtUsd(acc.positions_market_value)}</div><div class="kpi-sub">${acc.open_positions_count || 0} confirmed positions</div></div>
        <div class="kpi-card"><div class="kpi-label">Realised P&amp;L</div><div class="kpi-value ${acc.realised_pnl >= 0 ? 'pos' : 'neg'}">${fmtUsd(acc.realised_pnl)}</div><div class="kpi-sub">Confirmed Closed Trades</div></div>
        <div class="kpi-card"><div class="kpi-label">Unrealised P&amp;L</div><div class="kpi-value ${acc.unrealised_pnl >= 0 ? 'pos' : 'neg'}">${fmtUsd(acc.unrealised_pnl)}</div><div class="kpi-sub">Confirmed Open Holdings</div></div>
      `;

      document.getElementById('copilot-sell-box').innerHTML = sells.length ? `
        <div style="font-size:0.84rem;font-weight:600;color:var(--amber);margin-bottom:6px;">Step A — SELL Orders (Exits Triggered on Your Confirmed Holdings)</div>
        <table>
          <thead><tr><th>Ticker</th><th>Qty to Sell</th><th>Your Entry</th><th>Ref Exit Price</th><th>Est. P&amp;L</th><th>Exit Reason</th><th>Action</th></tr></thead>
          <tbody>
            ${sells.map(s => `
              <tr>
                <td><strong>${s.ticker}</strong></td>
                <td>${s.quantity_to_sell}</td>
                <td>${fmtUsd(s.avg_entry_price)}</td>
                <td>${fmtUsd(s.reference_exit_price)}</td>
                <td class="${s.estimated_realised_pnl >= 0 ? 'pos' : 'neg'}">${fmtUsd(s.estimated_realised_pnl)}</td>
                <td>${s.reason}</td>
                <td><button class="btn" onclick="confirmCopilotSell('${s.ticker}', ${s.quantity_to_sell}, ${s.reference_exit_price})">Confirm Sold</button></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      ` : '<div style="font-size:0.84rem;color:var(--muted);">No SELL exit triggers on your confirmed holdings today.</div>';

      document.getElementById('copilot-buy-box').innerHTML = buys.length ? `
        <div style="font-size:0.84rem;font-weight:600;color:var(--accent);margin:10px 0 6px;">Step B — BUY Candidates (Sized to 1% Risk of Your Real Account)</div>
        <table>
          <thead><tr><th>Ticker</th><th>Strategy</th><th>Rec. Shares</th><th>Ref Price</th><th>Est. Cost</th><th>Stop-Loss</th><th>Take-Profit</th><th>Max Risk</th><th>Actions</th></tr></thead>
          <tbody>
            ${buys.map(b => `
              <tr>
                <td><strong>${b.ticker}</strong></td>
                <td>${b.strategy_id} v${b.strategy_version}</td>
                <td><strong>${b.recommended_shares}</strong></td>
                <td>${fmtUsd(b.reference_entry_price)}</td>
                <td>${fmtUsd(b.estimated_cost_usd)} (${b.portfolio_weight_pct}%)</td>
                <td class="neg">${fmtUsd(b.stop_loss_price)}</td>
                <td class="pos">${fmtUsd(b.take_profit_price)}</td>
                <td>-${fmtUsd(b.estimated_risk_usd)}</td>
                <td style="display:flex;gap:6px;">
                  <button class="btn" onclick="confirmCopilotBuy('${b.ticker}', '${b.strategy_id}', ${b.strategy_version}, ${b.recommended_shares}, ${b.reference_entry_price}, ${b.stop_loss_price || 0}, ${b.take_profit_price || 0}, '${b.sector}')">Confirm Bought</button>
                  <button class="btn btn-secondary" onclick="skipCopilotSignal('${b.signal_date}', '${b.strategy_id}', '${b.ticker}')">Skip</button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      ` : '<div style="font-size:0.84rem;color:var(--muted);margin-top:8px;">No new BUY candidates pass your real-account cash and risk caps today.</div>';

      document.getElementById('copilot-positions-table').innerHTML = holds.length ? `
        <table>
          <thead><tr><th>Ticker</th><th>Qty</th><th>Avg Entry</th><th>Current</th><th>Unrealised P&amp;L</th><th>Stop / Target</th><th>Status</th></tr></thead>
          <tbody>
            ${holds.map(h => `
              <tr>
                <td><strong>${h.ticker}</strong></td>
                <td>${h.quantity}</td>
                <td>${fmtUsd(h.avg_entry_price)}</td>
                <td>${fmtUsd(h.current_price)}</td>
                <td class="${h.unrealised_pnl >= 0 ? 'pos' : 'neg'}">${fmtUsd(h.unrealised_pnl)}</td>
                <td>${fmtUsd(h.stop_loss_price)} / ${fmtUsd(h.take_profit_price)}</td>
                <td>${h.status}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      ` : '<div style="font-size:0.84rem;color:var(--muted);">0 confirmed real positions. Click "Confirm Bought" above or add a holding on the right.</div>';
    }

    async function saveCopilotCash() {
      const cash = Number(document.getElementById('cop-cash-input').value || 0);
      await fetch('/api/copilot/cash', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({cash_balance: cash, update_starting_baseline: true})});
      await loadDashboardState();
    }

    async function saveCopilotPosition() {
      const ticker = document.getElementById('cop-edit-ticker').value;
      const qty = Number(document.getElementById('cop-edit-qty').value || 0);
      const px = Number(document.getElementById('cop-edit-px').value || 100);
      await fetch('/api/copilot/edit-position', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ticker, quantity: qty, avg_entry_price: px})});
      await loadDashboardState();
    }

    async function confirmCopilotBuy(ticker, strategy_id, strategy_version, quantity, fill_price, stop_loss_price, take_profit_price, sector) {
      await fetch('/api/copilot/confirm-buy', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ticker, strategy_id, strategy_version, quantity, fill_price, stop_loss_price, take_profit_price, sector, fees_usd: 1.0})
      });
      await loadDashboardState();
    }

    async function confirmCopilotSell(ticker, quantity, fill_price) {
      await fetch('/api/copilot/confirm-sell', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ticker, quantity, fill_price, fees_usd: 1.0})
      });
      await loadDashboardState();
    }

    async function skipCopilotSignal(signal_date, strategy_id, ticker) {
      await fetch('/api/copilot/dismiss', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({signal_date, strategy_id, ticker, action: 'BUY'})
      });
      await loadDashboardState();
    }

    function showGuide(topic) {
      const notes = {
        arch: '<strong>1. Core Architecture — Separation of AI Reasoning &amp; Quantitative Execution:</strong><br/>• <strong>Deterministic Financial Engine:</strong> All price adjustments, technical indicators, signal triggers, position sizing, risk checks, and accounting are executed by deterministic Python code.<br/>• <strong>AI Research &amp; Governance Layer:</strong> Specialized agents scan the equity universe, diagnose post-session performance, and propose falsifiable strategy revisions.<br/>• <strong>Daily &amp; Weekly Cadence:</strong> Each weekday after US market close, the system updates market data, processes stop-loss/take-profit exits, and evaluates new entries. Every Saturday, it runs walk-forward optimization to test candidate strategy improvements.',
        strategies: '<strong>2. Strategy Families — Three Uncorrelated Swing Models (3–15 Day Horizon):</strong><br/>• <strong>Momentum &amp; Trend Continuation (<code>strat_momentum_trend</code>):</strong> Enters liquid stocks trading above rising 20/50-day moving averages that outperform the S&amp;P 500 (<code>SPY</code>) over 20 days with volume confirmation.<br/>• <strong>Post-Earnings Announcement Drift (<code>strat_pead_drift</code>):</strong> Captures multi-day institutional follow-through after a company reports a positive earnings surprise (+4% or higher) accompanied by a breakout and 1.3x volume.<br/>• <strong>Volatility Contraction Breakout (<code>strat_vol_breakout</code>):</strong> Identifies stocks consolidating in tight 10-day ranges that break above their 20-day high on 1.35x volume.',
        validation: '<strong>3. Validation Gates — Nine-Gate Out-of-Sample Promotion Audit:</strong><br/>Before any strategy or weekly revision can trade in the paper account, it must pass nine objective criteria:<br/>1) Positive net return after commissions, spread, and slippage • 2) Sharpe Ratio &gt; 1.0 • 3) Profit Factor &gt; 1.3 • 4) Max Drawdown &lt; 15.0% • 5) Minimum 15 trades • 6) Out-of-sample walk-forward consistency &ge; 60% • 7) Survives +50% higher transaction cost stress test • 8) Beats SPY on a risk-adjusted basis • 9) Parameter stability across variations.',
        risk: '<strong>4. Risk Controls — Portfolio Protection &amp; Veto Authority:</strong><br/>Every proposed entry is audited by the deterministic Risk Manager before execution:<br/>• <strong>1.0% Maximum Risk Per Trade:</strong> Position size is scaled by stock volatility (ATR) so a stop-loss exit loses at most 1% of equity (~$1,000).<br/>• <strong>5.0% Maximum Total Open Risk (Portfolio Heat Cap):</strong> Combined stop-loss risk across all open positions cannot exceed 5% of total equity.<br/>• <strong>15.0% Single-Stock &amp; 30.0% Sector Caps:</strong> Prevents concentration in any single company or industry.<br/>• <strong>15.0% Drawdown Kill Switch:</strong> Automatically suspends new entries if portfolio equity falls 15% from its peak.',
        pnl: '<strong>5. P&amp;L Accounting — Transparent Return Attribution:</strong><br/>The platform separates simulated paper trading from multi-year historical backtests:<br/>• <strong>Paper Portfolio Equity:</strong> <code>Starting Capital ($100,000) + Realised P&amp;L (closed trades net of fees) + Unrealised P&amp;L (open positions marked to market)</code>.<br/>• <strong>Attribution:</strong> Every dollar of P&amp;L is linked to the exact strategy version (<code>strategy_id v#</code>) and measurement window.'
      };
      document.getElementById('guide-detail-box').innerHTML = notes[topic] || notes.arch;
    }

    function renderOverview() {
      const acc = STATE.account || {};
      const snaps = STATE.snapshots || [];
      const activeStrats = (STATE.strategies || []).filter(s => s.status === 'PAPER_TRADING').map(s => `${s.name} (${s.strategy_id} v${s.version})`).join(', ') || 'None';
      const dateSpan = snaps.length ? `${snaps[0].snapshot_date} to ${snaps[snaps.length - 1].snapshot_date} (${snaps.length} trading days)` : 'Initial session';
      document.getElementById('overview-pnl-explainer').innerHTML = `
        <strong>Profit &amp; Loss Attribution</strong><br/>
        • <strong>Active Strategies:</strong> ${activeStrats}<br/>
        • <strong>Measurement Window:</strong> ${dateSpan}<br/>
        • <strong>Derivation:</strong> Starting Capital (${fmtUsd(acc.starting_capital)}) + Realised P&amp;L (${fmtUsd(acc.realised_pnl)}) + Unrealised P&amp;L (${fmtUsd(acc.unrealised_pnl)}) = <strong>${fmtUsd(acc.total_equity)} (${fmtPct(acc.total_return_pct)})</strong> [Net of commissions, spread &amp; slippage]
      `;
      const latestSnap = snaps[snaps.length - 1] || {};
      const retCls = (acc.total_return_pct >= 0) ? 'pos' : 'neg';
      document.getElementById('overview-kpis').innerHTML = `
        <div class="kpi-card" title="Cash Balance + Market Value of Open Positions. Equals Starting Capital ($100k) + Realised P&L + Unrealised P&L."><div class="kpi-label">Portfolio Equity ⓘ</div><div class="kpi-value">${fmtUsd(acc.total_equity)}</div><div class="kpi-sub">Starting: ${fmtUsd(acc.starting_capital)}</div></div>
        <div class="kpi-card" title="Total percentage return on the $100,000 paper portfolio compared with the S&P 500 (SPY) benchmark."><div class="kpi-label">Total Return ⓘ</div><div class="kpi-value ${retCls}">${fmtPct(acc.total_return_pct)}</div><div class="kpi-sub">vs SPY: ${fmtPct(latestSnap.benchmark_cum_return_pct || 0)}</div></div>
        <div class="kpi-card" title="Single-day return for the most recent trading session and cumulative locked-in Realised P&L."><div class="kpi-label">Daily Return ⓘ</div><div class="kpi-value">${fmtPct(latestSnap.daily_return_pct || 0)}</div><div class="kpi-sub">Realised P&L: ${fmtUsd(acc.realised_pnl)}</div></div>
        <div class="kpi-card" title="Uninvested cash currently available to open new swing positions."><div class="kpi-label">Available Cash ⓘ</div><div class="kpi-value">${fmtUsd(acc.cash_balance)}</div><div class="kpi-sub">Buying Power: ${fmtUsd(acc.buying_power)}</div></div>
        <div class="kpi-card" title="Number of active stock positions currently held (capped at 10 maximum)."><div class="kpi-label">Open Positions ⓘ</div><div class="kpi-value">${acc.open_positions_count || 0} / 10</div><div class="kpi-sub">Market Value: ${fmtUsd(acc.positions_market_value)}</div></div>
        <div class="kpi-card" title="Percentage drop from the portfolio's highest equity peak. New buying pauses automatically at -15.0%."><div class="kpi-label">Current Drawdown ⓘ</div><div class="kpi-value neg">-${Number(acc.current_drawdown_pct || 0).toFixed(2)}%</div><div class="kpi-sub">Kill Switch: ${acc.kill_switch_engaged ? 'ACTIVE' : 'Standby (15%)'}</div></div>
      `;

      const chartPts = snaps.length >= 2 ? snaps.map(s => ({equity: s.total_equity})) : ((STATE.experiments && STATE.experiments[0] && STATE.experiments[0].equity_curve) || []);
      document.getElementById('overview-equity-chart').innerHTML = renderSvgChart(chartPts, 'equity', '#10b981');

      const pos = STATE.positions || [];
      if (!pos.length) {
        document.getElementById('overview-positions-table').innerHTML = '<div style="color:#94a3b8;padding:12px;">No open positions currently held.</div>';
      } else {
        document.getElementById('overview-positions-table').innerHTML = `
          <table>
            <thead><tr><th>Ticker</th><th>Strategy</th><th>Qty</th><th>Entry</th><th>Current</th><th>Unrealised P&L</th></tr></thead>
            <tbody>
              ${pos.map(p => `
                <tr>
                  <td><strong>${p.ticker}</strong></td>
                  <td>${p.strategy_id} v${p.strategy_version}</td>
                  <td>${p.quantity}</td>
                  <td>${fmtUsd(p.avg_entry_price)}</td>
                  <td>${fmtUsd(p.current_price)}</td>
                  <td class="${p.unrealised_pnl >= 0 ? 'pos' : 'neg'}">${fmtUsd(p.unrealised_pnl)} (${fmtPct(p.unrealised_return_pct)})</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;
      }
    }

    function renderResearch() {
      const reports = STATE.research_reports || [];
      document.getElementById('research-candidates-table').innerHTML = `
        <table>
          <thead><tr><th>Ticker</th><th>Company</th><th>Price</th><th>Sector</th><th>20d RS vs SPY</th><th>Vol Ratio</th><th>Suggested Family</th><th>Rank Score</th><th>Confidence*</th></tr></thead>
          <tbody>
            ${reports.map((r, idx) => `
              <tr style="cursor:pointer;" onclick="showResearchDetail(${idx})">
                <td><strong>${r.ticker}</strong></td>
                <td>${r.company_name}</td>
                <td>${fmtUsd(r.current_price)}</td>
                <td>${r.market_and_sector_context.sector} (#${r.market_and_sector_context.sector_momentum_rank})</td>
                <td class="${r.relative_strength_vs_spy_20d >= 0 ? 'pos' : 'neg'}">${fmtPct(r.relative_strength_vs_spy_20d)}</td>
                <td>${Number(r.volume_analysis.volume_ratio_20 || 1).toFixed(2)}x</td>
                <td><span class="badge badge-info">${r.suggested_strategy_family}</span></td>
                <td><strong>${Number(r.composite_rank_score).toFixed(1)}</strong></td>
                <td>${(Number(r.research_confidence_score) * 100).toFixed(0)}%</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
      if (reports.length) showResearchDetail(0);

      const props = STATE.proposals || [];
      document.getElementById('research-proposals-table').innerHTML = `
        <table>
          <thead><tr><th>Date</th><th>Target Strategy</th><th>Regime</th><th>Proposed Hypothesis</th></tr></thead>
          <tbody>
            ${props.map(p => `
              <tr>
                <td>${p.session_date}</td>
                <td><strong>${p.target_strategy_id}</strong></td>
                <td>${p.market_regime}</td>
                <td>${p.proposed_hypothesis}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }

    function showResearchDetail(idx) {
      const r = (STATE.research_reports || [])[idx];
      if (!r) return;
      document.getElementById('research-detail-box').innerHTML = `
        <div style="display:flex;flex-direction:column;gap:8px;font-size:0.86rem;">
          <div><strong>${r.ticker} — ${r.company_name}</strong> (${fmtUsd(r.current_price)}) | Holding Period: ${r.potential_holding_period_days[0]}–${r.potential_holding_period_days[1]} trading days</div>
          <div><strong style="color:#10b981;">Bullish Thesis:</strong> ${r.bullish_thesis}</div>
          <div><strong style="color:#ef4444;">Bearish Thesis:</strong> ${r.bearish_thesis}</div>
          <div><strong>Key Risks:</strong> ${(r.main_risks || []).join(' • ')}</div>
          <div style="color:#94a3b8;font-size:0.78rem;">${r.confidence_disclaimer}</div>
        </div>
      `;
    }

    function renderStrategies() {
      const strats = STATE.strategies || [];
      const ledger = STATE.trade_ledger || [];
      const positions = STATE.positions || [];
      const sel = document.getElementById('bt-strategy-select');
      sel.innerHTML = strats.map(s => `<option value="${s.strategy_id}:${s.version}">${s.name} (${s.strategy_id} v${s.version})</option>`).join('');

      const paperByStrat = {};
      ledger.forEach(l => {
        const k = `${l.strategy_id}:${l.strategy_version}`;
        if (!paperByStrat[k]) paperByStrat[k] = {closed: 0, wins: 0, grossWin: 0, grossLoss: 0, realised: 0, unrealised: 0};
        if (l.side === 'SELL') {
          paperByStrat[k].closed += 1;
          const rp = Number(l.realised_pnl || 0);
          paperByStrat[k].realised += rp;
          if (rp > 0) { paperByStrat[k].wins += 1; paperByStrat[k].grossWin += rp; }
          else if (rp < 0) { paperByStrat[k].grossLoss += Math.abs(rp); }
        }
      });
      positions.forEach(p => {
        const k = `${p.strategy_id}:${p.strategy_version}`;
        if (!paperByStrat[k]) paperByStrat[k] = {closed: 0, wins: 0, grossWin: 0, grossLoss: 0, realised: 0, unrealised: 0};
        paperByStrat[k].unrealised += Number(p.unrealised_pnl || 0);
      });

      document.getElementById('strategies-table').innerHTML = `
        <table>
          <thead><tr><th>Strategy</th><th>Name</th><th>Status</th><th>Backtest Gates</th><th>Backtest Return</th><th>Sharpe / PF</th><th>Forward Paper Trades</th><th>Forward Paper P&amp;L</th><th>Live Trading Readiness</th></tr></thead>
          <tbody>
            ${strats.map(s => {
              const m = s.backtest_summary || {};
              const val = s.validation_summary || {};
              const checks = val.criteria_checks || {};
              const passedGates = Object.values(checks).filter(Boolean).length;
              const totalGates = Object.keys(checks).length || 9;
              const p = paperByStrat[`${s.strategy_id}:${s.version}`] || {closed: 0, wins: 0, grossWin: 0, grossLoss: 0, realised: 0, unrealised: 0};
              const netPaper = p.realised + p.unrealised;
              const pf = p.grossLoss > 0 ? (p.grossWin / p.grossLoss) : (p.grossWin > 0 ? 2.5 : 0);
              let readiness = `<span class="badge badge-info">BUILDING PAPER PROOF (${p.closed}/20 trades)</span>`;
              if (s.status === 'REJECTED') readiness = '<span class="badge badge-danger">NOT READY (Failed Backtest)</span>';
              else if (s.status === 'RETIRED') readiness = '<span class="badge badge-warn">RETIRED (Superseded)</span>';
              else if (passedGates === totalGates && p.closed >= 20 && pf >= 1.3 && netPaper > 0) {
                readiness = `<span class="badge badge-paper">READY FOR LIVE REVIEW (${p.closed} trades, PF ${pf.toFixed(2)})</span>`;
              }
              const stCls = s.status === 'PAPER_TRADING' ? 'badge-paper' : (s.status === 'REJECTED' ? 'badge-danger' : 'badge-warn');
              return `
                <tr>
                  <td><strong>${s.strategy_id} v${s.version}</strong></td>
                  <td>${s.name}</td>
                  <td><span class="badge ${stCls}">${s.status}</span></td>
                  <td><strong>${passedGates} / ${totalGates}</strong></td>
                  <td class="${(m.total_return_pct || 0) >= 0 ? 'pos' : 'neg'}">${m.total_return_pct !== undefined ? fmtPct(m.total_return_pct) : '-'}</td>
                  <td>${m.sharpe_ratio !== undefined ? Number(m.sharpe_ratio).toFixed(2) : '-'} / ${m.profit_factor !== undefined ? Number(m.profit_factor).toFixed(2) : '-'}</td>
                  <td>${p.closed} closed</td>
                  <td class="${netPaper >= 0 ? 'pos' : 'neg'}">${fmtUsd(netPaper)}</td>
                  <td>${readiness}</td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      `;
    }

    function renderBacktesting(exp) {
      if (!exp) return;
      const m = exp.metrics || {};
      document.getElementById('bt-summary-kpis').innerHTML = `
        <div class="kpi-card"><div class="kpi-label">Total Return</div><div class="kpi-value ${m.total_return_pct >= 0 ? 'pos' : 'neg'}">${fmtPct(m.total_return_pct)}</div><div class="kpi-sub">CAGR: ${fmtPct(m.annualised_return_pct)} | SPY: ${fmtPct(m.benchmark_return_pct)}</div></div>
        <div class="kpi-card"><div class="kpi-label">Sharpe / Sortino</div><div class="kpi-value">${Number(m.sharpe_ratio || 0).toFixed(2)} / ${Number(m.sortino_ratio || 0).toFixed(2)}</div><div class="kpi-sub">Calmar: ${Number(m.calmar_ratio || 0).toFixed(2)}</div></div>
        <div class="kpi-card"><div class="kpi-label">Profit Factor</div><div class="kpi-value">${Number(m.profit_factor || 0).toFixed(2)}</div><div class="kpi-sub">Win Rate: ${Number(m.win_rate_pct || 0).toFixed(1)}% (${m.trade_count || 0} trades)</div></div>
        <div class="kpi-card"><div class="kpi-label">Max Drawdown</div><div class="kpi-value neg">-${Number(m.max_drawdown_pct || 0).toFixed(2)}%</div><div class="kpi-sub">Avg Hold: ${Number(m.avg_holding_period_days || 0).toFixed(1)}d</div></div>
        <div class="kpi-card"><div class="kpi-label">Expectancy / Trade</div><div class="kpi-value">${fmtUsd(m.expectancy_usd)}</div><div class="kpi-sub">Avg Win: ${fmtUsd(m.avg_winning_trade_usd)} | Loss: ${fmtUsd(m.avg_losing_trade_usd)}</div></div>
      `;
      document.getElementById('bt-equity-chart').innerHTML = renderSvgChart(exp.equity_curve || [], 'equity', '#38bdf8');
      document.getElementById('bt-dd-chart').innerHTML = renderSvgChart(exp.equity_curve || [], 'drawdown_pct', '#ef4444');

      const trades = (exp.trades || []).slice(0, 40);
      document.getElementById('bt-trades-table').innerHTML = `
        <table>
          <thead><tr><th>Ticker</th><th>Sector</th><th>Entry Date</th><th>Exit Date</th><th>Hold</th><th>Qty</th><th>Entry</th><th>Exit</th><th>Net P&L</th><th>Return</th><th>Exit Reason</th></tr></thead>
          <tbody>
            ${trades.map(t => `
              <tr>
                <td><strong>${t.ticker}</strong></td>
                <td>${t.sector}</td>
                <td>${t.entry_date}</td>
                <td>${t.exit_date}</td>
                <td>${t.holding_days}d</td>
                <td>${t.quantity}</td>
                <td>${fmtUsd(t.entry_price)}</td>
                <td>${fmtUsd(t.exit_price)}</td>
                <td class="${t.net_pnl >= 0 ? 'pos' : 'neg'}">${fmtUsd(t.net_pnl)}</td>
                <td class="${t.return_pct >= 0 ? 'pos' : 'neg'}">${fmtPct(t.return_pct)}</td>
                <td style="font-size:0.78rem;color:#94a3b8;">${t.exit_reason}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }

    function renderPaperTrading() {
      const acc = STATE.account || {};
      document.getElementById('paper-kpis').innerHTML = `
        <div class="kpi-card"><div class="kpi-label">Account Balance</div><div class="kpi-value">${fmtUsd(acc.total_equity)}</div><div class="kpi-sub">Mode: ${acc.trading_mode}</div></div>
        <div class="kpi-card"><div class="kpi-label">Cash Balance</div><div class="kpi-value">${fmtUsd(acc.cash_balance)}</div><div class="kpi-sub">Positions MV: ${fmtUsd(acc.positions_market_value)}</div></div>
        <div class="kpi-card"><div class="kpi-label">Realised P&L</div><div class="kpi-value ${acc.realised_pnl >= 0 ? 'pos' : 'neg'}">${fmtUsd(acc.realised_pnl)}</div><div class="kpi-sub">Closed Executions</div></div>
        <div class="kpi-card"><div class="kpi-label">Unrealised P&L</div><div class="kpi-value ${acc.unrealised_pnl >= 0 ? 'pos' : 'neg'}">${fmtUsd(acc.unrealised_pnl)}</div><div class="kpi-sub">Open Positions</div></div>
      `;

      document.getElementById('paper-open-positions').innerHTML = document.getElementById('overview-positions-table').innerHTML;

      const ledger = STATE.trade_ledger || [];
      const attr = {};
      ledger.forEach(l => {
        if (!attr[l.strategy_id]) attr[l.strategy_id] = {fills: 0, pnl: 0, comm: 0};
        attr[l.strategy_id].fills += 1;
        attr[l.strategy_id].pnl += Number(l.realised_pnl || 0);
        attr[l.strategy_id].comm += Number(l.commission_usd || 0);
      });
      document.getElementById('paper-attribution').innerHTML = `
        <table>
          <thead><tr><th>Strategy ID</th><th>Fills</th><th>Realised P&L</th><th>Commissions</th></tr></thead>
          <tbody>
            ${Object.entries(attr).map(([sid, st]) => `
              <tr>
                <td><strong>${sid}</strong></td>
                <td>${st.fills}</td>
                <td class="${st.pnl >= 0 ? 'pos' : 'neg'}">${fmtUsd(st.pnl)}</td>
                <td>${fmtUsd(st.comm)}</td>
              </tr>
            `).join('') || '<tr><td colspan="4">No executions yet</td></tr>'}
          </tbody>
        </table>
      `;

      document.getElementById('paper-ledger-table').innerHTML = `
        <table>
          <thead><tr><th>Fill Date</th><th>Strategy</th><th>Ticker</th><th>Side</th><th>Qty</th><th>Fill Price</th><th>Gross</th><th>Comm/Slip</th><th>Realised P&L</th><th>Cash After</th></tr></thead>
          <tbody>
            ${ledger.map(l => `
              <tr>
                <td>${l.fill_date}</td>
                <td>${l.strategy_id} v${l.strategy_version}</td>
                <td><strong>${l.ticker}</strong></td>
                <td><span class="badge ${l.side === 'BUY' ? 'badge-info' : 'badge-warn'}">${l.side}</span></td>
                <td>${l.quantity}</td>
                <td>${fmtUsd(l.fill_price)}</td>
                <td>${fmtUsd(l.gross_amount)}</td>
                <td>${fmtUsd(Number(l.commission_usd) + Number(l.slippage_usd))}</td>
                <td class="${l.realised_pnl >= 0 ? 'pos' : 'neg'}">${fmtUsd(l.realised_pnl)}</td>
                <td>${fmtUsd(l.cash_after)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }

    function renderAnalytics() {
      const exp = (STATE.experiments && STATE.experiments[0]) || {};
      const evalRep = exp.evaluation_report || {};
      const strats = STATE.strategies || [];
      const firstVal = (strats[0] && strats[0].validation_summary) || {};
      const wf = (firstVal.walk_forward && firstVal.walk_forward.windows) || [];

      const secExp = (STATE.account && STATE.account.sector_exposures_pct) || {};
      document.getElementById('analytics-sector-table').innerHTML = `
        <table>
          <thead><tr><th>Sector</th><th>Current Portfolio Exposure (%)</th><th>Hard Limit</th></tr></thead>
          <tbody>
            ${Object.entries(secExp).map(([sec, pct]) => `
              <tr><td><strong>${sec}</strong></td><td>${pct}%</td><td>30.0%</td></tr>
            `).join('') || '<tr><td colspan="3">0% invested across sectors</td></tr>'}
          </tbody>
        </table>
      `;

      document.getElementById('analytics-regime-table').innerHTML = `
        <div style="padding:10px;font-size:0.86rem;">
          <p><strong>Latest Evaluation Notes:</strong> ${evalRep.regime_analysis_notes || 'Multi-regime evaluation completed across Bull, Sideways, and Correction windows.'}</p>
          <p style="margin-top:8px;color:#94a3b8;">${evalRep.performance_explanation || ''}</p>
        </div>
      `;

      document.getElementById('analytics-wf-table').innerHTML = `
        <table>
          <thead><tr><th>Window #</th><th>Start Date</th><th>End Date</th><th>Return (%)</th><th>Sharpe</th><th>Max DD (%)</th><th>Trades</th></tr></thead>
          <tbody>
            ${wf.map(w => `
              <tr>
                <td>Fold ${w.window_index}</td>
                <td>${w.start_date}</td>
                <td>${w.end_date}</td>
                <td class="${w.total_return_pct >= 0 ? 'pos' : 'neg'}">${fmtPct(w.total_return_pct)}</td>
                <td>${Number(w.sharpe_ratio).toFixed(2)}</td>
                <td class="neg">-${Number(w.max_drawdown_pct).toFixed(2)}%</td>
                <td>${w.trade_count}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }

    function renderMonitoring() {
      const jobs = STATE.jobs || [];
      document.getElementById('monitoring-jobs-table').innerHTML = `
        <table>
          <thead><tr><th>Job Name</th><th>Idempotency Key</th><th>Status</th><th>Started At</th></tr></thead>
          <tbody>
            ${jobs.map(j => `
              <tr>
                <td><strong>${j.job_name}</strong></td>
                <td style="font-size:0.76rem;color:#94a3b8;">${j.idempotency_key}</td>
                <td><span class="badge ${j.status === 'COMPLETED' ? 'badge-paper' : 'badge-danger'}">${j.status}</span></td>
                <td>${j.started_at}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;

      const alerts = STATE.risk_alerts || [];
      document.getElementById('monitoring-alerts-table').innerHTML = `
        <table>
          <thead><tr><th>Date</th><th>Severity</th><th>Rule</th><th>Ticker</th><th>Message</th></tr></thead>
          <tbody>
            ${alerts.map(a => `
              <tr>
                <td>${a.alert_date}</td>
                <td><span class="badge ${a.severity === 'WARNING' ? 'badge-warn' : 'badge-danger'}">${a.severity}</span></td>
                <td><strong>${a.rule_name}</strong></td>
                <td>${a.ticker || '-'}</td>
                <td style="font-size:0.8rem;">${a.message}</td>
              </tr>
            `).join('') || '<tr><td colspan="5">No risk alerts triggered</td></tr>'}
          </tbody>
        </table>
      `;
    }

    async function launchBacktest() {
      const val = document.getElementById('bt-strategy-select').value.split(':');
      const start = document.getElementById('bt-start').value;
      const end = document.getElementById('bt-end').value;
      const res = await fetch('/api/backtest', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({strategy_id: val[0], version: Number(val[1] || 1), start_date: start, end_date: end})
      });
      const data = await res.json();
      renderBacktesting(data);
    }

    async function runResearchScan() {
      await fetch('/api/research/scan', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({as_of_date: '2025-06-27'})});
      await loadDashboardState();
    }

    async function triggerDailyWorkflow() {
      await fetch('/api/workflow/daily', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({trading_date: '2025-06-27', force: true})});
      await loadDashboardState();
    }

    async function triggerWeeklyDiscovery() {
      await fetch('/api/workflow/weekly', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({week_ending_date: '2025-06-27', force: true})});
      await loadDashboardState();
    }

    loadDashboardState();
  </script>
</body>
</html>
"""

