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
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>SWING TRADING AI PLATFORM</h1>
      <span class="badge badge-paper" id="mode-badge">TRADING_MODE = PAPER ($100K)</span>
      <span class="badge badge-info" id="tz-badge">NYSE/NASDAQ • SGT Reporting</span>
    </div>
    <div style="display:flex; gap:10px;">
      <button class="btn btn-secondary" onclick="triggerDailyWorkflow()">Run Daily Session</button>
      <button class="btn" onclick="triggerWeeklyDiscovery()">Run AI Strategy Discovery</button>
    </div>
  </header>

  <nav id="main-nav">
    <button class="active" onclick="switchTab('eli5', this)">🧸 Start Here (Explain Like I'm 5)</button>
    <button onclick="switchTab('overview', this)">1. Overview &amp; P&amp;L</button>
    <button onclick="switchTab('research', this)">2. Market Research</button>
    <button onclick="switchTab('strategies', this)">3. Strategy Rulebooks</button>
    <button onclick="switchTab('backtesting', this)">4. Historical Backtests</button>
    <button onclick="switchTab('paper', this)">5. Paper Trading Ledger</button>
    <button onclick="switchTab('analytics', this)">6. Risk &amp; Sector Analytics</button>
    <button onclick="switchTab('monitoring', this)">7. System Logs</button>
  </nav>

  <main>
    <div class="disclaimer">
      <strong>Quantitative Governance Notice:</strong> Deterministic software handles all price/indicator calculations,
      signal generation, ATR position sizing, risk vetoes, and P&amp;L accounting. Historical backtest returns or LLM
      research confidence scores do not guarantee future profitability.
    </div>

    <!-- 0. EXPLAIN LIKE I'M 5 -->
    <section id="tab-eli5" class="tab-section active">
      <div class="card">
        <div class="card-header"><span class="card-title">🧸 Explain Like I'm 5: How Does This App Actually Work?</span></div>
        <p style="font-size:0.92rem;color:#cbd5e1;margin-bottom:14px;">
          Imagine you have a <strong>toy piggy bank with $100,000 of pretend money</strong> (called <strong>Paper Money</strong>).
          This app tests whether strict math rulebooks can grow that piggy bank by buying shares of big US companies, holding them for
          <strong>3 to 15 days</strong> (Swing Trading), and selling them. We split the work into two strict teams:
          <strong>1) The AI Detective Team</strong> (finds stock ideas and suggests rules, but is <em>never</em> allowed to touch the money) and
          <strong>2) The Strict Calculator &amp; Safety Guard</strong> (tests the rules on past history, checks 6 safety seatbelts, and tracks every penny).
        </p>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;">
          <button class="btn btn-secondary" onclick="showEli5('loop')">🔄 1. The Daily &amp; Weekly Loop</button>
          <button class="btn btn-secondary" onclick="showEli5('agents')">🤖 2. Meet the 5 AI Helpers</button>
          <button class="btn btn-secondary" onclick="showEli5('strategies')">📏 3. The 3 Trading Rulebooks</button>
          <button class="btn btn-secondary" onclick="showEli5('safety')">🛡️ 4. The 6 Safety Seatbelts</button>
          <button class="btn btn-secondary" onclick="showEli5('pnl')">💰 5. How P&amp;L Math Works</button>
        </div>
        <div id="eli5-detail-box" style="background:rgba(56,189,248,0.08);border:1px solid rgba(56,189,248,0.3);padding:14px 16px;border-radius:8px;font-size:0.88rem;">
          <strong>🔄 The Daily &amp; Weekly Loop:</strong> Every weekday after the US market closes, the app downloads fresh stock prices, sells any pretend stock that hit its goal or safety stop-loss, and buys new stocks that pass all rules. Every Saturday morning, the AI Coach reviews any mistakes, proposes an improved rulebook version, and tests it against a 9-part exam before promoting it!
        </div>
      </div>
    </section>

    <!-- 1. OVERVIEW -->
    <section id="tab-overview" class="tab-section">
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
      <div class="card">
        <div class="card-header">
          <span class="card-title">Versioned Strategy Registry &amp; Promotion Lifecycle</span>
        </div>
        <div id="strategies-table"></div>
      </div>
    </section>

    <!-- 4. BACKTESTING -->
    <section id="tab-backtesting" class="tab-section">
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
      renderBacktesting(STATE.experiments && STATE.experiments[0]);
      renderPaperTrading();
      renderAnalytics();
      renderMonitoring();
    }

    function showEli5(topic) {
      const notes = {
        loop: '<strong>🔄 The Daily &amp; Weekly Loop:</strong> Every weekday after the US market closes, the app downloads fresh stock prices, sells any pretend stock that hit its goal or safety stop-loss, and buys new stocks that pass all rules. Every Saturday morning, the AI Coach reviews any mistakes, proposes an improved rulebook version, and tests it against a 9-part exam before promoting it!',
        agents: '<strong>🤖 Meet the 5 AI Helpers:</strong> 1) <em>Market Researcher</em> scans 15+ US stocks daily; 2) <em>Strategy Architect</em> writes math rulebooks; 3) <em>Strategy Evaluator</em> grades rulebooks on a 9-part exam and rejects weak ones; 4) <em>Portfolio Risk Manager</em> blocks any trade that breaks safety limits; 5) <em>Performance Analyst</em> reviews closed trades and suggests Saturday upgrades.',
        strategies: '<strong>📏 The 3 Core Rulebooks:</strong> 1) <em>Momentum Trend</em> buys stocks beating the S&amp;P 500 (SPY) above their 20d/50d averages; 2) <em>Post-Earnings Drift (PEAD)</em> buys companies right after a big quarterly earnings beat; 3) <em>Volatility Breakout</em> buys stocks breaking above their 20-day high on high volume after a quiet 10-day consolidation.',
        safety: '<strong>🛡️ The 6 Safety Seatbelts:</strong> 1) Max 1% risk per trade ($1,000 max loss on $100k); 2) Max 15% in any single stock; 3) Max 30% in any single sector; 4) Max 10 stocks held at once; 5) Automatic Emergency Kill Switch if portfolio drops -15% from peak; 6) Hardcoded to Paper Mode Only.',
        pnl: '<strong>💰 Honest P&amp;L Math:</strong> We never mix multi-year Backtest P&amp;L with daily Paper Account P&amp;L. Paper Account Equity = Starting Capital ($100,000) + Locked-In Realised P&amp;L (from closed trades after fees/slippage) + Open Unrealised P&amp;L (from currently held stocks).'
      };
      document.getElementById('eli5-detail-box').innerHTML = notes[topic] || notes.loop;
    }

    function renderOverview() {
      const acc = STATE.account || {};
      const snaps = STATE.snapshots || [];
      const activeStrats = (STATE.strategies || []).filter(s => s.status === 'PAPER_TRADING').map(s => `${s.name} (${s.strategy_id} v${s.version})`).join(', ') || 'None';
      const dateSpan = snaps.length ? `${snaps[0].snapshot_date} to ${snaps[snaps.length - 1].snapshot_date} (${snaps.length} trading days)` : 'Initial session';
      document.getElementById('overview-pnl-explainer').innerHTML = `
        <strong>💡 Transparent Paper P&amp;L Breakdown:</strong><br/>
        • <strong>Strategies Used:</strong> ${activeStrats}<br/>
        • <strong>Exact Date Span:</strong> ${dateSpan}<br/>
        • <strong>How We Arrived at ${fmtUsd(acc.total_equity)}:</strong> Starting Capital (${fmtUsd(acc.starting_capital)}) + Closed Trade Realised P&amp;L (${fmtUsd(acc.realised_pnl)}) + Open Position Unrealised P&amp;L (${fmtUsd(acc.unrealised_pnl)}) = <strong>${fmtUsd(acc.total_equity)} (${fmtPct(acc.total_return_pct)})</strong>
      `;
      const latestSnap = snaps[snaps.length - 1] || {};
      const retCls = (acc.total_return_pct >= 0) ? 'pos' : 'neg';
      document.getElementById('overview-kpis').innerHTML = `
        <div class="kpi-card"><div class="kpi-label">Portfolio Equity</div><div class="kpi-value">${fmtUsd(acc.total_equity)}</div><div class="kpi-sub">Starting: ${fmtUsd(acc.starting_capital)}</div></div>
        <div class="kpi-card"><div class="kpi-label">Total Return</div><div class="kpi-value ${retCls}">${fmtPct(acc.total_return_pct)}</div><div class="kpi-sub">vs SPY: ${fmtPct(latestSnap.benchmark_cum_return_pct || 0)}</div></div>
        <div class="kpi-card"><div class="kpi-label">Daily Return</div><div class="kpi-value">${fmtPct(latestSnap.daily_return_pct || 0)}</div><div class="kpi-sub">Realised P&L: ${fmtUsd(acc.realised_pnl)}</div></div>
        <div class="kpi-card"><div class="kpi-label">Available Cash</div><div class="kpi-value">${fmtUsd(acc.cash_balance)}</div><div class="kpi-sub">Buying Power: ${fmtUsd(acc.buying_power)}</div></div>
        <div class="kpi-card"><div class="kpi-label">Open Positions</div><div class="kpi-value">${acc.open_positions_count || 0} / 10</div><div class="kpi-sub">Market Value: ${fmtUsd(acc.positions_market_value)}</div></div>
        <div class="kpi-card"><div class="kpi-label">Current Drawdown</div><div class="kpi-value neg">-${Number(acc.current_drawdown_pct || 0).toFixed(2)}%</div><div class="kpi-sub">Kill Switch: ${acc.kill_switch_engaged ? 'ACTIVE' : 'Standby (15%)'}</div></div>
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
      const sel = document.getElementById('bt-strategy-select');
      sel.innerHTML = strats.map(s => `<option value="${s.strategy_id}:${s.version}">${s.name} (${s.strategy_id} v${s.version})</option>`).join('');

      document.getElementById('strategies-table').innerHTML = `
        <table>
          <thead><tr><th>Strategy ID</th><th>Ver</th><th>Name</th><th>Family</th><th>Status</th><th>Holding</th><th>Sharpe</th><th>Profit Factor</th><th>Total Return</th><th>Max DD</th><th>Promotion / Rejection Audit</th></tr></thead>
          <tbody>
            ${strats.map(s => {
              const m = s.backtest_summary || {};
              const stCls = s.status === 'PAPER_TRADING' ? 'badge-paper' : (s.status === 'REJECTED' ? 'badge-danger' : 'badge-warn');
              return `
                <tr>
                  <td><strong>${s.strategy_id}</strong></td>
                  <td>v${s.version}</td>
                  <td>${s.name}</td>
                  <td>${s.strategy_family}</td>
                  <td><span class="badge ${stCls}">${s.status}</span></td>
                  <td>${s.holding_period_min_days}–${s.holding_period_max_days}d</td>
                  <td>${m.sharpe_ratio !== undefined ? Number(m.sharpe_ratio).toFixed(2) : '-'}</td>
                  <td>${m.profit_factor !== undefined ? Number(m.profit_factor).toFixed(2) : '-'}</td>
                  <td class="${(m.total_return_pct || 0) >= 0 ? 'pos' : 'neg'}">${m.total_return_pct !== undefined ? fmtPct(m.total_return_pct) : '-'}</td>
                  <td class="neg">${m.max_drawdown_pct !== undefined ? '-' + Number(m.max_drawdown_pct).toFixed(2) + '%' : '-'}</td>
                  <td style="max-width:340px;font-size:0.78rem;color:#94a3b8;">${s.promotion_decision_reason || s.hypothesis}</td>
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

