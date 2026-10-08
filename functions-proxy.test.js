import test from 'node:test';
import assert from 'node:assert/strict';
import { proxyRequest } from './functions/index.js';
function response() {
  return { code: 200, headers: {}, status(code) { this.code = code; return this; }, set(key, value) { this.headers[key] = value; return this; }, json(value) { this.body = value; return this; } };
}
test('Firebase proxy never forwards refresh or writes', async t => {
  const fetch = t.mock.method(globalThis, 'fetch');
  for (const req of [{ method: 'POST', path: '/api/refresh' }, { method: 'GET', path: '/api/refresh' }, { method: 'POST', path: '/api/market' }, { method: 'GET', path: '/.env' }]) {
    const res = response(); await proxyRequest(req, res); assert.equal(res.code, 404);
  }
  assert.equal(fetch.mock.calls.length, 0);
});
test('Firebase proxy preserves backend failure and forwards only symbol', async t => {
  const previous = process.env.PIYASALENS_API_URL;
  process.env.PIYASALENS_API_URL = 'https://example.test';
  t.after(() => { if (previous == null) delete process.env.PIYASALENS_API_URL; else process.env.PIYASALENS_API_URL = previous; });
  const fetch = t.mock.method(globalThis, 'fetch', async () => ({ status: 503, json: async () => ({ status: 'unavailable' }) }));
  const res = response(); await proxyRequest({ method: 'GET', path: '/api/kap', query: { symbol: 'THYAO', token: 'private' } }, res);
  assert.equal(res.code, 503); assert.equal(res.body.status, 'unavailable');
  assert.equal(String(fetch.mock.calls[0].arguments[0]), 'https://example.test/api/kap?symbol=THYAO');
});
