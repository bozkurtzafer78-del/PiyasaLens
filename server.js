import http from 'node:http';
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { URL } from 'node:url';
import { readCloudMarket, persistMarketSnapshot } from './snapshot-store.js';
import { cert, getApps, initializeApp } from 'firebase-admin/app';
import { getFirestore } from 'firebase-admin/firestore';
const root = process.cwd();
process.loadEnvFile && await readFile(join(root, '.env')).then(() => process.loadEnvFile(join(root, '.env'))).catch(() => {});
const port = Number(process.env.PORT || 4173);
const host = process.env.HOST || '0.0.0.0';
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8' };
const kapCache = new Map();
const secCache = new Map();
const kapHeaders = { 'Accept': 'application/json, text/plain, */*', 'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8', 'User-Agent': 'PiyasaLens/1.0' };
const secHeaders = { 'Accept': 'application/json', 'User-Agent': process.env.SEC_USER_AGENT || 'PiyasaLens/1.0 research' };
let firestore = null;
try {
  if (process.env.FIREBASE_SERVICE_ACCOUNT_JSON) {
    const credentials = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT_JSON);
    const app = getApps()[0] || initializeApp({ credential: cert(credentials) });
    firestore = getFirestore(app);
  }
} catch (error) { console.warn(`Firestore sunucu bağlantısı kurulamadı: ${error.message}`); }
let refreshRunning = false;
const providerStatus = () => ({
  bist: { configured: Boolean(process.env.BIST_DATA_SERVICE_URL), mode: 'delayed', endpoint: process.env.BIST_DATA_SERVICE_URL ? 'configured' : 'missing' },
  us: { configured: Boolean(process.env.MARKET_DATA_API_KEY), provider: 'Twelve Data EOD', mode: 'daily-close' },
  ai: { configured: Boolean(process.env.GEMINI_API_KEY), provider: process.env.GEMINI_MODEL || 'configured-model' },
  firestore: { configured: Boolean(firestore), mode: 'server-side persistence' },
});
const kapDate = (date) => new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: '2-digit', month: '2-digit', year: 'numeric' }).format(date);
async function kapRequest(path, options = {}) {
  const response = await fetch(`https://www.kap.org.tr${path}`, { ...options, headers: { ...kapHeaders, ...(options.headers || {}) }, signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error(`KAP HTTP ${response.status}`);
  return response.json();
}
async function getKapDisclosures(symbol) {
  const cached = kapCache.get(symbol);
  if (cached && Date.now() - cached.at < 5 * 60 * 1000) return cached.value;
  const search = await kapRequest('/tr/api/search/combined', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Origin': 'https://www.kap.org.tr', 'Referer': 'https://www.kap.org.tr/tr/' }, body: JSON.stringify({ keyword: symbol, memberTypeCode: 'BIST' }) });
  const companies = (search || []).find((group) => group.category === 'companyOrFunds')?.results || [];
  const company = companies.find((item) => String(item.cmpOrFundCode || '').toUpperCase() === symbol);
  const companyName = company?.searchValue || '';
  const today = new Date();
  const from = new Date(today.getTime() - 48 * 60 * 60 * 1000);
  const rows = await kapRequest('/tr/api/disclosure/list/main', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Origin': 'https://www.kap.org.tr', 'Referer': 'https://www.kap.org.tr/tr/' }, body: JSON.stringify({ fromDate: kapDate(from), toDate: kapDate(today), disclosureTypes: null, memberTypes: ['IGS', 'DDK'], mkkMemberOid: company?.memberOrFundOid || null }) });
  const items = (Array.isArray(rows) ? rows : []).map((item) => item.disclosureBasic || item).filter((item) => {
    const codes = String(item.stockCode || item.relatedStocks || '').toUpperCase();
    const title = String(item.companyTitle || item.title || '').toUpperCase();
    return codes.includes(symbol) || (companyName && title.includes(companyName.toUpperCase()));
  }).slice(0, 6).map((item) => ({ index: item.disclosureIndex, title: item.title || item.subject || 'KAP bildirimi', summary: item.summary || '', date: item.publishDate || '', url: item.disclosureIndex ? `https://www.kap.org.tr/tr/Bildirim/${item.disclosureIndex}` : 'https://www.kap.org.tr/tr/' }));
  const value = { status: 'ok', symbol, companyName, items, fetchedAt: new Date().toISOString() };
  kapCache.set(symbol, { at: Date.now(), value });
  return value;
}
async function secRequest(url) {
  const response = await fetch(url, { headers: secHeaders, signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error(`SEC HTTP ${response.status}`);
  return response.json();
}
async function getSecFilings(symbol) {
  const cached = secCache.get(symbol);
  if (cached && Date.now() - cached.at < 60 * 60 * 1000) return cached.value;
  const tickerMap = await secRequest('https://www.sec.gov/files/company_tickers.json');
  const match = Object.values(tickerMap).find((item) => String(item.ticker || '').toUpperCase() === symbol);
  if (!match) return { status: 'ok', symbol, companyName: '', items: [], fetchedAt: new Date().toISOString() };
  const cik = String(match.cik_str).padStart(10, '0');
  const submissions = await secRequest(`https://data.sec.gov/submissions/CIK${cik}.json`);
  const recent = submissions.filings?.recent || {};
  const allowed = new Set(['10-K', '10-Q', '8-K', '20-F', '6-K', '424B2']);
  const items = (recent.form || []).map((form, index) => ({ form, index })).filter(({ form }) => allowed.has(form)).slice(0, 6).map(({ form, index }) => {
    const accession = recent.accessionNumber[index];
    const accessionPath = accession.replaceAll('-', '');
    const document = recent.primaryDocument[index];
    return { form, title: recent.primaryDocDescription?.[index] || `${form} bildirimi`, date: recent.filingDate[index], url: `https://www.sec.gov/Archives/edgar/data/${Number(match.cik_str)}/${accessionPath}/${document}` };
  });
  const value = { status: 'ok', symbol, companyName: submissions.name || match.title || '', items, fetchedAt: new Date().toISOString() };
  secCache.set(symbol, { at: Date.now(), value });
  return value;
}
async function readMarketFile() {
  const data = JSON.parse(await readFile(join(root, 'data/latest_market.json'), 'utf-8'));
  if (!data.provider || !Object.keys(data.markets || {}).length || /tradingview/i.test(JSON.stringify(data))) throw new Error('Eski/uygunsuz veri kaynağı reddedildi; yeni veri görevi bekleniyor.');
  return data;
}
function runRefresh() {
  return new Promise((resolve, reject) => {
    const child = spawn('python3', ['-u', 'collect_and_analyze.py', '--market', 'all', '--analyze'], { cwd: root, env: process.env });
    let output = '';
    const timeout = setTimeout(() => child.kill('SIGKILL'), 850000);
    child.stdout.on('data', (chunk) => { output = (output + chunk).slice(-20000); process.stdout.write(`[pipeline] ${chunk}`); });
    child.stderr.on('data', (chunk) => { output = (output + chunk).slice(-20000); process.stderr.write(`[pipeline-error] ${chunk}`); });
    child.on('error', error => { clearTimeout(timeout); reject(error); });
    child.on('close', code => { clearTimeout(timeout); code === 0 ? resolve(output) : reject(new Error(output || `Veri görevi ${code} koduyla sonlandı.`)); });
  });
}
const publicFiles = new Set(['index.html', 'propicks.js', 'propicks.css', 'account.css', 'firebase-client.js', 'ui-data.js']);
http.createServer(async (req, res) => {
  const pathname = new URL(req.url || '/', 'http://localhost').pathname;
  const path = pathname === '/' ? 'index.html' : normalize(pathname).replace(/^[/\\]+/, '');
  if (path.startsWith('..')) { res.writeHead(403); res.end('Forbidden'); return; }
  if (pathname === '/api/health') {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ status: 'ok', firestore: Boolean(firestore), refreshRunning, providers: providerStatus() }));
    return;
  }
  if (pathname === '/api/providers') {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify({ generated_at: new Date().toISOString(), providers: providerStatus(), disclaimer: 'Gecikmeli/araştırma verisi; otomatik emir ve kesin yatırım sinyali yoktur.' }));
    return;
  }
  if (pathname === '/api/market') {
    try {
      let data;
      try { data = await readCloudMarket(firestore); } catch (error) { console.warn('Bulut snapshot okunamadı:', error.message); }
      data ||= await readMarketFile();
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(JSON.stringify(data));
    } catch (error) {
      res.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ status: 'unavailable', error: `Günlük piyasa verisi okunamadı: ${error.message}` }));
    }
    return;
  }
  if (pathname === '/api/strategy' || pathname === '/data/latest_strategy.json') {
    try {
      let market;
      try { market = await readCloudMarket(firestore); } catch {}
      market ||= await readMarketFile();
      const strategy = market.gemini || { status: 'unavailable', reason: 'Temel veri veya analiz henüz hazır değil.' };
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(JSON.stringify({ ...strategy, generated_at: market.generated_at }));
    } catch {
      res.writeHead(503, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'unavailable' }));
    }
    return;
  }
  if (pathname === '/api/refresh') {
    if (req.method !== 'POST' || !process.env.REFRESH_TOKEN || req.headers.authorization !== `Bearer ${process.env.REFRESH_TOKEN}`) { res.writeHead(401, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ status: 'error', error: 'Yetkisiz güncelleme isteği.' })); return; }
    if (refreshRunning) { res.writeHead(202, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ status: 'running' })); return; }
    refreshRunning = true;
    try {
      const existing = await readCloudMarket(firestore) || await readMarketFile();
      const day = value => new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Istanbul', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(value));
      if (!existing.errors?.length && day(existing.generated_at) === day(Date.now())) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'cached', generated_at: existing.generated_at })); refreshRunning = false; return;
      }
    } catch {}
    try {
      const output = await runRefresh();
      const data = await readMarketFile();
      const stored = await persistMarketSnapshot(firestore, data);
      res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
      res.end(JSON.stringify({ status: 'ok', stored, generated_at: data.generated_at, output: output.slice(-2000) }));
    } catch (error) { res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ status: 'error', error: error.message })); }
    finally { refreshRunning = false; }
    return;
  }
  if (pathname === '/api/kap') {
    const symbol = new URL(req.url || '/', 'http://localhost').searchParams.get('symbol')?.trim().toUpperCase();
    if (!symbol || !/^[A-Z0-9.]{1,12}$/.test(symbol)) { res.writeHead(400, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ status: 'error', error: 'Geçersiz BIST sembolü.' })); return; }
    try { const data = await getKapDisclosures(symbol); res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(data)); }
    catch (error) { res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ status: 'unavailable', symbol, error: `KAP bağlantısı şu an kullanılamıyor: ${error.message}` })); }
    return;
  }
  if (pathname === '/api/sec') {
    const symbol = new URL(req.url || '/', 'http://localhost').searchParams.get('symbol')?.trim().toUpperCase();
    if (!symbol || !/^[A-Z]{1,6}$/.test(symbol)) { res.writeHead(400, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ status: 'error', error: 'Geçersiz ABD sembolü.' })); return; }
    try { const data = await getSecFilings(symbol); res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(data)); }
    catch (error) { res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify({ status: 'unavailable', symbol, error: `SEC bağlantısı şu an kullanılamıyor: ${error.message}` })); }
    return;
  }
  if (!publicFiles.has(path)) { res.writeHead(404); res.end('Not found'); return; }
  try { const data = await readFile(join(root, path)); res.writeHead(200, { 'Content-Type': types[extname(path)] || 'text/plain', 'Cache-Control': 'no-store, no-cache, must-revalidate' }); res.end(data); }
  catch { res.writeHead(404); res.end('Not found'); }
}).listen(port, host, function () { console.log(`PiyasaLens: http://${host}:${this.address().port}`); });
