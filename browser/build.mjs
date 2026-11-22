import {copyFile, mkdir, readFile, writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const output = join(root, 'dist', 'native');
await mkdir(output, {recursive: true});
const entries = [
  ['browser', ['browser.css', 'chat.js', 'backend.js', 'analytics.js', 'usage-transport.js', 'pdf.js']],
  ['native', ['native.js']],
  ['app/static', ['owl.svg', 'theme.css', 'styles.css', 'chat.css', 'markdown.js', 'streaming.js', 'app.js', 'display-preferences.js', 'workspace.css', 'usage.css', 'usage.js']],
  ['app/static/vendor', ['marked.min.js', 'purify.min.js', 'highlight.min.js', 'marked.LICENSE', 'dompurify.LICENSE', 'highlight.LICENSE']],
];
await Promise.all(entries.flatMap(([directory, files]) => files.map(file => copyFile(join(root, directory, file), join(output, file)))));
const read = file => readFile(join(root, file), 'utf8');
const staticLinks = html => html.replaceAll('/static/vendor/', './').replaceAll('/static/', './').replaceAll('href="/"', 'href="./"');
const shared = await read('app/static/index.html');
const chat = staticLinks(shared.split('<body class="chat-page">')[1].split('</body>')[0])
  .replace('href="/settings?v=5"', 'href="#settings"')
  .replace('href="/usage"', 'href="./usage.html"')
  .replace(/^.*href="\/lab".*$/m, '        <a href="?onboarding=1">Model setup</a>');
const display = (await read('app/static/settings.html')).match(/<section id="display-panel"[\s\S]*?<\/section>/)[0]
  .replace(' role="tabpanel" aria-labelledby="display-tab" hidden', '');
const settings = `<dialog id="browser-settings" aria-labelledby="browser-settings-title">
  <header><h1 id="browser-settings-title">Settings</h1>
    <form method="dialog"><button class="icon-button" aria-label="Close settings">×</button></form>
  </header>
  <div class="browser-settings-content">
    <p class="setup-note">Replies are generated on this device. When Search is enabled, only the current search query goes to the search service.</p>
    ${display}
    <a class="manage-models" href="?onboarding=1">Model setup</a>
  </div>
</dialog>`;
const shell = await read('browser/index.html');
await writeFile(join(output, 'index.html'), shell.replace('<!-- shared chat -->', () => chat).replace('<!-- display settings -->', () => settings));
const usage = staticLinks(await read('app/static/usage.html'))
  .replace('<script src="./usage.js?v=2" defer></script>', '<script src="./usage-transport.js" type="module"></script>')
  .replace('<a href="/usage" aria-current="page">Usage</a><a href="/lab">Lab</a>', '<a href="./usage.html" aria-current="page">Usage</a>');
await writeFile(join(output, 'usage.html'), usage);
for (const file of ['pdf.min.mjs', 'pdf.worker.min.mjs']) {
  await copyFile(join(root, 'node_modules/pdfjs-dist/build', file), join(output, file));
}
await copyFile(join(root, 'node_modules/pdfjs-dist/LICENSE'), join(output, 'pdfjs.LICENSE'));
