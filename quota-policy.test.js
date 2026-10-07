import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const read = (file) => readFile(new URL(`./${file}`, import.meta.url), 'utf8');

test('daily quota policy removes manual refresh and frequent polling', async () => {
  const [html, script] = await Promise.all([read('index.html'), read('propicks.js')]);
  assert.doesNotMatch(html, /id="refreshButton"/);
  assert.doesNotMatch(script, /refreshButton/);
  assert.doesNotMatch(script, /setInterval\s*\(/);
  assert.match(html, /Hafta içi otomatik güncellenir/);
});

test('backend schedule is limited to one weekday run', async () => {
  const functions = await read('functions/index.js');
  assert.match(functions, /schedule:\s*'15 19 \* \* 1-5'/);
  assert.match(functions, /range:\s*\[0, 500\]/);
});
