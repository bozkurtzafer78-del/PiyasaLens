import test from 'node:test';
import assert from 'node:assert/strict';
import { buildAlert, evaluateAlert, notificationKey } from './alerts.js';
const item = { symbol: 'TEST', market: 'BIST', price: 100 };
test('return alert uses saved reference price rather than daily change', () => {
  const alert = buildAlert(item, '', '5');
  assert.equal(evaluateAlert({ ...item, price: 101, change_pct: 8 }, alert).triggered, false);
  assert.equal(evaluateAlert({ ...item, price: 105, change_pct: 0 }, alert).triggered, true);
});
test('zero disables return target; price target still works', () => {
  const alert = buildAlert(item, '110', '0');
  assert.equal(alert.returnPct, null);
  assert.equal(evaluateAlert({ ...item, price: 110 }, alert).triggered, true);
});
test('invalid target cannot be saved', () => {
  for (const price of ['-1', 'Infinity', 'oops']) assert.throws(() => buildAlert(item, price, '5'));
  assert.throws(() => buildAlert(item, '', '0'));
});
test('legacy alarms need reference price for return trigger', () => {
  assert.equal(evaluateAlert({ ...item, change_pct: 10 }, { returnPct: 5 }).triggered, false);
  assert.equal(evaluateAlert({ ...item, price: 110 }, { price: 110 }).triggered, true);
});
test('notification keys separate symbols and accounts', () => {
  assert.notEqual(notificationKey(item), notificationKey({ ...item, symbol: 'OTHER' }));
  assert.notEqual(notificationKey(item, 'first'), notificationKey(item, 'second'));
});
