import test from 'node:test';
import assert from 'node:assert/strict';
import { findInstrument, getProviderStatus } from './data-provider.js';

test('catalog classifies BIST equity and US ETF separately', () => {
  assert.equal(findInstrument('THYAO').exchange, 'BIST');
  assert.equal(findInstrument('SPY').assetType, 'ETF');
});
test('unsupported coverage is explicit', () => assert.equal(findInstrument('AAPL').coverage, 'unavailable'));
test('provider status never claims real time', () => assert.equal(getProviderStatus().realTime, false));
