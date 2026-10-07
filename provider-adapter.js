// Sunucu tarafında lisanslı sağlayıcıya bağlanacak tek sınır.
// Anahtarlar tarayıcıya gönderilmez; eksik yapılandırmada demo moduna sessizce düşmez.
export async function fetchQuote(symbol, config = {}) {
  if (!config.baseUrl || !config.apiKey) throw new Error('MARKET_DATA_BASE_URL ve MARKET_DATA_API_KEY yapılandırılmalı.');
  const url = new URL(config.baseUrl); url.searchParams.set('symbol', symbol);
  const response = await fetch(url, { headers: { Authorization: `Bearer ${config.apiKey}` } });
  if (!response.ok) throw new Error(`Veri sağlayıcısı HTTP ${response.status} döndürdü.`);
  const data = await response.json();
  if (!Number.isFinite(Number(data.price)) || !data.asOf) throw new Error('Sağlayıcı yanıtı fiyat veya zaman bilgisi içermiyor.');
  return { symbol, price: Number(data.price), currency: data.currency, asOf: data.asOf, status: data.status || 'delayed', source: config.name || 'configured-provider' };
}
