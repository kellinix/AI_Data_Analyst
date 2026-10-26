import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const root = fileURLToPath(new URL('../', import.meta.url));
const destination = path.join(root, 'src/generated');
await mkdir(destination, { recursive: true });
// One source of truth for the browser and mobile API contracts.
const contracts = await readFile(path.join(root, '../frontend/src/types/index.ts'), 'utf8');
await writeFile(path.join(destination, 'contracts.ts'), '// Generated from frontend/src/types/index.ts.\n' + contracts);
const runtime = await readFile(require.resolve('echarts/dist/echarts.min.js'), 'utf8');
await writeFile(path.join(destination, 'echarts.ts'), '// Generated from the installed ECharts package.\nexport default ' + JSON.stringify(runtime) + ';\n');
console.log('Prepared shared contracts and offline chart runtime');
