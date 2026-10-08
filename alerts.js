const positive = value => value != null && value !== '' && Number.isFinite(Number(value)) && Number(value) > 0;
export function buildAlert(item, priceValue, returnValue, now = new Date().toISOString()) {
  const price = priceValue === '' ? null : Number(priceValue);
  const returnPct = returnValue === '' || Number(returnValue) === 0 ? null : Number(returnValue);
  if ((price != null && !positive(price)) || (returnPct != null && !positive(returnPct))) throw new Error('Hedef fiyat ve minimum getiri pozitif olmalı.');
  if (price == null && returnPct == null) throw new Error('Bir hedef fiyat veya minimum getiri girin.');
  if (!positive(item.price)) throw new Error('Geçerli referans fiyat olmadan alarm kurulamaz.');
  return { price, returnPct, referencePrice: Number(item.price), updatedAt: now };
}
export function evaluateAlert(item, alert) {
  if (!alert || !positive(item?.price)) return { triggered: false, returnPct: null };
  const returnPct = positive(alert.referencePrice) ? (Number(item.price) / Number(alert.referencePrice) - 1) * 100 : null;
  const priceReached = positive(alert.price) && Number(item.price) >= Number(alert.price);
  const returnReached = positive(alert.returnPct) && returnPct != null && returnPct >= Number(alert.returnPct) - 1e-9;
  return { triggered: Boolean(priceReached || returnReached), returnPct };
}
export function notificationKey(item, owner = 'guest') {
  return `trader-alert-notified:${owner}:${item.market}:${item.symbol}`;
}
