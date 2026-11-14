---
name: minimalist-ui-design
description: >-
  Use this skill whenever designing, building, refactoring, or modifying any UI,
  dashboard, web page, frontend component, table, log viewer, or Streamlit/HTML
  interface. Enforces the user's preferred Minimalist Matte-Dark (Linear / Apple
  Stocks) aesthetic, zero-emoji restraint, plain-English beginner clarity,
  shallow navigation without sidebars or admin clutter, and focused single-day
  chronological journals.
---

# Minimalist UI & Beginner-First Financial Design Skill

Activate and follow this skill **whenever** you create, redesign, or modify any user interface, dashboard (`dashboard/streamlit_app.py`, `dashboard/ui_template.py`), table, journal, or visual component.

---

## 1. Collaboration & Interview-First Workflow

1. **Ask Before Guessing on Layout Trade-Offs**:
   - Whenever a UI request or organization improvement has multiple reasonable layout directions, use `ask_question` with concise multiple-choice options (putting the recommended option first with `(Recommended)`) to confirm what the user likes before writing UI code.
2. **Design for Calm Readability**:
   - Every screen should feel effortless for a beginner to scan in 5 seconds while remaining institutional and trustworthy for daily financial monitoring.

---

## 2. Visual Aesthetic & Color Tokens (Linear / Apple Stocks Matte-Dark)

Use a restrained, matte-dark surface hierarchy with crisp typography and tabular numbers:

- **Canvas & Surfaces**:
  - App background canvas: `#0c0e12`
  - Elevated card surface: `#13161c`
  - Subtle nested / hover surface: `#181c24`
  - Card border: `1px solid rgba(255, 255, 255, 0.07)`
  - Border radius: `10px` on primary cards, `6px–8px` on compact inline rows
  - Centered container: `max-width: 1140px` with generous vertical and horizontal whitespace
- **Typography & Numerals**:
  - Primary text / figures: `#f8fafc` or `#f1f5f9`
  - Secondary body text: `#cbd5e1` or `#94a3b8`
  - Muted labels / captions / column headers: `#64748b` or `#8b95a5` (uppercase micro-labels `0.70rem–0.74rem` with subtle `0.04em` tracking)
  - Always apply `font-variant-numeric: tabular-nums` to prices, share counts, percentages, P&L figures, and timestamps so columns align cleanly.
- **Strict Color & Decoration Restraint**:
  - **Semantic Green (`#22c55e`) & Red (`#ef4444`) ONLY for Financial Outcomes**: Reserve green and red strictly for positive/negative P&L, return percentages, or directional profit/loss indicators. Keep structural borders, headers, and account containers neutral.
  - **Zero Emojis**: Never use emojis (`🟢`, `🚀`, `📊`, `⚠️`, etc.) anywhere in headers, tabs, buttons, status labels, or tables. If a status dot is needed, use a tiny `6px–7px` CSS circle.
  - **No Loud Visual Noise**: Never use neon borders, gradients, loud multi-colored pill badges, or complex candlestick/SVG charts when clean numbers + a 1-sentence plain-English summary communicate the state faster.

---

## 3. Layout, Navigation & Zero Admin Clutter

1. **No Left Sidebar**:
   - Collapse and hide sidebars (`initial_sidebar_state="collapsed"` in Streamlit). Place title, subtle connection status, and essential external links in a clean full-width top header.
2. **Shallow Tab Hierarchy (2–3 Tabs Max)**:
   - Group related information into at most **2–3 top-level tabs** (e.g., `Overview & Open Trades`, `Daily Journal`, `Performance & System`) rather than sprawling 6–8 tab menus.
3. **Omit Redundant Manual Controls & Developer Clutter**:
   - Do **not** add manual "Sync" buttons when background schedules already automate syncing.
   - Do **not** expose capital/risk sizing sliders, manual ticker onboarding forms, emergency reset buttons, raw JSON dumps, or dense rule cheat-sheets in the primary monitoring UI.

