// End-to-end UI test. Needs a running server (BASE) and the `playwright` package.
// Usage: BASE=http://127.0.0.1:8000 SHOTS=/tmp/shots node e2e/ui.e2e.js
const { chromium } = require('playwright');

const BASE = process.env.BASE || 'http://127.0.0.1:8000';
const SHOTS = process.env.SHOTS || '/tmp/ui-shots';
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
function nextWeekday(weekday /* 0 = Monday */, minDaysAhead) {
  const d = new Date();
  d.setDate(d.getDate() + minDaysAhead);
  while ((d.getDay() + 6) % 7 !== weekday) d.setDate(d.getDate() + 1);
  return iso(d);
}

let step = 0;
function check(cond, msg) {
  if (!cond) throw new Error(`FAIL: ${msg}`);
  console.log(`ok ${String(++step).padStart(2, '0')}  ${msg}`);
}
const names = (page) => page.locator('article.maid h3').allTextContents();
async function waitForCards(page, n) {
  await page.waitForFunction((count) => document.querySelectorAll('article.maid').length === count, n, { timeout: 8000 });
}
async function search(page, fields) {
  for (const [id, value] of Object.entries(fields)) await page.fill(`#${id}`, value);
  await page.click('#search-form button[type=submit]');
}

const problems = [];
let page;
(async () => {
  const browser = await chromium.launch();
  page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error' && !m.text().includes('Failed to load resource')) problems.push(`console: ${m.text()}`); });

  const tuesday = nextWeekday(1, 3);
  const monday = nextWeekday(0, 3);

  // 1. Empty state and sample data
  await page.goto(BASE);
  await page.waitForSelector('text=No maids match yet');
  check(true, 'empty state is shown before any maid exists');
  await page.screenshot({ path: `${SHOTS}/01-empty.png` });
  await page.click('#seed-btn');
  await waitForCards(page, 3);
  check((await names(page)).join() === 'Asha Rao,Meena Iyer,Ravi Kumar', 'sample maids load, sorted by rating');
  await page.screenshot({ path: `${SHOTS}/02-results.png`, fullPage: true });

  // 2. Filters
  await search(page, { 'f-locality': 'koramangala' });
  await waitForCards(page, 2);
  check((await names(page)).join() === 'Asha Rao,Ravi Kumar', 'area filter is case-insensitive');
  await page.selectOption('#f-rating', '4.5');
  await page.click('#search-form button[type=submit]');
  await waitForCards(page, 1);
  check((await names(page))[0] === 'Asha Rao', 'min rating filter');
  await page.click('#f-reset');
  await waitForCards(page, 3);
  await page.selectOption('#f-gender', 'MALE');
  await page.click('#search-form button[type=submit]');
  await waitForCards(page, 1);
  check((await names(page))[0] === 'Ravi Kumar', 'gender filter');
  await page.click('#f-reset');
  await search(page, { 'f-skills': 'infant-care' });
  await waitForCards(page, 1);
  check((await names(page))[0] === 'Meena Iyer', 'skills filter');
  await page.click('#f-reset');
  await search(page, { 'f-rate': '150' });
  await waitForCards(page, 1);
  check((await names(page))[0] === 'Ravi Kumar', 'max rate without a service matches any offered rate (Ravi dishwashing is 120)');
  await page.selectOption('#f-service', 'CLEANING');
  await page.click('#search-form button[type=submit]');
  await page.waitForSelector('text=No maids match yet');
  check(true, 'max rate with a service applies to that service only (cleaning rates are 180 and up)');
  await page.click('#f-reset');
  await waitForCards(page, 3);

  // 3. Availability search
  await search(page, { 'f-date': tuesday, 'f-time': '10:00' });
  await waitForCards(page, 3);
  check(true, 'all three maids are free Tuesday 10:00');
  await search(page, { 'f-time': '08:30' });
  await waitForCards(page, 1);
  check((await names(page))[0] === 'Asha Rao', 'only maids working at 08:30 are returned');
  await page.fill('#f-time', '');
  await page.click('#search-form button[type=submit]');
  await page.waitForSelector('text=Pick both a date and a start time');
  check(true, 'date without time is rejected with a message');

  // 4. Book, decline, pay
  await search(page, { 'f-date': tuesday, 'f-time': '10:00' });
  await waitForCards(page, 3);
  await page.click('article.maid:has-text("Asha Rao") >> text=Book Asha');
  await page.waitForSelector('#booking-form');
  check((await page.inputValue('#b-date')) === tuesday, 'booking dialog is prefilled from the search');
  await page.screenshot({ path: `${SHOTS}/03-book-dialog.png` });
  await page.click('#b-submit');
  await page.waitForSelector('#payment-form');
  check(await page.locator('#p-submit').textContent() === 'Pay ₹250.00', 'payment button shows the amount');
  await page.fill('#p-instrument', 'fail@upi');
  await page.click('#p-submit');
  await page.waitForSelector('#p-error .banner.err');
  check((await page.textContent('#p-error')).includes('declined'), 'declined payment shows an error and stays on the form');
  await page.screenshot({ path: `${SHOTS}/04-payment-declined.png` });
  await page.fill('#p-instrument', 'asha@upi');
  await page.click('#p-submit');
  await page.waitForSelector('text=Booking confirmed');
  check((await page.textContent('#dlg-body')).includes('₹250.00'), 'payment succeeds and booking is confirmed');
  await page.screenshot({ path: `${SHOTS}/05-confirmed.png` });
  await page.click('#dlg-body button:text-is("Close")');

  // 5. The booked maid disappears from availability search
  await page.waitForSelector('article.maid');
  await search(page, { 'f-date': tuesday, 'f-time': '10:00' });
  await waitForCards(page, 2);
  check(!(await names(page)).includes('Asha Rao'), 'a booked maid is no longer offered for that time');

  // 6. Another customer cannot take the same slot
  await page.fill('#customer', 'bob');
  await page.press('#customer', 'Tab');
  await page.fill('#f-date', '');
  await page.fill('#f-time', '');
  await page.click('#search-form button[type=submit]');
  await waitForCards(page, 3);
  await page.click('article.maid:has-text("Asha Rao") >> text=Book Asha');
  await page.fill('#b-date', tuesday);
  await page.fill('#b-time', '10:30');
  await page.click('#b-submit');
  await page.waitForSelector('#b-error .banner.err');
  check((await page.textContent('#b-error')).includes('not available'), 'double booking attempt shows the conflict');
  await page.click('#dlg-body button:text-is("Cancel")');

  // 7. Bookings are per customer
  await page.goto(`${BASE}/#bookings`);
  await page.waitForSelector('text=No bookings yet');
  check(true, 'a different customer sees no bookings');
  await page.fill('#customer', 'customer-1');
  await page.press('#customer', 'Tab');
  await page.waitForSelector('article.booking');
  check((await page.textContent('article.booking')).includes('Confirmed'), 'original customer sees the confirmed booking');
  await page.screenshot({ path: `${SHOTS}/06-my-bookings.png`, fullPage: true });

  // 8. Cancel with refund
  await page.click('article.booking button:has-text("Cancel")');
  await page.click('article.booking button:has-text("Confirm cancel")');
  await page.waitForSelector('.toast:has-text("Refund ₹250.00")');
  check(true, 'cancelling more than 24h ahead refunds in full');
  await page.waitForSelector('article.booking .pill:has-text("Cancelled")');
  await page.goto(`${BASE}/#find`);
  await search(page, { 'f-date': tuesday, 'f-time': '10:00' });
  await waitForCards(page, 3);
  check((await names(page)).includes('Asha Rao'), 'cancelled slot is bookable again');

  // 9. Recurring booking, partial payment, then cancellations
  await page.fill('#f-date', ''); await page.fill('#f-time', '');
  await search(page, { 'f-locality': 'koramangala' });
  await waitForCards(page, 2);
  await page.click('article.maid:has-text("Ravi Kumar") >> text=Book Ravi');
  await page.click('label:has-text("Recurring")');
  await page.click('.days label:has-text("Mon")');
  await page.click('.days label:has-text("Wed")');
  await page.fill('#b-rdate', monday);
  await page.fill('#b-rtime', '10:00');
  await page.fill('#b-count', '4');
  check((await page.textContent('#estimate')).includes('₹720.00'), 'recurring estimate multiplies by the number of visits');
  await page.click('#b-submit');
  await page.waitForSelector('#payment-form');
  await page.click('label:has-text("One visit")');
  await page.selectOption('#p-method', 'WALLET');
  await page.fill('#p-instrument', 'wallet-1');
  await page.click('#p-submit');
  await page.waitForSelector('text=Visit paid');
  check((await page.textContent('#dlg-body')).includes('3 visits still awaiting payment'), 'one visit of a series can be paid on its own');
  await page.click('#dlg-body button:text-is("Close")');
  await page.goto(`${BASE}/#bookings`);
  const series = page.locator('article.booking:has-text("Recurring")');
  await series.waitFor();
  check((await series.textContent()).includes('Awaiting payment'), 'series shows awaiting payment while visits are unpaid');
  await series.locator('button:has-text("Pay all 3 unpaid")').click();
  await page.selectOption('#p-method', 'CARD');
  await page.fill('#p-instrument', '4111111111111111');
  check((await page.locator('#p-submit').textContent()) === 'Pay ₹540.00', 'pay-all button sums the unpaid visits');
  await page.click('#p-submit');
  await page.waitForSelector('text=Booking confirmed');
  await page.click('#dlg-body button:text-is("Close")');
  await page.waitForFunction(() => {
    const card = [...document.querySelectorAll('article.booking')].find((a) => a.textContent.includes('Recurring'));
    return card && card.querySelectorAll('.occ li .pill.CONFIRMED').length === 4;
  });
  check(await series.locator('.occ li').count() === 4, 'series lists all four visits');
  await page.screenshot({ path: `${SHOTS}/07-series.png`, fullPage: true });
  await series.locator('.occ li').nth(1).locator('button:has-text("Cancel")').click();
  await series.locator('.occ li').nth(1).locator('button:has-text("Confirm cancel")').click();
  await page.waitForSelector('.toast:has-text("Cancelled 1 visit. Refund ₹180.00")');
  check(true, 'a single visit of the series can be cancelled with its own refund');
  await series.locator('button:has-text("Cancel whole series")').click();
  await series.locator('button:has-text("Confirm cancel series")').click();
  await page.waitForSelector('.toast:has-text("Cancelled 3 visits. Refund ₹540.00")');
  await series.locator('> .booking-head .pill:has-text("Cancelled")').waitFor();
  check(true, 'cancelling the whole series refunds the remaining visits');

  // 10. Add a maid (validation, then success)
  await page.goto(`${BASE}/#add`);
  await page.fill('#m-name', 'Zoya Khan');
  await page.fill('#m-locality', 'HSR Layout');
  await page.fill('#m-rating', '4.9');
  await page.check('input[name=svc][value=COOKING]');
  await page.click('#add-form button[type=submit]');
  await page.waitForSelector('#add-form .banner.err');
  check((await page.textContent('#add-form .banner.err')).includes('hourly rate for Cooking'), 'add form asks for a rate for every chosen service');
  await page.fill('input[name=rate-COOKING]', '320');
  await page.fill('#m-skills', 'baking, north-indian');
  await page.click('#add-form button[type=submit]');
  await page.waitForSelector('.toast:has-text("Zoya Khan added")');
  await waitForCards(page, 4);
  await page.selectOption('#f-service', 'COOKING');
  await search(page, { 'f-locality': 'hsr layout' });
  await waitForCards(page, 1);
  check((await page.textContent('article.maid')).includes('₹320.00/h'), 'new maid is searchable with her rate');
  check((await page.locator('#localities option').evaluateAll((o) => o.map((x) => x.value))).includes('HSR Layout'), 'area suggestions include the new maid\'s area');

  // 11. Instant booking gives either a payment form or a clear reason
  await page.click('#f-reset');
  await waitForCards(page, 4);
  await page.click('article.maid:has-text("Meena Iyer") >> text=Book Meena');
  await page.click('label:has-text("Instant")');
  await page.click('#b-submit');
  await page.waitForSelector('#payment-form, #b-error .banner.err');
  check(true, 'instant booking responds with a payment form or an explained error');
  await page.keyboard.press('Escape');

  // 12. Phone layout
  const phone = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await phone.goto(BASE);
  await phone.waitForSelector('article.maid');
  const overflow = await phone.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  check(!overflow, 'no horizontal scrolling at phone width');
  await phone.screenshot({ path: `${SHOTS}/08-phone.png` });

  check(problems.length === 0, `no JavaScript errors (${problems.join(' | ') || 'none'})`);
  await browser.close();
  console.log(`\nAll ${step} UI checks passed`);
})().catch(async (e) => { console.error(e.message); if (page) { await page.screenshot({ path: `${SHOTS}/failure.png`, fullPage: true }).catch(() => {}); console.error('Page text:', (await page.textContent('main').catch(() => '')).slice(0, 400)); } if (problems.length) console.error('Browser problems:', problems.join(' | ')); process.exit(1); });
