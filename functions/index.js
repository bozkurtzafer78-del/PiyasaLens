import { onRequest } from 'firebase-functions/v2/https';
import { defineString } from 'firebase-functions/params';
const apiUrl = defineString('PIYASALENS_API_URL');
const routes = new Set(['/api/health', '/api/providers', '/api/market', '/api/strategy', '/api/kap', '/api/sec']);
export async function proxyRequest(req, res) {
  if (req.method !== 'GET' || !routes.has(req.path)) return res.status(404).json({ error: 'Endpoint bulunamadı.' });
  try {
    const base = new URL(apiUrl.value());
    if (base.protocol !== 'https:') throw new Error('HTTPS backend gerekli.');
    const url = new URL(req.path, base);
    if (req.query.symbol) url.searchParams.set('symbol', String(req.query.symbol));
    const response = await fetch(url, { signal: AbortSignal.timeout(45000) });
    res.set('Cache-Control', 'no-store');
    return res.status(response.status).json(await response.json());
  } catch {
    return res.status(502).json({ error: 'Veri servisine ulaşılamıyor.' });
  }
}
export const api = onRequest({ region: 'us-central1', timeoutSeconds: 60 }, proxyRequest);
