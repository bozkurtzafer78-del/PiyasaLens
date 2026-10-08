import { mkdir, copyFile, rm } from 'node:fs/promises';
const files = ['index.html', 'propicks.js', 'propicks.css', 'account.css', 'firebase-client.js', 'ui-data.js'];
await rm('dist', { recursive: true, force: true });
await mkdir('dist', { recursive: true });
for (const file of files) await copyFile(file, `dist/${file}`);
console.log('Web dosyaları dist/ içine hazırlandı.');
