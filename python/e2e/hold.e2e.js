// Hold expiry end to end. The server clock is read from CLOCK_FILE, so the test can move time forward.
const { chromium } = require('playwright');
const fs = require('fs');

const BASE = process.env.BASE || 'http://127.0.0.1:8766';
const CLOCK_FILE = process.env.CLOCK_FILE || '/tmp/hold-e2e-clock.txt';
const SHOTS = process.env.SHOTS || '/tmp/ui-shots';
const DAY = '2030-01-10';                                   // the day we book; the server clock starts on 2030-01-08

const problems = [];
let page;
let step = 0;
function check(cond, msg) {
  if (!cond) throw new Error(`FAIL: ${msg}`);
  console.log(`ok ${String(++step).padStart(2, '0')}  [hold] ${msg}`);
}
const text = (sel) => page.locator(sel).first().innerText();
const setClock = (iso) => fs.writeFileSync(CLOCK_FILE, iso);
const api = (path, options) => page.evaluate(async ([p, o]) => {
  const res = await fetch(p, o); return { status: res.status, body: await res.json().catch(() => null) };
}, [path, options]);
const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
async function waitSweep() { await page.waitForTimeout(2500); }          // the server sweeps every second

(async () => {
  setClock('2030-01-08T10:00:00');
  const browser = await chromium.launch();
  page = await browser.newPage({ viewport: { width: 420, height: 900 } });
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error' && !m.text().includes('Failed to load resource')) problems.push(`console: ${m.text()}`); });

  // Maids, then a booking made through the UI and left unpaid
  await page.goto(BASE);
  await page.click('#seed-btn');
  await page.waitForSelector('.tile[data-service="CLEANING"] small:has-text("2 maids")');
  await page.click('.tile[data-service="CLEANING"]');
  await page.waitForSelector('#cal');
  await page.click(`#cal [data-date="${DAY}"]`);
  await page.waitForSelector('.slot[data-time="08:00"]');
  await page.click('.slot[data-time="10:00"]');
  await page.click('#see-maids');
  await page.waitForSelector('article.maid[data-maid="Asha Rao"]');
  await page.click('article.maid[data-maid="Asha Rao"] [data-book]');
  await page.waitForSelector('#payment-form');
  check(/held for (9|10):\d\d/.test(await text('#hold-timer')), 'the payment sheet counts down the hold');
  await page.screenshot({ path: `${SHOTS}/hold-sheet.png` });
  await page.click('#pay-later');
  await page.waitForSelector('article.bk');
  check((await text('article.bk .pill')).toLowerCase() === 'awaiting payment', 'an unpaid booking is awaiting payment');

  // While the hold is live nobody else can have the slot
  const asha = (await api('/api/maids/search?serviceType=CLEANING')).body.find((m) => m.name === 'Asha Rao');
  const ravi = (await api('/api/maids/search?serviceType=CLEANING')).body.find((m) => m.name === 'Ravi Kumar');
  const slotBody = (maid, customer, hour) => ({ customerId: customer, maidId: maid.id, serviceType: 'CLEANING', bookingType: 'SCHEDULED',
    durationMinutes: 60, startDateTime: `${DAY}T${hour}:00` });
  const taken = await post('/api/bookings', slotBody(asha, 'customer-2', '10'));
  check(taken.status === 409 && taken.body.code === 'SLOT_UNAVAILABLE', 'a live hold blocks the slot for other customers');

  // Time passes: the hold runs out and the sweeper marks it expired
  setClock('2030-01-08T10:11:00');
  await waitSweep();
  await page.reload();
  await page.waitForSelector('article.bk');
  check((await text('article.bk .pill')).toLowerCase() === 'expired', 'after the deadline the booking shows as expired');
  check((await text('article.bk')).includes('Not paid in time'), 'the list says it was not paid in time');
  await page.screenshot({ path: `${SHOTS}/hold-expired-list.png` });

  // The slot is bookable again, and the expired customer can still pay while it is free
  await page.click('article.bk a.bk-main');
  await page.waitForSelector('#status-title');
  check((await text('#status-title')) === 'Hold expired', 'the details screen says the hold expired');
  check((await text('#d-paystatus')) === 'Not paid in time', 'payment status reads not paid in time');
  check(await page.locator('#detail-actions button.visit').count() === 0, 'an expired visit cannot be cancelled');
  await page.screenshot({ path: `${SHOTS}/hold-expired-details.png`, fullPage: true });
  await page.click('#pay-visit');
  await page.waitForSelector('#payment-form');
  check((await text('#hold-timer')).includes('hold on this slot has ended'), 'the sheet explains that paying now re-checks the slot');
  await page.fill('#p-instrument', 'asha@upi');
  await page.click('#p-submit');
  await page.waitForSelector('#paid-title');
  check((await text('#paid-title')) === 'Booking confirmed', 'a late payment succeeds while the slot is still free');
  await page.click('#view-booking');
  await page.waitForSelector('#status-title:has-text("Upcoming service")');
  check(true, 'the booking is back to upcoming');

  // Someone else takes a lapsed slot, so the late payment is refused
  const lapsed = await post('/api/bookings', slotBody(ravi, 'customer-2', '14'));
  check(lapsed.status === 201, 'a second customer holds Ravi at 14:00');
  setClock('2030-01-08T10:30:00');
  await waitSweep();
  const winner = await post('/api/bookings', slotBody(ravi, 'customer-1', '14'));
  check(winner.status === 201, 'the lapsed hold no longer blocks the slot');
  const paid = await post(`/api/bookings/${winner.body.id}/payments`, { method: 'WALLET', instrument: 'w-1' });
  check(paid.status === 201, 'and the new customer pays for it');
  await page.reload();
  await page.goto(`${BASE}/#/booking/${lapsed.body.id}`);
  await page.waitForSelector('#pay-visit');
  await page.click('#pay-visit');
  await page.fill('#p-instrument', 'late@upi');
  await page.click('#p-submit');
  await page.waitForSelector('#p-error .note.err');
  check((await text('#p-error')).includes('no longer free'), 'a late payment is refused when the slot was taken');
  check(await page.locator('#choose-another').isVisible(), 'the sheet offers another time');
  await page.screenshot({ path: `${SHOTS}/hold-late-refused.png` });
  const none = await api(`/api/bookings/${lapsed.body.id}`);
  check(none.body.occurrences[0].status === 'EXPIRED', 'nothing was charged: the visit stays expired');

  check(problems.length === 0, `no JavaScript errors (${problems.join(' | ') || 'none'})`);
  await browser.close();
  console.log(`\nAll ${step} hold-expiry checks passed`);
})().catch(async (e) => {
  console.error(e.message);
  if (problems.length) console.error('Browser problems:', problems.join(' | '));
  if (page) {
    await page.screenshot({ path: `${SHOTS}/hold-failure.png`, fullPage: true }).catch(() => {});
    console.error('Page text:', (await page.innerText('body').catch(() => '')).replace(/\s+/g, ' ').slice(0, 500));
  }
  process.exit(1);
});
