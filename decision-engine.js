export function calculateDecision(input) {
  const required = ['price', 'target', 'buyLow', 'buyHigh'];
  if (!required.every(k => Number.isFinite(Number(input[k]))) || input.price <= 0 || input.target <= 0) {
    return { newBuy: 'Veri yetersiz', holding: 'Veri yetersiz', reason: 'Fiyat, hedef veya alım bandı eksik/geçersiz.' };
  }
  if (input.dataStatus && input.dataStatus !== 'demo' && input.dataStatus !== 'real-time' && input.dataStatus !== 'delayed' && input.dataStatus !== 'end-of-day') {
    return { newBuy: 'Veri yetersiz', holding: 'Veri yetersiz', reason: 'Veri durumu doğrulanamadı.' };
  }
  if (Number.isFinite(Number(input.dataAgeHours)) && Number(input.dataAgeHours) > Number(input.maxDataAgeHours ?? 24)) {
    return { newBuy: 'Veri yetersiz', holding: 'Veri yetersiz', reason: `Veri güncel değil: ${input.dataAgeHours} saat önce güncellendi.` };
  }
  const costs = Math.max(0, Number(input.buyCost || 0)) + Math.max(0, Number(input.sellCost || 0));
  const gross = (input.target / input.price - 1) * 100;
  const net = (((input.target * (1 - Number(input.sellCost || 0) / 100)) / (input.price * (1 + Number(input.buyCost || 0) / 100))) - 1) * 100;
  const risk = Math.max(0, (input.price - Number(input.stop || input.price * .9)) / input.price * 100);
  const ratio = risk > 0 ? Math.max(0, net) / risk : null;
  const bandMissed = input.price > input.buyHigh;
  let newBuy = 'Bekle / İzle';
  let reason = [];
  if (bandMissed) reason.push('Fiyat alım bandının üstünde; yeni giriş koşulu beklenmeli.');
  if (net < 5) reason.push(`Net potansiyel %${net.toFixed(2)} ile %5 eşiğinin altında.`);
  if (net >= 5 && !bandMissed && (ratio === null || ratio >= Number(input.minRatio || 2))) {
    newBuy = 'Al'; reason.push('Net potansiyel ve yapılandırılmış risk/getiri koşulu sağlanıyor.');
  } else if (!reason.length) reason.push('Tek başına %5 eşiği alım için yeterli değil; ek kanıt beklenmeli.');
  const holding = input.thesis === 'broken' ? 'Azalt / Sat' : 'Tut';
  return { newBuy, holding, gross, net, risk, ratio, costs, bandMissed, reason: reason.join(' ') };
}
