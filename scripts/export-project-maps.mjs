import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

// One-time, local rendering. The application does not need the presentation runtime.
const modules = process.env.ARTIFACT_NODE_MODULES;
if (!modules) throw new Error('Set ARTIFACT_NODE_MODULES to the bundled Node.js packages directory.');
const require = createRequire(path.join(modules, 'package.json'));
const { FileBlob, PresentationFile } = await import(pathToFileURL(require.resolve('@oai/artifact-tool')));
const JSZip = require('jszip');
const { xml2js } = require('xml-js');
const sharp = require('sharp');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourceFile = 'Fixed Asset ID Process & Progress - 11 August 2026.pptx';
const source = path.join(root, 'DOCUMENTOS', sourceFile);
const destination = path.join(root, 'backend/app/resources/project-maps');
const bytes = await fs.readFile(source);
const zip = await JSZip.loadAsync(bytes);
const presentation = await PresentationFile.importPptx(await FileBlob.load(source));
const pages = [
  { id: 'plant-1', slide: 3, es: 'Planta 1', en: 'Plant 1' },
  { id: 'plant-2-esd-injection', slide: 4, es: 'Planta 2 - ESD e inyecci\u00f3n', en: 'Plant 2 - ESD and injection' },
  { id: 'plant-2-second-floor', slide: 5, es: 'Planta 2 - Segundo piso', en: 'Plant 2 - Second floor' },
  { id: 'plant-2-expansion', slide: 6, es: 'Planta 2 - Expansi\u00f3n', en: 'Plant 2 - Expansion' },
  { id: 'plant-2-expansion-second-floor', slide: 7, es: 'Planta 2 - Expansi\u00f3n, segundo piso', en: 'Plant 2 - Expansion, second floor' },
  { id: 'temporary-warehouse', slide: 8, es: 'Almac\u00e9n temporal', en: 'Temporary warehouse' },
];
const nodes = (node, name) => [
  ...(node.name === name ? [node] : []),
  ...(node.elements ?? []).flatMap(child => nodes(child, name)),
];
await fs.mkdir(destination, { recursive: true });
for (const page of pages) {
  const xml = xml2js(await zip.file(`ppt/slides/slide${page.slide}.xml`).async('string'));
  page.text = nodes(xml, 'a:p').map(p => nodes(p, 'a:t').flatMap(t => (t.elements ?? []).map(v => v.text ?? '')).join('')).filter(Boolean);
  const slide = presentation.slides.getItem(page.slide - 1);
  const rendered = await presentation.export({ slide, format: 'png', scale: 2.25 });
  const image = Buffer.from(await rendered.arrayBuffer());
  const metadata = await sharp(image).metadata();
  page.width = metadata.width;
  page.height = metadata.height;
  await sharp(image).png({ compressionLevel: 9 }).toFile(path.join(destination, `${page.id}.png`));
  await sharp(image).resize({ width: 320 }).png().toFile(path.join(destination, `${page.id}-thumb.png`));
  console.log(`${page.id}: ${page.width}x${page.height}`);
}
await fs.writeFile(path.join(destination, 'manifest.json'), JSON.stringify({
  title: 'Fixed Asset ID Process & Progress', sourceFile,
  sourceSha256: createHash('sha256').update(bytes).digest('hex'),
  date: '2026-08-11', location: 'Zacatecas', pages,
}, null, 2) + '\n');
