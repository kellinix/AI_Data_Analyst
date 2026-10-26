import { createRequire } from 'node:module';
import { Buffer } from 'node:buffer';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
// Optional maintenance tool: Next.js already installs sharp in frontend/.
const require = createRequire(path.join(root, '../frontend/package.json'));
const sharp = require('sharp');
const source = await readFile(path.join(root, '../logo/02-icon-only.svg'), 'utf8');
const mark = source.match(/<g transform="translate\(72, 44\)">([\s\S]*?)<\/g>/)?.[1];
if (!mark) throw new Error('Existing logo mark not found');
const svg = (background, transform, monochrome = false) => `<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">${background ? `<rect width="1024" height="1024" fill="${background}"/>` : ''}<g transform="${transform}">${monochrome ? mark.replace(/#[A-Fa-f0-9]{6}/g, '#FFFFFF') : mark}</g></svg>`;
await sharp(Buffer.from(svg('#F6F8FC', 'translate(192,190) scale(8)'))).png().toFile(path.join(root, 'assets/icon.png'));
await sharp(Buffer.from(svg(null, 'translate(272,250) scale(6)'))).png().toFile(path.join(root, 'assets/android-icon-foreground.png'));
await sharp(Buffer.from(svg(null, 'translate(272,250) scale(6)', true))).png().toFile(path.join(root, 'assets/android-icon-monochrome.png'));
await sharp(Buffer.from(svg(null, 'translate(272,250) scale(6)'))).resize(256, 256).png().toFile(path.join(root, 'assets/splash-icon.png'));
await sharp(Buffer.from(svg('#F6F8FC', 'translate(192,190) scale(8)'))).resize(48, 48).png().toFile(path.join(root, 'assets/favicon.png'));
console.log('Rendered native app assets from the existing logo');
