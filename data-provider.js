// Gerçek sağlayıcı entegrasyonu için değiştirilebilir sınır.
export const demoCatalog = [
  { symbol: 'THYAO', name: 'Türk Hava Yolları', exchange: 'BIST', assetType: 'Hisse', sector: 'Ulaştırma', currency: 'TRY', price: 312.4, coverage: 'demo', source: 'https://www.kap.org.tr/tr/sirket-bilgileri/ozet/953-thy-turk-hava-yollari-a-o' },
  { symbol: 'ASELS', name: 'Aselsan', exchange: 'BIST', assetType: 'Hisse', sector: 'Savunma', currency: 'TRY', price: 184.2, coverage: 'unavailable', source: 'https://www.kap.org.tr/' },
  { symbol: 'BIMAS', name: 'BİM Birleşik Mağazalar', exchange: 'BIST', assetType: 'Hisse', sector: 'Perakende', currency: 'TRY', price: 512.1, coverage: 'unavailable', source: 'https://www.kap.org.tr/' },
  { symbol: 'GARAN', name: 'Garanti BBVA', exchange: 'BIST', assetType: 'Hisse', sector: 'Bankacılık', currency: 'TRY', price: 145.3, coverage: 'unavailable', source: 'https://www.kap.org.tr/' },
  { symbol: 'AAPL', name: 'Apple Inc.', exchange: 'NASDAQ', assetType: 'Hisse', sector: 'Teknoloji', currency: 'USD', price: 226.5, coverage: 'unavailable', source: 'https://www.sec.gov/edgar/search/' },
  { symbol: 'MSFT', name: 'Microsoft Corp.', exchange: 'NASDAQ', assetType: 'Hisse', sector: 'Teknoloji', currency: 'USD', price: 510.2, coverage: 'unavailable', source: 'https://www.sec.gov/edgar/search/' },
  { symbol: 'NVDA', name: 'NVIDIA Corp.', exchange: 'NASDAQ', assetType: 'Hisse', sector: 'Yarı iletken', currency: 'USD', price: 188.4, coverage: 'unavailable', source: 'https://www.sec.gov/edgar/search/' },
  { symbol: 'SPY', name: 'SPDR S&P 500 ETF', exchange: 'NYSE Arca', assetType: 'ETF', sector: 'Endeks ETF', currency: 'USD', price: 671.8, coverage: 'unavailable', source: 'https://www.ssga.com/us/en/intermediary/etfs/funds/spdr-sp-500-etf-trust-spy' }
];

export function findInstrument(symbol) {
  return demoCatalog.find(x => x.symbol === String(symbol).trim().toUpperCase()) ?? null;
}

export function getProviderStatus() {
  return { mode: 'demo', lastSuccessfulUpdate: new Date().toISOString(), provider: 'Demo catalog', realTime: false };
}
