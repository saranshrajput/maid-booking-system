// End-to-end UI test. Needs a running server (BASE) and the `playwright` package.
// Usage: BASE=http://127.0.0.1:8000 SHOTS=/tmp/shots node e2e/ui.e2e.js   (server must start with no maids)
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
const tuesday = nextWeekday(1, 3);
const monday = nextWeekday(0, 3);

const problems = [];
let page;
let step = 0;
function check(cond, msg) {
  if (!cond) throw new Error(`FAIL: ${msg}`);
  console.log(`ok ${String(++step).padStart(2, '0')}  ${msg}`);
}
const text = (sel) => page.locator(sel).first().innerText();
async function pickDate(date) {
  for (let i = 0; i < 4 && !(await page.locator(`#cal [data-date="${date}"]`).count()); i++) await page.click('#cal-next');
  await page.click(`#cal [data-date="${date}"]`);
}
async function startDetails(service, mode) {
  await page.goto(`${BASE}/#/details/${service}`);
  await page.waitForSelector('#sections .card');
  await page.click(`.segtabs [data-mode="${mode}"]`);
  await page.waitForSelector('#sections .card');
}
async function chooseSlot(time, period) {
  if (period) await page.click(`[data-period="${period}"]`);
  await page.click(`.slot[data-time="${time}"]`);
}
async function bookWith(name) {
  await page.click('#see-maids');
  await page.waitForSelector(`article.maid[data-maid="${name}"]`);
  await page.click(`article.maid[data-maid="${name}"] [data-book]`);
  await page.waitForSelector('#payment-form');
}
async function payWith(method, instrument) {
  await page.selectOption('#p-method', method);
  await page.fill('#p-instrument', instrument);
  await page.click('#p-submit');
}

