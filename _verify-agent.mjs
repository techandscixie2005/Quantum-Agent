import { chromium } from 'playwright';
const page = await chromium.launch().then(b => b.newPage());
const reqs = [];
page.on('request', r => { if (!r.url().endsWith('.woff2') && !r.url().endsWith('.js')) reqs.push(`${r.method()} ${r.url().replace('http://127.0.0.1:3000','')}`); });
page.on('response', async r => {
  if (r.status() >= 400) console.log(`!! ${r.status()} ${r.request().method()} ${r.url().slice(0,120)}`);
});
await page.goto('http://127.0.0.1:3000/agent', { waitUntil: 'networkidle', timeout: 30000 });
console.log('--- all requests ---');
reqs.forEach(r => console.log('  ' + r));
const text = await page.locator('body').innerText();
console.log('--- body text (first 600 chars) ---');
console.log(text.slice(0, 600));
await page.screenshot({ path: '/tmp/claude-1000/agent-login.png', fullPage: false });
console.log('--- screenshot saved ---');
