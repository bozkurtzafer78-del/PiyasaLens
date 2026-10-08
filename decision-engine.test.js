import test from 'node:test';
import assert from 'node:assert/strict';
import { calculateDecision } from './decision-engine.js';

const base = { price: 100, target: 110, buyLow: 90, buyHigh: 105, buyCost: .2, sellCost: .2, stop: 95 };
test('blocks 4.99 net potential', () => assert.notEqual(calculateDecision({ ...base, target: 105.5 }).newBuy, 'Al'));
test('5 percent is necessary but not sufficient', () => assert.notEqual(calculateDecision({ ...base, target: 106 }).newBuy, 'Al'));
test('missed buy band produces wait', () => assert.equal(calculateDecision({ ...base, price: 106 }).newBuy, 'Bekle / İzle'));
test('costs can pull gross above 5 below net 5', () => assert.ok(calculateDecision({ ...base, target: 105.3 }).net < 5));
test('missing data does not recommend', () => assert.equal(calculateDecision({ ...base, target: null }).newBuy, 'Veri yetersiz'));
test('stale data does not recommend', () => assert.equal(calculateDecision({ ...base, dataAgeHours: 25, maxDataAgeHours: 24 }).newBuy, 'Veri yetersiz'));
test('blocked new buy is not automatic sell', () => assert.equal(calculateDecision({ ...base, target: 104, thesis: 'intact' }).holding, 'Tut'));
test('thesis can independently trigger holding reduction', () => assert.equal(calculateDecision({ ...base, thesis: 'broken' }).holding, 'Azalt / Sat'));
test('below lower buy band is blocked', () => assert.notEqual(calculateDecision({ ...base, buyLow: 101 }).newBuy, 'Al'));
test('stop at or above price cannot bypass risk', () => assert.equal(calculateDecision({ ...base, stop: 101 }).newBuy, 'Veri yetersiz'));
test('missing buy band is rejected', () => assert.equal(calculateDecision({ ...base, buyLow: null }).newBuy, 'Veri yetersiz'));
test('negative costs rejected', () => assert.equal(calculateDecision({ ...base, buyCost: -1 }).newBuy, 'Veri yetersiz'));
test('broken thesis cannot produce a new buy', () => assert.notEqual(calculateDecision({ ...base, target: 120, thesis: 'broken' }).newBuy, 'Al'));
test('valid in-band opportunity passes with costs', () => assert.equal(calculateDecision({ ...base, target: 120 }).newBuy, 'Al'));
