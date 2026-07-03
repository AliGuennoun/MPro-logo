/**
 * End-to-end test for MasterAds Pro.
 * Drives the real app in headless Chromium through the full "good Monday morning" workflow:
 * create client → import Meta + Google CSVs → verify metrics/verdicts/combined totals →
 * client report → import leads → pipeline moves → offline message templates →
 * prospection outreach → strategy save → backup export/wipe/restore → AI-guard path.
 *
 * Run:  cd tests && npm install && node e2e.mjs
 */
import { chromium } from 'playwright';
import { fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP = 'file://' + path.resolve(__dirname, '..', 'MasterAds-Pro.html');
const SAMPLES = path.resolve(__dirname, '..', 'sample-data');

let passed = 0, failed = 0;
function ok(cond, name, extra = '') {
  if (cond) { passed++; console.log('  ✅ ' + name); }
  else { failed++; console.log('  ❌ ' + name + (extra ? ' — ' + extra : '')); }
}
function section(t) { console.log('\n▶ ' + t); }

async function launch() {
  try { return await chromium.launch(); }
  catch { return await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' }); }
}

const browser = await launch();
const ctx = await browser.newContext({ acceptDownloads: true });
const page = await ctx.newPage();
page.on('dialog', d => d.accept());
const errors = [];
page.on('pageerror', e => errors.push(String(e)));

await page.goto(APP);
await page.evaluate(() => localStorage.clear());
await page.reload();

/* ---------- 1. Pure-function unit checks ---------- */
section('Unit checks (parsing, formatting, verdicts)');
const u = await page.evaluate(() => {
  const M = window.MAP;
  const v = (c, t) => M.verdictFor(c, t).label;
  return {
    n1: M.parseNum('1,500.00'), n2: M.parseNum('8,000'), n3: M.parseNum('1 234,56'),
    n4: M.parseNum('400.00'), n5: M.parseNum('53,33'),
    m1: M.fmtMoney(4250, 'MAD'), m2: M.fmtMoney(37.5, 'MAD'), m3: M.fmtMoney(1234.5, 'USD'), m4: M.fmtMoney(1234, 'EUR'),
    v1: v({spend:1500,impressions:120000,clicks:2400,results:40}, 50),   // CPL 37.5 → SCALE
    v2: v({spend:800,impressions:40000,clicks:520,results:15}, 50),      // CPL 53.33 → KEEP
    v3: v({spend:950,impressions:30000,clicks:900,results:14}, 50),      // CPL 67.86 → WATCH
    v4: v({spend:600,impressions:90000,clicks:450,results:4}, 50),       // CPL 150 → KILL
    v5: v({spend:120,impressions:9000,clicks:80,results:0}, 50),         // no results, spend > 2× target → KILL
    v6: v({spend:60,impressions:5000,clicks:40,results:0}, 50),          // no results, low spend → WATCH
    v7: v({spend:100,impressions:1000,clicks:10,results:2}, null),       // no target → SET TARGET
    met: M.metrics({spend:1500,impressions:120000,clicks:2400,results:40}),
    plat1: M.detectPlatform(['Campaign name','Amount spent (MAD)','Impressions']),
    plat2: M.detectPlatform(['Campaign','Cost','Impr.','Clicks','Conversions'])
  };
});
ok(u.n1 === 1500, 'parseNum "1,500.00" → 1500', String(u.n1));
ok(u.n2 === 8000, 'parseNum "8,000" → 8000', String(u.n2));
ok(u.n3 === 1234.56, 'parseNum "1 234,56" → 1234.56', String(u.n3));
ok(u.n4 === 400, 'parseNum "400.00" → 400', String(u.n4));
ok(u.n5 === 53.33, 'parseNum "53,33" → 53.33', String(u.n5));
ok(u.m1 === '4 250 MAD', 'fmtMoney MAD thousands', u.m1);
ok(u.m2 === '37,50 MAD', 'fmtMoney MAD decimals', u.m2);
ok(u.m3 === '$1,234.50', 'fmtMoney USD', u.m3);
ok(u.m4 === '1 234 €', 'fmtMoney EUR', u.m4);
ok(u.v1 === 'SCALE' && u.v2 === 'KEEP' && u.v3 === 'WATCH' && u.v4 === 'KILL', 'verdict thresholds SCALE/KEEP/WATCH/KILL', [u.v1,u.v2,u.v3,u.v4].join(','));
ok(u.v5 === 'KILL' && u.v6 === 'WATCH', 'zero-result verdicts', [u.v5,u.v6].join(','));
ok(u.v7 === 'SET TARGET', 'no-target verdict', u.v7);
ok(Math.abs(u.met.cpm - 12.5) < 1e-9 && Math.abs(u.met.ctr - 2) < 1e-9 && Math.abs(u.met.cpl - 37.5) < 1e-9, 'metrics CPM/CTR/CPL math', JSON.stringify(u.met));
ok(u.plat1 === 'meta' && u.plat2 === 'google', 'platform auto-detection', u.plat1 + '/' + u.plat2);

/* ---------- 2. Create a client ---------- */
section('Clients: create with currency + target CPL');
await page.click('[data-view="clients"]');
await page.click('#btnAddClient');
await page.fill('#cName', 'Riad Atlas');
await page.fill('#cCompany', 'Riad Atlas Marrakech');
await page.selectOption('#cCurrency', 'MAD');
await page.fill('#cTarget', '50');
await page.click('#btnSaveClient');
await page.waitForSelector('#clientsTable');
ok(await page.locator('#clientsTable').textContent().then(t => t.includes('Riad Atlas') && t.includes('50 MAD')), 'client saved with target 50 MAD');

/* ---------- 3. Import Meta CSV ---------- */
section('Ads: import Meta CSV export');
await page.click('[data-view="ads"]');
await page.click('#btnImportAds');
await page.setInputFiles('#impFile', path.join(SAMPLES, 'meta-ads-sample.csv'));
await page.waitForSelector('#impPreview table');
ok(await page.locator('#impPreview').textContent().then(t => t.includes('Meta') && t.includes('3')), 'Meta platform + 3 campaigns detected');
await page.click('#btnDoImport');
await page.waitForSelector('.adsTable');

/* ---------- 4. Import Google CSV (with junk header rows + "Total" row) ---------- */
section('Ads: import Google Ads CSV (junk rows + Total row skipped)');
await page.click('#btnImportAds');
await page.setInputFiles('#impFile', path.join(SAMPLES, 'google-ads-sample.csv'));
await page.waitForSelector('#impPreview table');
const gPrev = await page.locator('#impPreview').textContent();
ok(gPrev.includes('Google') && gPrev.includes('2') && !gPrev.includes('Total: Account'), 'Google detected, 2 campaigns, Total row excluded');
await page.click('#btnDoImport');
await page.waitForSelector('.adsTable');

/* ---------- 5. Verify combined table: metrics, verdicts, totals ---------- */
section('Ads: combined Meta+Google table with verdicts');
const rowBroad = page.locator('tr[data-campaign="Broad - Interests Travel"]');
ok(await rowBroad.locator('.badge').textContent() === 'KILL', 'Broad campaign (CPL 150 vs target 50) → KILL');
ok(await page.locator('tr[data-campaign="Leads - Riad Booking - Adv+"] .badge').textContent() === 'SCALE', 'Adv+ campaign (CPL 37,50) → SCALE');
ok(await page.locator('tr[data-campaign="Search - Brand"] .badge').textContent() === 'SCALE', 'Google Brand (CPL 40 = 0.8×target) → SCALE');
ok(await page.locator('tr[data-campaign="Search - Generic Riad Marrakech"] .badge').textContent() === 'WATCH', 'Google Generic (CPL 67,86) → WATCH');
ok(await page.locator('#adsTableCard .b-kill').count() === 1 && await page.locator('#adsTableCard .b-scale').count() === 2, 'verdict badge counts (1 KILL, 2 SCALE)');
const totSpend = (await page.locator('[data-total-spend]').textContent()).trim();
const totCpl = (await page.locator('[data-total-cpl]').textContent()).trim();
ok(totSpend === '4 250 MAD', 'combined total spend = 4 250 MAD', totSpend);
ok(totCpl === '51,20 MAD', 'combined blended CPL = 51,20 MAD (4250/83)', totCpl);
ok(await rowBroad.textContent().then(t => t.includes('Low CTR')), 'diagnostic hint on low-CTR campaign');

/* ---------- 6. Client report (print view) ---------- */
section('Ads: client-ready combined report');
await page.click('#btnReport');
await page.waitForSelector('#reportView.open');
const rep = await page.locator('#reportView').textContent();
ok(rep.includes('Meta Ads') && rep.includes('Google Ads'), 'report has both platform sections');
ok((await page.locator('#repTotalSpend').textContent()).trim() === '4 250 MAD', 'report headline total spend');
ok(rep.includes('MasterAds Pro') && rep.includes('Riad Atlas'), 'report branded + client named');
await page.click('#reportView button.btn2'); // Close
ok(!(await page.locator('#reportView').evaluate(el => el.classList.contains('open'))), 'report closes');

/* ---------- 7. CRM: import leads, pipeline, follow-ups ---------- */
section('CRM: leads import + pipeline');
await page.click('[data-view="crm"]');
await page.click('#btnImportLeads');
await page.selectOption('#limpClient', { index: 1 }); // Riad Atlas
await page.setInputFiles('#limpFile', path.join(SAMPLES, 'leads-sample.csv'));
await page.waitForSelector('#limpPreview table');
ok(await page.locator('#limpPreview').textContent().then(t => t.includes('5')), '5 leads detected in CSV');
await page.click('#btnDoLeadImport');
await page.waitForSelector('.kanban');
ok(await page.locator('.kcol[data-stage="New"] .kcard').count() === 5, '5 leads land in "New" column');
// Move first lead forward
await page.locator('.kcol[data-stage="New"] .kcard').first().locator('button:has-text("▶")').click();
ok(await page.locator('.kcol[data-stage="Contacted"] .kcard').count() === 1, 'lead moved New → Contacted');
// Lead detail + offline follow-up message (no API key set)
await page.locator('.kcol[data-stage="Contacted"] .kcard .nm').first().click();
await page.waitForSelector('#btnMsg');
await page.click('#btnMsg');
await page.waitForSelector('#leadAiOut .ai-out');
const msg = await page.locator('#leadAiOut').textContent();
ok(msg.includes('WhatsApp') && msg.includes('Email'), 'offline follow-up templates generated (WhatsApp + Email)');
await page.click('#modal button:has-text("Close")');

/* ---------- 8. Dashboard KPIs ---------- */
section('Dashboard: KPI tiles reflect the data');
await page.click('[data-view="dashboard"]');
ok((await page.locator('#kpiClients').textContent()).trim() === '1', 'clients KPI = 1');
ok((await page.locator('#kpiLeads').textContent()).trim() === '5', 'leads (7 days) KPI = 5');
ok((await page.locator('#kpiDue').textContent()).trim() === '5', 'follow-ups due KPI = 5 (import sets follow-up to today)');
ok(await page.locator('#kpiSpend').textContent().then(t => t.includes('4 250 MAD')), 'spend KPI shows 4 250 MAD');
ok(await page.locator('#dueList').textContent().then(t => t.includes('Yassine El Amrani')), 'due list names the lead');

/* ---------- 9. Prospection: add prospect + offline outreach ---------- */
section('Prospection: tracker + outreach writer');
await page.click('[data-view="prospection"]');
ok(await page.locator('details.play').count() >= 6, 'playbook has 6+ tactics');
await page.click('#btnAddProspect');
await page.fill('#pName', 'Salma Ouazzani');
await page.fill('#pCompany', 'Kech Furniture');
await page.fill('#pNotes', 'Just started Meta ads, boosted posts only, no CTA.');
await page.click('#btnSaveProspect');
await page.waitForSelector('#prospectsTable');
await page.locator('#prospectsTable button:has-text("Open")').first().click();
await page.click('#btnOutreach');
await page.waitForSelector('#poOut .ai-out');
const outr = await page.locator('#poOut').textContent();
ok(outr.includes('Salma') && outr.includes('LinkedIn'), 'offline outreach references prospect + channel');
await page.click('#modal button:has-text("Close")');

/* ---------- 10. Strategy: save inputs ---------- */
section('Strategy: inputs persist');
await page.click('[data-view="strategy"]');
await page.selectOption('#stratClientSel', { index: 1 });
await page.fill('#sMarket', 'Boutique riad in Marrakech medina, direct bookings, ~1200 MAD/night.');
await page.fill('#sCompetitors', 'Riad Yasmine\nRiad BE');
await page.click('#btnSaveStrat');
await page.waitForSelector('#sMarket');
ok(await page.locator('#sMarket').inputValue().then(v => v.includes('Boutique riad')), 'strategy inputs saved and re-rendered');
ok(await page.locator('a[href*="facebook.com/ads/library"]').count() >= 2, 'competitor Ad Library spy links generated');

/* ---------- 11. Persistence across reload ---------- */
section('Persistence: full reload');
await page.reload();
await page.click('[data-view="dashboard"]');
ok((await page.locator('#kpiClients').textContent()).trim() === '1', 'data survives page reload');

/* ---------- 12. Backup export → wipe → restore ---------- */
section('Backup: export → wipe → restore');
await page.click('[data-view="settings"]');
const [download] = await Promise.all([page.waitForEvent('download'), page.click('#btnExport')]);
const bkPath = path.join(__dirname, 'backup-test.json');
await download.saveAs(bkPath);
const bk = JSON.parse(fs.readFileSync(bkPath, 'utf8'));
ok(bk.clients.length === 1 && bk.leads.length === 5 && bk.campaigns.length === 5, 'backup JSON contains 1 client / 5 campaigns / 5 leads');
await page.click('button:has-text("Erase all data")');
await page.click('[data-view="dashboard"]');
ok((await page.locator('#kpiClients').textContent()).trim() === '0', 'wipe empties the app');
await page.click('[data-view="settings"]');
await page.setInputFiles('#importBackupFile', bkPath);
await page.waitForSelector('#kpiClients');
ok((await page.locator('#kpiClients').textContent()).trim() === '1', 'backup restore brings everything back');
fs.unlinkSync(bkPath);

/* ---------- 13. AI guard: no key → routed to Settings ---------- */
section('AI guard without API key');
await page.click('[data-view="ads"]');
await page.selectOption('#adsClientSel', { index: 1 }); // pick the client → AI + report buttons appear
await page.waitForSelector('#btnAiAds');
await page.click('#btnAiAds');
await page.waitForSelector('#setKey');
ok(await page.locator('h1').textContent().then(t => t.includes('Settings')), 'AI button without key routes to Settings with a hint');

/* ---------- Result ---------- */
ok(errors.length === 0, 'no JavaScript page errors during the whole run', errors.join(' | '));
console.log(`\n${'='.repeat(50)}\nRESULT: ${passed} passed, ${failed} failed\n`);
await browser.close();
process.exit(failed ? 1 : 0);
