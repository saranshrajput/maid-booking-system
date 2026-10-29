// "Book now" end to end against a server with a fixed clock.
//   SCENARIO=day   server clock Tue 10:07: maids are working, so an instant booking goes all the way through
//   SCENARIO=night server clock Tue 21:00: nobody is working, so the user is told and offered a later slot
const { chromium } = require('playwright');

const BASE = process.env.BASE || 'http://127.0.0.1:8766';
const SCENARIO = process.env.SCENARIO || 'day';
const SHOTS = process.env.SHOTS || '/tmp/ui-shots';
const problems = [];
let page;
let step = 0;
function check(cond, msg) {
  if (!cond) throw new Error(`FAIL: ${msg}`);
  console.log(`ok ${String(++step).padStart(2, '0')}  [${SCENARIO}] ${msg}`);
}
const text = (sel) => page.locator(sel).first().innerText();

async function startBookNow() {
  await page.goto(BASE);
  await page.waitForSelector('#seed-btn, .tile');
  if (await page.locator('#seed-btn').count()) await page.click('#seed-btn');
  await page.waitForSelector('.tile[data-service="CLEANING"] small:has-text("maid")');
  await page.click('#promo');
  await page.waitForSelector('#sections .card');
  check((await text('#sections .card h3')) === 'Starts right now', 'Book now opens the details screen in Now mode');
  check((await page.getAttribute('.segtabs [data-mode="NOW"]', 'aria-pressed')) === 'true', 'the Now tab is selected');
  check(await page.locator('#see-maids').isEnabled(), 'no date or time is needed for an instant booking');
}

(async () => {
  const browser = await chromium.launch();
  page = await browser.newPage({ viewport: { width: 420, height: 900 } });
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error' && !m.text().includes('Failed to load resource')) problems.push(`console: ${m.text()}`); });

  await startBookNow();
  await page.click('[data-minutes="60"]');
  await page.click('#see-maids');

  if (SCENARIO === 'night') {
    await page.waitForSelector('#no-match');
    check((await text('#no-match h3')) === 'No maid is free right now', 'with nobody working the user is told so plainly');
    await page.screenshot({ path: `${SHOTS}/instant-night.png` });
    await page.click('#schedule-later');
    await page.waitForSelector('#cal');
    check((await page.getAttribute('.segtabs [data-mode="ONE"]', 'aria-pressed')) === 'true', 'Schedule for later switches to a dated booking');
  } else {
    await page.waitForSelector('article.maid');
    check((await page.locator('article.maid h3').allTextContents()).join() === 'Asha Rao,Ravi Kumar', 'only maids working right now and offering cleaning are listed');
    check((await text('#flow-summary')).includes('Right now'), 'the summary says the visit starts right now');
    await page.screenshot({ path: `${SHOTS}/instant-maids.png` });
    await page.click('article.maid[data-maid="Ravi Kumar"] [data-book]');
    await page.waitForSelector('#payment-form');
    check((await text('#p-submit')) === 'Pay ₹180.00', 'an hour with Ravi costs ₹180');
    await page.fill('#p-instrument', 'ravi@upi');
    await page.click('#p-submit');
    await page.waitForSelector('#paid-title');
    check((await text('#paid-title')) === 'Booking confirmed', 'payment confirms the instant booking');
    await page.click('#view-booking');

    await page.waitForSelector('#status-title');
    check((await text('#status-title')) === 'Service in progress', 'a paid instant booking is in progress straight away');
    check((await text('#d-start')) === '10:07 am', 'it starts at the current minute');
    const ring = await text('#ring');
    const left = Number((ring.match(/\d+/g) || []).pop());
    check(ring.includes('TIME LEFT') && left >= 50 && left <= 60, `the time-left ring counts down the hour (${left} min)`);
    check((await page.locator('.statusbar').count()) === 1, 'the screen is drawn once');
    await page.screenshot({ path: `${SHOTS}/instant-in-progress.png`, fullPage: true });

    await page.goto(`${BASE}/#/bookings`);
    await page.waitForSelector('article.bk');
    check((await text('article.bk .pill')).toLowerCase() === 'in progress', 'the bookings list shows the visit as in progress');

    await startBookNow();
    await page.click('#see-maids');
    await page.waitForSelector('article.maid');
    check((await page.locator('article.maid h3').allTextContents()).join() === 'Asha Rao', 'a maid already on a visit is not offered for another instant booking');

    await page.goto(`${BASE}/#/bookings`);
    await page.click('article.bk a.bk-main');
    await page.waitForSelector('#detail-actions button.visit');
    await page.click('#detail-actions button.visit');
    await page.click('#detail-actions button.visit:has-text("Confirm cancel")');
    await page.waitForSelector('.toast:has-text("Refund ₹0.00")');
    check(true, 'cancelling a visit that has already started refunds nothing');
  }

  check(problems.length === 0, `no JavaScript errors (${problems.join(' | ') || 'none'})`);
  await browser.close();
  console.log(`\nAll ${step} instant-booking checks passed (${SCENARIO})`);
})().catch(async (e) => {
  console.error(e.message);
  if (problems.length) console.error('Browser problems:', problems.join(' | '));
  if (page) {
    await page.screenshot({ path: `${SHOTS}/instant-failure-${SCENARIO}.png`, fullPage: true }).catch(() => {});
    console.error('Page text:', (await page.innerText('body').catch(() => '')).replace(/\s+/g, ' ').slice(0, 500));
  }
  process.exit(1);
});
