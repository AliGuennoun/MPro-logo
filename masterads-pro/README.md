# MasterAds Pro — Cockpit

A single-file local app for a digital marketer / media buyer: ads performance analysis
(Meta + Google combined), a client CRM pipeline, strategic planning, and prospection —
with optional AI assistance through your own Anthropic API key.

**Everything runs in your browser. Your data never leaves your machine** (except the
specific text of an AI request when you use an AI button, sent directly to Anthropic).

## Quick start

1. Download `MasterAds-Pro.html`.
2. Double-click it — it opens in your browser. That's it. No installation, no server.
3. On the Dashboard, click **Load sample data** to explore, then erase it in **Settings**.
4. Add your real clients in **Clients** (set each client's currency and target CPA/CPL —
   this powers the verdicts).

> Tip: bookmark the file, and always open it in the **same browser** — data is stored in
> that browser's local storage. Export a JSON backup from **Settings** regularly.

## The weekly workflow

| Task | Where | How |
|---|---|---|
| Ads analysis | **Ads Analysis** | Export CSV from Meta Ads Manager (Campaigns → Export) and Google Ads (Download → CSV), import both. You get CPM / CTR / CPC / CPA-CPL per campaign, SCALE / KEEP / WATCH / KILL verdicts vs. your target, diagnostics hints, and combined Meta+Google totals. |
| Client report | **Ads Analysis → Client report** | Branded, printable combined report — use *Print → Save as PDF*. |
| Lead management | **CRM Pipeline** | Import leads from Google Sheets/Meta exports (CSV), duplicates auto-skipped, follow-up auto-set to today. Move leads across New → Contacted → Qualified → Proposal → Won/Lost. Hot/Warm/Cold scoring built in. |
| Strategy | **Strategy** | Fill market / personas / pains / competitors (with one-click Meta Ad Library spy links), then generate an AI media plan with budget allocation. |
| Prospection | **Prospection** | Prospect tracker with next-action dates + an outreach writer (LinkedIn DM, cold email, follow-up) + a playbook of 7 client-acquisition tactics, including Ad Library sniping. |
| Morning check | **Dashboard** | Follow-ups due, prospection actions due, spend and lead KPIs. |

## AI features (optional)

Paste an Anthropic API key in **Settings** (get one at platform.claude.com — it's stored
only in your browser). This unlocks:

- **AI analysis** of a client's ad account (cross-platform budget recommendations),
  included in the client report.
- **Strategy & media plan generation** from your strategic inputs.
- **AI lead qualification** and personalized follow-up messages.
- **Personalized outreach** for prospects (DM + email + follow-up).

Without a key, everything still works: verdicts are rule-based and messages use smart
templates. Default model: Claude Opus 4.8 (switchable to Sonnet 5 / Haiku 4.5 in Settings
to lower cost). Typical AI call cost: a few cents.

## Data & backups

- Stored in browser local storage under the key `masterads_pro_v1`.
- **Settings → Export backup** downloads everything as one JSON file; **Import backup** restores it.
- Moving to a new computer/browser = export on the old one, import on the new one.
- **Leads → Export CSV** for use in Sheets or elsewhere.

## Known limits (v1) and upgrade path

- **No live Meta/Google API connection.** Both require an approved developer app + OAuth
  server, which can't live inside a local HTML file. V1 uses their CSV exports (~30s per
  platform). The natural v2 is a small local/hosted server doing OAuth to the Marketing
  API / Google Ads API and auto-syncing — the app's data model is already shaped for it.
- **Data is per-browser.** Reselling to clients = give each client the HTML file (rename
  the brand in Settings — it's white-label ready), or move to a hosted multi-user version.
- Report "PDF" is via the browser's Print → Save as PDF.

## Tests

Full end-to-end suite (48 checks) drives the real app in headless Chromium:
client creation, Meta + Google CSV imports (incl. junk rows and Total-row skipping),
metric math, verdict thresholds, combined totals, report generation, lead import and
pipeline moves, offline templates, persistence, and backup export/wipe/restore.

```bash
cd tests
npm install
node e2e.mjs
```