(async () => {
  const browser = await chromium.launch();
  page = await browser.newPage({ viewport: { width: 420, height: 900 } });
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error' && !m.text().includes('Failed to load resource')) problems.push(`console: ${m.text()}`); });

  // 1. Home, empty state, sample data, area
  await page.goto(BASE);
  await page.waitForSelector('#seed-btn');
  check((await text('h2')).includes('What service do you need?'), 'home shows the service question and an empty state');
  await page.screenshot({ path: `${SHOTS}/01-home-empty.png` });
  await page.click('#seed-btn');
  await page.waitForSelector('.tile[data-service="CLEANING"] small:has-text("2 maids")');
  check((await text('.tile[data-service="CLEANING"] small')).includes('from ₹180/hour'), 'tiles show the lowest hourly rate and maid count');
  await page.click('#area-btn');
  await page.click('button[data-area="Koramangala"]');
  await page.waitForSelector('.tile[data-service="LAUNDRY"][aria-disabled="true"]');
  check((await text('#area-btn')).includes('Koramangala'), 'choosing an area updates the header');
  check((await text('.tile[data-service="LAUNDRY"] small')).includes('Not available'), 'a service nobody offers in the area is disabled');
  await page.screenshot({ path: `${SHOTS}/02-home.png`, fullPage: true });

  // 2. Choose service details: calendar, duration, time slots
  await page.click('.tile[data-service="CLEANING"]');
  await page.waitForSelector('#cal');
  check((await text('h2')).includes('Choose service details'), 'service tile opens the details screen');
  await pickDate(tuesday);
  await page.waitForSelector('.slot[data-time="08:00"]');
  check(await page.locator('.slot[data-time="07:45"]').isDisabled(), 'a start time before every maid starts work is greyed out');
  check(await page.locator('.slot[data-time="08:00"]').isEnabled(), 'a start time when a maid is free is selectable');
  check(await page.locator('#see-maids').isDisabled(), 'maid list stays locked until a time is chosen');
  await chooseSlot('10:00');
  check((await text('#bar-price')) === 'from ₹180', 'price bar shows the cheapest total for the choice');
  await page.click('[data-minutes="120"]');
  await page.waitForSelector('.slot[data-time="10:00"]');
  check((await text('#bar-price')) === 'from ₹360', 'changing the duration updates the price and clears the time');
  check(await page.locator('#see-maids').isDisabled(), 'changing the duration clears the chosen time');
  await page.click('[data-minutes="60"]');
  await page.waitForSelector('.slot[data-time="10:00"]');
  await chooseSlot('10:00');
  await page.screenshot({ path: `${SHOTS}/03-details.png`, fullPage: true });

  // 3. Maid list, declined and successful payment
  await page.click('#see-maids');
  await page.waitForSelector('article.maid');
  const names = await page.locator('article.maid h3').allTextContents();
  check(names.join() === 'Asha Rao,Ravi Kumar', 'only maids free at that time are listed, best rated first');
  await page.screenshot({ path: `${SHOTS}/04-maids.png`, fullPage: true });
  await page.click('article.maid[data-maid="Asha Rao"] [data-book]');
  await page.waitForSelector('#payment-form');
  check((await text('#p-submit')) === 'Pay ₹250.00', 'payment sheet shows the amount to pay');
  await payWith('UPI', 'fail@upi');
  await page.waitForSelector('#p-error .note.err');
  check((await text('#p-error')).includes('declined'), 'a declined payment shows an error and keeps the sheet open');
  await page.screenshot({ path: `${SHOTS}/05-payment.png` });
  await page.fill('#p-instrument', 'asha@upi');
  await page.click('#p-submit');
  await page.waitForSelector('#paid-title');
  check((await text('#paid-title')) === 'Booking confirmed', 'successful payment confirms the booking');
  await page.click('#view-booking');

  // 4. Booking details, then cancel with refund
  await page.waitForSelector('#status-title');
  check((await text('#status-title')) === 'Upcoming service', 'booking details show an upcoming service');
  check(!/null|undefined/.test(await text('#view')), 'booking details show no stray null or undefined text');
  check((await text('#d-start')) === '10:00 am' && (await text('#d-total')) === '₹250.00' && (await text('#d-paystatus')) === 'Paid online', 'details show time, amount and paid status');
  await page.screenshot({ path: `${SHOTS}/06-booking-details.png`, fullPage: true });
  await page.click('#detail-actions button.visit');
  await page.click('#detail-actions button.visit:has-text("Confirm cancel")');
  await page.waitForSelector('.toast:has-text("Refund ₹250.00")');
  await page.waitForSelector('#status-title:has-text("Booking cancelled")');
  check(true, 'cancelling more than 24h ahead refunds in full and marks the booking cancelled');

  // 5. Grey-out: when every maid is booked, that start time becomes unavailable
  async function bookAt10(maidName) {
    await startDetails('CLEANING', 'ONE');
    await pickDate(tuesday);
    await page.waitForSelector('.slot[data-time="10:00"]');
    await chooseSlot('10:00');
    await bookWith(maidName);
    await page.click('#pay-later');
  }
  await bookAt10('Asha Rao');
  await bookAt10('Ravi Kumar');
  await startDetails('CLEANING', 'ONE');
  await pickDate(tuesday);
  await page.waitForSelector('.slot[data-time="10:00"]');
  check(await page.locator('.slot[data-time="10:00"]').isDisabled(), 'a start time with every maid booked is greyed out');
  check(await page.locator('.slot[data-time="09:15"]').isDisabled(), 'a start time that overlaps the bookings is greyed out too');
  check(await page.locator('.slot[data-time="11:00"]').isEnabled(), 'the time right after the bookings is still free');
  await page.screenshot({ path: `${SHOTS}/07-slots-greyed.png`, fullPage: true });

  // 6. Pay a held booking later from My bookings
  await page.goto(`${BASE}/#/bookings`);
  await page.waitForSelector('article.bk');
  check((await page.locator('article.bk').count()) === 3, 'bookings list shows every booking for the customer');
  check((await text('#filters [aria-pressed="true"]')) === 'All', 'All filter is selected by default');
  const held = page.locator('article.bk:has-text("Awaiting payment")').first();
  await held.locator('a.bk-main').click();
  await page.waitForSelector('#pay-visit');
  check((await text('#status-title')) === 'Payment pending', 'a held booking shows payment pending');
  await page.click('#pay-visit');
  await payWith('CARD', '4111111111111111');
  await page.waitForSelector('#paid-title');
  await page.click('#paid-close');
  await page.waitForSelector('#status-title:has-text("Upcoming service")');
  check(true, 'a held booking can be paid later and becomes upcoming');

  // 7. Multiple days
  await startDetails('CLEANING', 'MULTI');
  const wed = nextWeekday(2, 10), fri = nextWeekday(4, 10);
  await pickDate(wed);
  await pickDate(fri);
  check((await text('.rangebar .daychip')) === '3 days', 'picking a start and end date shows the number of days');
  await page.waitForSelector('.slot[data-time="09:00"]');
  await chooseSlot('09:00');
  check((await text('#bar-price')) === 'from ₹540', 'multi-day price multiplies by the number of days');
  await bookWith('Ravi Kumar');
  check((await text('#p-submit')) === 'Pay ₹540.00', 'paying all three days costs the sum');
  await payWith('WALLET', 'wallet-1');
  await page.waitForSelector('#paid-title');
  await page.click('#paid-close');

  // 8. Weekly recurring, pay one visit
  await startDetails('COOKING', 'WEEKLY');
  await pickDate(monday);
  await page.click('#weekly-card [data-day="2"]');
  await page.fill('#visits', '4');
  await page.waitForSelector('.slot[data-time="10:00"]');
  await chooseSlot('10:00');
  await bookWith('Asha Rao');
  await page.click('label:has-text("One visit")');
  await payWith('UPI', 'asha@upi');
  await page.waitForSelector('#paid-title');
  check((await text('#paid-detail')).includes('3 visits still awaiting payment'), 'one visit of a weekly series can be paid on its own');
  await page.click('#paid-close');

  // 9. Bookings list filters and visits
  await page.goto(`${BASE}/#/bookings`);
  await page.waitForSelector('article.bk[data-kind="multiple"]');
  check((await page.locator('article.bk[data-kind="multiple"]').count()) === 1 && (await page.locator('article.bk[data-kind="recurring"]').count()) === 1, 'bookings are classified as single, multiple or recurring');
  await page.click('#filters [data-filter="multiple"]');
  check((await page.locator('article.bk').count()) === 1, 'the Multiple filter shows only multi-day bookings');
  const multi = page.locator('article.bk[data-kind="multiple"]');
  check((await multi.textContent()).includes('3 days'), 'multi-day card summarises the number of days');
  await multi.locator('.togglevisits').click();
  check((await multi.locator('a.visit').count()) === 3, 'expanding a card lists every visit');
  await page.screenshot({ path: `${SHOTS}/08-bookings.png`, fullPage: true });
  await multi.locator('a.visit').nth(1).click();
  await page.waitForSelector('.dots');
  check((await page.locator('.dot').count()) === 3, 'visit details show a dot per visit');
  await page.screenshot({ path: `${SHOTS}/09-visit-details.png`, fullPage: true });
  await page.click('#detail-actions button.visit');
  await page.click('#detail-actions button.visit:has-text("Confirm cancel")');
  await page.waitForSelector('.toast:has-text("Cancelled 1 visit. Refund ₹180.00")');
  await page.waitForSelector('.dot.cancelled');
  check(true, 'cancelling one visit of a series refunds just that visit');
  await page.click('#detail-actions button.series');
  await page.click('#detail-actions button.series:has-text("Confirm cancel series")');
  await page.waitForSelector('.toast:has-text("Cancelled 2 visits. Refund ₹360.00")');
  check(true, 'cancelling the whole series refunds the remaining visits');

  // 10. Instant booking answers either way
  await startDetails('CLEANING', 'NOW');
  await page.click('#see-maids');
  await page.waitForSelector('article.maid, #no-match');
  check(true, 'instant booking lists maids free right now or explains there are none');

  // 11. Account and customers
  await page.click('#dlg-close').catch(() => {});
  await page.goto(`${BASE}/#/account`);
  await page.fill('#customer', 'bob');
  await page.press('#customer', 'Enter');
  await page.goto(`${BASE}/#/bookings`);
  await page.waitForSelector('#no-bookings');
  check(true, 'a different customer id sees no bookings');
  await page.goto(`${BASE}/#/account`);
  await page.fill('#customer', 'customer-1');
  await page.press('#customer', 'Enter');

  // 12. Add a maid
  await page.click('#add-maid-link');
  await page.fill('#m-name', 'Zoya Khan');
  await page.fill('#m-locality', 'HSR Layout');
  await page.check('input[name=svc][value=COOKING]');
  await page.click('#add-submit');
  await page.waitForSelector('#add-form .note.err');
  check((await text('#add-form .note.err')).includes('hourly rate for cooking'), 'add form asks for a rate for every chosen service');
  await page.fill('input[name=rate-COOKING]', '320');
  await page.click('#add-submit');
  await page.waitForSelector('.toast:has-text("Zoya Khan added")');
  await page.click('#area-btn');
  await page.click('button[data-area="HSR Layout"]');
  await page.waitForSelector('.tile[data-service="COOKING"] small:has-text("1 maid")');
  check((await text('.tile[data-service="COOKING"] small')).includes('from ₹320/hour'), 'a new maid appears under her area with her rate');

  // 12b. Many maids: the list is paged and aggregates come from the server
  await page.evaluate(async () => {
    for (let i = 0; i < 24; i++) {
      await fetch('/api/maids', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        name: `Bulk ${String(i).padStart(2, '0')}`, locality: 'Koramangala', gender: 'FEMALE', rating: 3 + (i % 10) / 10, hourlyRates: { CLEANING: 150 + i },
        skills: [], availability: [0, 1, 2, 3, 4, 5].map((day) => ({ day, start: '08:00', end: '18:00' })) }) });
    }
  });
  await page.goto(`${BASE}/#/home`);
  await page.click('#area-btn');
  await page.click('button[data-area="Koramangala"]');
  await page.waitForSelector('.tile[data-service="CLEANING"] small:has-text("maids")');
  check((await text('.tile[data-service="CLEANING"] small')).includes('from ₹150/hour · 26 maids'), 'home tiles aggregate 26 cleaning maids in one summary query');
  await startDetails('CLEANING', 'ONE');
  await pickDate(tuesday);
  await page.waitForSelector('.slot[data-time="08:00"]');
  await chooseSlot('14:00', 'Afternoon');
  await page.click('#see-maids');
  await page.waitForSelector('article.maid');
  check((await page.locator('article.maid').count()) === 20, 'the maid list shows one page of 20');
  check((await text('#result-count')) === '26 maids available', 'the total comes from the server');
  await page.click('#show-more');
  await page.waitForFunction(() => document.querySelectorAll('article.maid').length === 26);
  check(await page.locator('#show-more').isHidden(), 'Show more loads the rest and hides itself');
  await page.screenshot({ path: `${SHOTS}/11-paged-list.png` });

  // 13. Layout and errors
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  check(!overflow, 'no horizontal scrolling at phone width');
  const wide = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await wide.goto(`${BASE}/#/bookings`);
  await wide.waitForSelector('article.bk');
  await wide.screenshot({ path: `${SHOTS}/10-desktop.png` });
  check(problems.length === 0, `no JavaScript errors (${problems.join(' | ') || 'none'})`);
  await browser.close();
  console.log(`\nAll ${step} UI checks passed`);
})().catch(async (e) => {
  console.error(e.message);
  if (problems.length) console.error('Browser problems:', problems.join(' | '));
  if (page) {
    await page.screenshot({ path: `${SHOTS}/failure.png`, fullPage: true }).catch(() => {});
    console.error('Page text:', (await page.innerText('body').catch(() => '')).replace(/\s+/g, ' ').slice(0, 500));
  }
  process.exit(1);
});
