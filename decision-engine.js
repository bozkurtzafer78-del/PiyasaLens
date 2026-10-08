export function calculateDecision(input) {
  const missing = reason => ({ newBuy: 'Veri yetersiz', holding: 'Veri yetersiz', reason });
  const numeric = value => value != null && value !== '' && typeof value !== 'boolean' && Number.isFinite(Number(value));
  if (!['price', 'target', 'buyLow', 'buyHigh', 'stop'].every(key => numeric(input[key]))) return missing('Fiyat, hedef, alım bandı veya stop eksik/geçersiz.');
  const price = Number(input.price), target = Number(input.target), low = Number(input.buyLow), high = Number(input.buyHigh), stop = Number(input.stop);
  if (price <= 0 || target <= 0 || low <= 0 || high < low || stop <= 0 || stop >= price) return missing('Fiyat, alım bandı veya stop sıralaması geçersiz.');
  if (input.dataStatus && !['demo', 'real-time', 'delayed', 'end-of-day'].includes(input.dataStatus)) return missing('Veri durumu doğrulanamadı.');
  if (input.dataStatus && input.dataStatus !== 'demo' && !numeric(input.dataAgeHours)) return missing('Veri zamanı eksik.');
  if (input.dataAgeHours != null && (!numeric(input.dataAgeHours) || Number(input.dataAgeHours) < 0 || Number(input.dataAgeHours) > Number(input.maxDataAgeHours ?? 96))) return missing('Veri güncel değil veya zaman geçersiz.');
  const buyCost = Number(input.buyCost ?? 0), sellCost = Number(input.sellCost ?? 0), minRatio = Number(input.minRatio ?? 2);
  if (![buyCost, sellCost, minRatio].every(Number.isFinite) || buyCost < 0 || sellCost < 0 || buyCost >= 100 || sellCost >= 100 || minRatio < 2) return missing('Maliyet veya risk/getiri eşiği geçersiz.');
  const gross = (target / price - 1) * 100;
  const net = (target * (1 - sellCost / 100) / (price * (1 + buyCost / 100)) - 1) * 100;
  const risk = (1 - stop * (1 - sellCost / 100) / (price * (1 + buyCost / 100))) * 100;
  const ratio = Math.max(0, net) / risk;
  const bandMissed = price < low || price > high;
  const reason = [];
  if (bandMissed) reason.push('Fiyat alım bandının dışında.');
  if (net < 5) reason.push('Net potansiyel %5 eşiğinin altında.');
  if (ratio < minRatio) reason.push('Risk/getiri koşulu sağlanmıyor.');
  if (input.thesis === 'broken') reason.push('Yatırım tezi kırılmış.');
  const eligible = net >= 5 && !bandMissed && ratio >= minRatio && input.thesis !== 'broken';
  if (eligible) reason.push('Net potansiyel ve risk/getiri koşulu sağlanıyor.');
  return { newBuy: eligible ? 'Al' : 'Bekle / İzle', holding: input.thesis === 'broken' ? 'Azalt / Sat' : 'Tut',
    gross, net, risk, ratio, costs: buyCost + sellCost, bandMissed, reason: reason.join(' ') };
}
