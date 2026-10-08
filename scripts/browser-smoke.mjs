import http from 'node:http';
import { spawn } from 'node:child_process';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import assert from 'node:assert/strict';
const executable = process.env.CHROME_BIN || ['/usr/bin/google-chrome', '/opt/google/chrome/chrome', '/usr/bin/chromium'].find(existsSync);
if (!executable) throw new Error('Chrome bulunamadı; CHROME_BIN ayarlayın.');
const date = new Date().toISOString();
const item = (symbol, price) => ({ symbol, name: symbol, market: 'BIST', price, currency: 'TRY', as_of: date, screen_score: 80, change_pct: 1, volume: 1000000 });
const market = { provider: 'BIST Data Service + Twelve Data EOD', generated_at: date, markets: { BIST: { delayed: true, row_count: 2, items: [item('THYAO', 100), item('ASELS', 200)] }, US: { items: [], row_count: 0 } }, errors: [] };
const accountModule = `export const auth = {}; export function onAuthStateChanged(auth, fn) { fn(null); } export async function signInWithEmailAndPassword() {} export async function createUserWithEmailAndPassword() {} export async function signOut() {} export async function getDoc() { return { exists: () => false }; } export async function setDoc() {} export const profileRef = uid => uid;`;
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/api/market') { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(market)); return; }
  if (url.pathname === '/api/kap') {
    const symbol = url.searchParams.get('symbol');
    if (symbol === 'THYAO') await new Promise(resolve => setTimeout(resolve, 400));
    res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ items: [{ title: symbol + ' raporu', url: 'https://www.kap.org.tr/tr/', date }] })); return;
  }
  if (url.pathname === '/firebase-client.js') { res.setHeader('Content-Type', 'text/javascript'); res.end(accountModule); return; }
  const file = url.pathname === '/' ? 'index.html' : url.pathname.slice(1);
  if (!['index.html', 'propicks.js', 'propicks.css', 'account.css', 'ui-data.js', 'alerts.js'].includes(file)) { res.writeHead(404); res.end(); return; }
  res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html');
  res.end(await readFile(file));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const profile = await mkdtemp(join(tmpdir(), 'piyasalens-chrome-'));
const chrome = spawn(executable, ['--headless', '--no-sandbox', '--disable-dev-shm-usage', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
let socket, closeBrowser;
try {
  const port = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Chrome başlangıç süresi aşıldı.')), 15000);
    chrome.stderr.on('data', chunk => { const match = String(chunk).match(/DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)/); if (match) { clearTimeout(timer); resolve(match[1]); } });
    chrome.on('exit', code => { clearTimeout(timer); reject(new Error(`Chrome çıktı: ${code}`)); });
  });
  const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(pages.find(page => page.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }); });
  const pending = new Map(); let id = 0;
  socket.addEventListener('message', event => { const message = JSON.parse(event.data); if (message.id && pending.has(message.id)) { const [resolve, reject, timer] = pending.get(message.id); clearTimeout(timer); pending.delete(message.id); message.error ? reject(new Error(message.error.message)) : resolve(message.result); } });
  function call(method, params = {}) { return new Promise((resolve, reject) => { const key = ++id; const timer = setTimeout(() => { pending.delete(key); reject(new Error(method + ' timeout')); }, 15000); pending.set(key, [resolve, reject, timer]); socket.send(JSON.stringify({ id: key, method, params })); }); }
  closeBrowser = () => call('Browser.close');
  async function evaluate(expression) { const result = await call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (result.exceptionDetails) throw new Error(result.exceptionDetails.text + ': ' + result.exceptionDetails.exception?.description); return result.result.value; }
  await call('Page.enable');
  await call('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/` });
  const waitFor = expression => evaluate(`new Promise((resolve,reject)=>{const until=Date.now()+5000;const check=()=>{if(${expression}) resolve(true);else if(Date.now()>until)reject(new Error('UI bekleme süresi aşıldı'));else setTimeout(check,25)};check()})`);
  await waitFor("document.querySelectorAll('#screenerBody tr[data-symbol]').length === 2");
  await evaluate(`document.querySelector('[data-symbol="THYAO"]').click()`);
  await evaluate('new Promise(resolve=>setTimeout(resolve,50))');
  await evaluate(`document.querySelector('[data-symbol="ASELS"]').click()`);
  await waitFor("document.getElementById('sourceLinks').textContent.includes('ASELS raporu')");
  await evaluate('new Promise(resolve=>setTimeout(resolve,500))');
  assert.match(await evaluate("document.getElementById('sourceLinks').textContent"), /ASELS raporu/);
  await evaluate(`document.getElementById('alertReturn').value='5';document.getElementById('saveAlert').click()`);
  assert.equal(await evaluate("JSON.parse(localStorage.getItem('trader-alerts')).ASELS.referencePrice"), 200);
  await evaluate("document.getElementById('removeAlert').click()");
  assert.equal(await evaluate("Object.keys(JSON.parse(localStorage.getItem('trader-alerts'))).length"), 0);
  await evaluate("document.getElementById('watchlistToggle').click();document.getElementById('clearWatchlist').click()");
  assert.equal(await evaluate("JSON.parse(localStorage.getItem('trader-watchlist')).length"), 0);
  await evaluate(`window.Notification = class { static permission='granted'; constructor(title) { (window.__notifications ||= []).push(title); } };document.getElementById('alertPrice').value='200';document.getElementById('alertReturn').value='0';document.getElementById('saveAlert').click();document.querySelector('[data-symbol="THYAO"]').click();document.getElementById('alertPrice').value='100';document.getElementById('alertReturn').value='0';document.getElementById('saveAlert').click();document.querySelector('[data-symbol="ASELS"]').click()`);
  assert.equal(await evaluate('window.__notifications.length'), 2, 'Semboller arasında geçiş aynı alarmı tekrar bildirmemeli.');
  await evaluate("document.getElementById('accountButton').click();document.getElementById('accountPassword').value='test-password';document.getElementById('accountDialog').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))");
  assert.equal(await evaluate("document.getElementById('accountDialog').hidden && document.getElementById('accountPassword').value === '' && document.activeElement.id === 'accountButton'"), true);
  await call('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true, 'Mobil görünüm yatay taşmamalı.');
  console.log('Tarayıcı kontrolleri geçti: veri yükleme, hızlı seçim/kaynak yarışı, alarm kaydetme/kaldırma, takip temizleme, bildirim tekrar denetimi, hesap penceresi ve mobil taşma.');
} finally {
  if (chrome.exitCode == null) {
    const exit = new Promise(resolve => chrome.once('exit', resolve));
    const timer = setTimeout(() => chrome.kill('SIGKILL'), 3000);
    if (closeBrowser) await closeBrowser().catch(() => {}); else chrome.kill('SIGTERM');
    await exit; clearTimeout(timer);
  }
  socket?.close();
  await new Promise(resolve => server.close(resolve));
  await rm(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
}
