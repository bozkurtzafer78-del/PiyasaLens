import test from 'node:test';
import assert from 'node:assert/strict';
import { marketPulse, validStrategy } from './ui-data.js';
test('unknown change does not become zero in market average', () => {
  assert.equal(marketPulse([{ change_pct: null }, { change_pct: 10 }]).average, 10);
  assert.equal(marketPulse([{ change_pct: null }]).average, null);
});
test('old AI output cannot be attached to a new market snapshot', () => {
  assert.equal(validStrategy({ status: 'ok', generated_at: 'old' }, { generated_at: 'new' }), null);
});
import { dataAgeHours } from './ui-data.js';
test('new refresh cannot make an old quote fresh', () => {
  const now = Date.parse('2026-10-08T12:00:00Z');
  assert.equal(dataAgeHours({ markets: { US: { items: [{ as_of: '2026-10-01T12:00:00Z' }] } } }, now), 168);
  assert.equal(dataAgeHours({ markets: { US: { items: [{ as_of: null }] } } }, now), Infinity);
});
test('undated strategy is rejected', () => {
  assert.equal(validStrategy({ status: 'ok' }, {}), null);
});
