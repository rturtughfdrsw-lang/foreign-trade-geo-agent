/* Local browser QA only; no customer services or persisted credentials. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.DEMO_PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({ channel: process.env.DEMO_BROWSER_CHANNEL || 'msedge', headless: true });
  const url = process.env.DEMO_URL;
  assert.match(url, /^http:\/\/127\.0\.0\.1:\d+$/);
  const errors = [], external = [], mutations = [];
  const credentials = { username: process.env.DEMO_USERNAME, password: process.env.DEMO_PASSWORD };
  const output = process.env.DEMO_SCREENSHOTS;
  let checks = 0;
  const check = (value, message) => { assert.ok(value, message); checks++; };
  try {
    const anonymous = await browser.newContext();
    check((await anonymous.request.get(url + '/healthz')).status() === 200, 'Health is public');
    check((await anonymous.request.get(url)).status() === 401, 'Home requires authentication');
    await anonymous.close();
    const context = await browser.newContext({ httpCredentials: credentials, viewport: { width: 1440, height: 900 } });
    await context.route('**/*', route => {
      if (new URL(route.request().url()).origin !== url) {
        external.push(route.request().url());
        return route.abort();
      }
      if (!['GET', 'HEAD'].includes(route.request().method())) mutations.push(route.request().method());
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    const noOverflow = async () => check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No horizontal overflow');
    const shot = name => page.screenshot({ path: path.join(output, name + '.png'), fullPage: true });
    await page.goto(url);
    check(await page.locator('h1').textContent() === 'SEO 内容工作台', 'Clear home heading');
    check(await page.locator('a.primary').count() === 1, 'Exactly one primary home action');
    check(await page.locator('form,input,select,textarea').count() === 0, 'No unavailable business controls');
    await noOverflow();
    await shot('desktop-home');
    await page.getByRole('link', { name: '体验演示任务' }).click();
    const taskUrl = page.url();
    check(await page.locator('[data-review-item]').count() === 5, 'Actual seed contains five obligations');
    check(await page.locator('[data-review-item]:visible').count() === 1, 'Only one item is shown');
    check(await page.locator('output').textContent() === '1 / 5', 'Initial progress is browsing position');
    check(await page.getByRole('button', { name: '上一项' }).isDisabled(), 'First item has no previous');
    check(await page.locator('details[open]').count() === 0, 'All evidence is collapsed');
    await noOverflow();
    await shot('desktop-review');
    const firstTop = (await page.locator('[data-review-item]:visible').boundingBox()).y;
    const firstScroll = await page.evaluate(() => scrollY);
    for (let index = 2; index <= 5; index++) {
      await page.getByRole('button', { name: '下一项' }).click();
      check(await page.locator('output').textContent() === `${index} / 5`, 'Next item updates position');
      check(await page.locator('[data-review-item]:visible').count() === 1, 'Exactly one item after switching');
      check(Math.abs((await page.locator('[data-review-item]:visible').boundingBox()).y - firstTop) < 2, 'Workspace stays in position');
      check(await page.evaluate(() => scrollY) === firstScroll, 'Switch does not scroll page');
    }
    check(await page.getByRole('button', { name: '下一项' }).isDisabled(), 'Last item has no next');
    await page.getByRole('button', { name: '上一项' }).focus();
    await page.keyboard.press('Enter');
    check(await page.locator('output').textContent() === '4 / 5', 'Keyboard navigates items');
    await page.locator('[data-review-item]:visible').getByText('查看完整原文与来源', { exact: true }).click();
    check(await page.locator('[data-review-item]:visible blockquote').first().isVisible(), 'Full original quote opens');
    check(await page.evaluate(() => !Array.from(document.querySelectorAll('*')).some(e => {
      const css = getComputedStyle(e);
      return e !== document.documentElement && e !== document.body && ['auto', 'scroll'].includes(css.overflowY) && e.scrollHeight > e.clientHeight;
    })), 'No nested scrolling containers');
    await page.getByRole('button', { name: '上一项' }).click();
    check(await page.locator('details[open]').count() === 0, 'Leaving an item collapses its evidence');
    await page.getByRole('tab', { name: '事实核对' }).focus();
    await page.keyboard.press('ArrowRight');
    check(await page.getByRole('tab', { name: '文章内容' }).getAttribute('aria-selected') === 'true', 'Arrow keys switch tabs');
    check(await page.getByText('此演示任务尚无文章正文。', { exact: true }).isVisible(), 'No fabricated generated article');
    await shot('desktop-article');
    await page.getByRole('tab', { name: '事实核对' }).click();
    check(await page.locator('output').textContent() === '3 / 5', 'Changing tabs retains browsing position');
    await page.reload();
    check(await page.locator('output').textContent() === '1 / 5', 'Reload does not claim saved review');
    check(await page.evaluate(() => localStorage.length === 0 && sessionStorage.length === 0), 'Navigation stores no data');
    check(await page.locator('[data-review-item]:visible .status').textContent() === '尚未核对', 'Browsing does not change review status');
    check(!(await page.content()).includes(credentials.password), 'Password never rendered');
    for (const width of [390, 320, 768]) {
      await page.setViewportSize({ width, height: width === 768 ? 900 : 844 });
      await page.goto(url);
      await noOverflow();
      check(await page.getByRole('link', { name: '体验演示任务' }).isVisible(), 'Home action visible on small screens');
      if (width === 390) await shot('mobile-home');
      await page.getByRole('link', { name: '体验演示任务' }).click();
      await noOverflow();
      await page.getByRole('button', { name: '下一项' }).click();
      check(await page.locator('output').textContent() === '2 / 5', 'Small-screen navigation works');
      if (width === 390) await shot('mobile-review');
      await page.getByRole('tab', { name: '文章内容' }).click();
      await noOverflow();
      if (width === 390) await shot('mobile-article');
    }
    await page.setViewportSize({ width: 720, height: 450 });
    await page.goto(taskUrl);
    await page.locator('[data-review-workspace]').scrollIntoViewIfNeeded();
    const scrolled = await page.evaluate(() => scrollY);
    check(scrolled > 0, 'Short viewport exercises scrolled navigation');
    await page.getByRole('button', { name: '下一项' }).click();
    check(await page.evaluate(() => scrollY) === scrolled, 'Navigation preserves nonzero scroll position');
    const noJs = await browser.newContext({ httpCredentials: credentials, javaScriptEnabled: false });
    const fallback = await noJs.newPage();
    await fallback.goto(taskUrl);
    check(await fallback.locator('[data-review-item]:visible').count() === 5, 'All evidence remains available without JS');
    check(await fallback.getByRole('button', { name: '下一项' }).count() === 0, 'No dead navigation without JS');
    await noJs.close();
    check(external.length === 0, 'No external requests');
    check(mutations.length === 0, 'UI sends no mutations');
    check(errors.length === 0, 'No JavaScript or CSP errors: ' + errors.join('; '));
    console.log(JSON.stringify({ browser: 'Chromium / ' + process.env.DEMO_BROWSER_CHANNEL, checks, failures: 0,
      viewports: ['1440x900', '390x844', '320x844', '768x900', '720x450'], screenshots: output }));
    await context.close();
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
