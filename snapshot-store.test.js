import test from 'node:test';
import assert from 'node:assert/strict';
import { readCloudMarket, persistMarketSnapshot, PROVIDER } from './snapshot-store.js';
function database() {
  const docs = new Map();
  return { docs, doc(path) { return { path, async get() { return { exists: docs.has(path), data: () => docs.get(path) }; }, async set(value) { docs.set(path, value); } }; },
    batch() { const writes = []; return { set(ref, value) { writes.push([ref.path, value]); }, async commit() { for (const [path, value] of writes) docs.set(path, value); } }; },
    collection(path) { return { orderBy() { return { async get() { const entries = [...docs].filter(([key]) => key.startsWith(path + '/')).sort(([a], [b]) => a.localeCompare(b)); return { empty: !entries.length, docs: entries.map(([, value]) => ({ data: () => value })) }; } }; } }; } };
}
function payload(count = 101) {
  const row = market => ({ source: 'test', provider: market, delayed: true, data_quality: 'delayed', fetched_at: '2026-10-08T16:15:00Z', row_count: count, items: Array.from({ length: count }, (_, i) => ({ symbol: `${market}${i}`, price: 100 })) });
  return { provider: PROVIDER, generated_at: '2026-10-08T16:15:00Z', markets: { BIST: row('BIST'), US: row('US') }, gemini: { status: 'ok', generated_at: '2026-10-08T16:15:00Z', result: { picks: [] } } };
}
test('cloud round trip keeps both markets, provider and strategy', async () => {
  const db = database(), input = payload(); await persistMarketSnapshot(db, input);
  const result = await readCloudMarket(db);
  assert.equal(result.provider, PROVIDER); assert.equal(result.markets.BIST.items.length, 101);
  assert.equal(result.markets.US.items.length, 101); assert.deepEqual(result.gemini, input.gemini);
});
test('smaller snapshot cannot include old trailing pages', async () => {
  const db = database(); await persistMarketSnapshot(db, payload()); await persistMarketSnapshot(db, payload(1));
  assert.equal((await readCloudMarket(db)).markets.BIST.items.length, 1);
});
test('empty snapshots do not replace metadata', async () => {
  const db = database(); await persistMarketSnapshot(db, payload());
  const meta = db.docs.get('marketSnapshots/meta');
  await assert.rejects(persistMarketSnapshot(db, { markets: {} }));
  assert.equal(db.docs.get('marketSnapshots/meta'), meta);
});
test('failed page write preserves active snapshot', async () => {
  const db = database(); await persistMarketSnapshot(db, payload());
  const meta = db.docs.get('marketSnapshots/meta');
  db.batch = () => ({ set() {}, async commit() { throw new Error('write failed'); } });
  await assert.rejects(persistMarketSnapshot(db, payload(1)));
  assert.equal(db.docs.get('marketSnapshots/meta'), meta);
});
