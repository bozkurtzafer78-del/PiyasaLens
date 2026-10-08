import { randomUUID } from 'node:crypto';
export const PROVIDER = 'BIST Data Service + Twelve Data EOD';

export async function readCloudMarket(db) {
  if (!db) return null;
  const meta = await db.doc('marketSnapshots/meta').get();
  if (!meta.exists) return null;
  const info = meta.data();
  const keys = info.markets || ['BIST', 'US'];
  const pairs = await Promise.all(keys.map(async market => {
    const id = info.snapshots?.[market] || `latest_${market}`;
    const pages = await db.collection(`marketSnapshots/${id}/pages`).orderBy('page').get();
    if (pages.empty) throw new Error(`${market} snapshot sayfaları eksik.`);
    const first = pages.docs[0].data();
    const items = pages.docs.flatMap(page => page.data().items || []);
    if (items.length !== first.row_count) throw new Error(`${market} snapshot eksik.`);
    return [market, { market, source: first.source, provider: first.provider, data_quality: first.data_quality,
      delayed: first.delayed, retained: Boolean(first.retained), fetched_at: first.fetched_at, row_count: items.length, items }];
  }));
  if (!pairs.length) return null;
  return { provider: PROVIDER, generated_at: info.generated_at, markets: Object.fromEntries(pairs), errors: info.errors || [], gemini: info.gemini || null };
}

export async function persistMarketSnapshot(db, payload) {
  if (!db) return false;
  const entries = Object.entries(payload.markets || {});
  if (!entries.length || entries.some(([, value]) => !value.items?.length)) throw new Error('Boş snapshot yayınlanamaz.');
  const version = randomUUID();
  const snapshots = {};
  let batch = db.batch(), writes = 0;
  for (const [market, snapshot] of entries) {
    const id = `${version}_${market}`;
    snapshots[market] = id;
    const items = snapshot.items;
    for (let offset = 0; offset < items.length; offset += 100) {
      const page = offset / 100;
      batch.set(db.doc(`marketSnapshots/${id}/pages/${String(page).padStart(4, '0')}`), {
        market, source: snapshot.source || '', provider: snapshot.provider || '', data_quality: snapshot.data_quality || 'partial',
        delayed: Boolean(snapshot.delayed), retained: Boolean(snapshot.retained), fetched_at: snapshot.fetched_at || payload.generated_at,
        row_count: items.length, page, items: items.slice(offset, offset + 100),
      });
      if (++writes === 400) { await batch.commit(); batch = db.batch(); writes = 0; }
    }
  }
  if (writes) await batch.commit();
  // Readers switch only once every page is written; no mixed old/new market pages.
  await db.doc('marketSnapshots/meta').set({ provider: PROVIDER, generated_at: payload.generated_at,
    errors: payload.errors || [], markets: entries.map(([market]) => market), snapshots,
    gemini: payload.gemini || null, updatedAt: new Date().toISOString() });
  return true;
}