---

## 4. Beginner-Friendly Plain English (Zero Quant Jargon)

1. **Lead With Exact Financial Numbers**:
   - Make core figures immediately scannable: **Shares**, **Dollar Value (`$`)**, **Entry / Limit Price (`$`)**, **Current Price (`$`)**, **Unrealized / Realized P&L (`$` and `%`)**, **Auto Stop-Loss (`$` and `$ max loss` or `$ locked gain`)**, **Profit Target (`$` and `$ target gain`)**, **Breakeven Trigger (`$`)**, and **Holding Duration (`Day N`)**.
2. **Translate Technical & Broker Codes into Everyday English**:
   - Never expose raw indicator formulas or internal broker enums (`RSI(2)=4.1`, `SMA50>SMA200`, `LowerBB`, `RS20d`, `1.65R`, `R-multiple`, `OCO`, `PEAD`, `SQN`, `QUEUED_ON_ALPACA`) without translating them into **one short, plain-English sentence** explaining *why* the trade was placed and *how* its automatic exit orders protect it.
   - Use intuitive order labels in tables: e.g., `Entry (Buy)`, `Entry (Short)`, `Auto Exit (Sell)`, `Auto Exit (Buy to Cover)`, `Working at Broker`, `Filled`.
3. **Local Timezone Clarity (`SGT`)**:
   - Display every order, fill, and workflow run timestamp in **Singapore Time (`SGT`, `UTC+8`)** in a clear human-readable format (e.g., `Nov 13, 18:10 SGT`) and label columns explicitly (`Date / Time (SGT)`).

---

## 5. Logs, Tables & Chronological Journals

When displaying historical logs, order ledgers, or daily journals:

1. **Single-Day Focused View (No Endless Multi-Day Scrolling)**:
   - Default to showing **one day at a time** (latest active day first) with `← Previous` / `Next →` navigation buttons and a date dropdown that previews each day's activity count (e.g., `Fri, Nov 13 · 7 orders · Latest`).
2. **1-Sentence `Daily Takeaway` Banner**:
   - Start each day's view with one calm, plain-English sentence summarizing what happened and why (e.g., *"Placed 7 new entry orders across 2 accounts and continued holding 11 open positions; no existing stop-losses needed adjustment today."*).
3. **Unified Activity-First Grouping**:
   - Organize chronologically/by action across accounts rather than repeating separate per-account boxes (especially when an account had zero activity):
     1. **`New Orders & Fills`** (tagged inline with the account name)
     2. **`Stop-Loss Adjustments`** (render **only** when adjustments > 0; hide completely when 0)
     3. **`Positions Held`** (render as **one compact clean table**, not tall multi-line cards)
4. **Quiet Deduplicated Footers & Relevant Data Only**:
   - Combine skipped/untriggered items into **one single collapsed expander** at the bottom of the page, deduplicated by symbol.
   - Sort order and run logs **newest-first**, always include `Date / Time (SGT)`, and hide pre-link/simulated test rows whenever live connected account history exists.

---

## 6. Pre-Ship UI Verification Checklist

Before finishing any UI change, verify:
- [ ] **Zero emojis** anywhere in the rendered UI or strings.
- [ ] **Green/red color restraint**: only P&L / return figures use green or red; cards and borders remain neutral matte dark (`#0c0e12` / `#13161c`).
- [ ] **Plain-English check**: no raw `R-multiple`, `OCO`, `RSI/SMA/ATR` code strings, or internal status enums leak onto the screen untranslated.
- [ ] **Timestamp check**: every order log and run table displays `Date / Time (SGT)` sorted newest-first.
- [ ] **Python 3.11 compatibility** (for Python/Streamlit UIs): no backslashes or escaped quotes inside `{...}` f-string expressions (`SyntaxError` in Python 3.11); pre-compute sub-strings in local variables before interpolating, and run headless verification (`verify_context.py`).

