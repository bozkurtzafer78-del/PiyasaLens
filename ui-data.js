export function marketPulse(items) {
  const changes = items.map(item => item.change_pct).filter(value => value != null && value !== '' && Number.isFinite(Number(value))).map(Number);
  return { count: items.length,
    average: changes.length ? changes.reduce((sum, value) => sum + value, 0) / changes.length : null,
    positive: changes.length ? changes.filter(value => value > 0).length / changes.length * 100 : null };
}
export function validStrategy(strategy, market) {
  return strategy?.status === 'ok' && typeof strategy.generated_at === 'string' && Number.isFinite(Date.parse(strategy.generated_at)) && strategy.generated_at === market?.generated_at ? strategy : null;
}

export function dataAgeHours(data, now = Date.now()) {
  const items = Object.values(data?.markets || {}).flatMap(market => market.items || []);
  if (!items.length) return Infinity;
  const dates = items.map(item => item.as_of ? Date.parse(item.as_of) : NaN);
  if (dates.some(date => !Number.isFinite(date) || date > now + 300000)) return Infinity;
  return (now - Math.min(...dates)) / 3600000;
}
