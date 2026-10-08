/** Billing dates are pairs. Never mix two providers' starts and ends. */
const { parseResetInstant } = require('./dayWindow');

function normalizeCycle(start, end) {
  const a = parseResetInstant(start);
  const b = parseResetInstant(end);
  if (!a || !b || a >= b) return null;
  return { start: a.toISOString(), end: b.toISOString(), estimated: false };
}

function currentCycle(cycle, now = new Date()) {
  return Boolean(cycle && Date.parse(cycle.start) <= +now && +now < Date.parse(cycle.end));
}

function selectCycle(candidates, now = new Date()) {
  const valid = candidates.filter(Boolean);
  const current = valid.filter(cycle => currentCycle(cycle, now));
  // A stale fallback must not overwrite the live billing interval.
  return (current.length ? current : valid).sort((a, b) =>
    Date.parse(b.start) - Date.parse(a.start) || Date.parse(b.end) - Date.parse(a.end))[0] || null;
}

function shiftMonths(anchor, months, day) {
  const date = new Date(anchor);
  date.setUTCDate(1);
  date.setUTCMonth(date.getUTCMonth() + months);
  const last = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate();
  date.setUTCDate(Math.min(day, last));
  return date;
}

function subscriptionCycle(start, end, { now = new Date(), activePaid = false } = {}) {
  const cycle = normalizeCycle(start, end);
  if (!cycle) return null;
  if (currentCycle(cycle, now)) return cycle;
  if (!activePaid || Date.parse(cycle.end) > +now) return null;
  const a = new Date(cycle.start), b = new Date(cycle.end);
  const months = (b.getUTCFullYear() - a.getUTCFullYear()) * 12 + b.getUTCMonth() - a.getUTCMonth();
  // Only infer a recognizable monthly/annual schedule. Never add 30 days,
  // or extrapolate a cancelled/free plan, trial, or malformed claim.
  if (months !== 1 && months !== 12) return null;
  const day = Math.max(a.getUTCDate(), b.getUTCDate());
  if (+shiftMonths(a, months, day) !== +b) return null;
  const elapsed = (now.getUTCFullYear() - b.getUTCFullYear()) * 12 + now.getUTCMonth() - b.getUTCMonth();
  let n = Math.max(0, Math.floor(elapsed / months));
  let next = shiftMonths(b, (n + 1) * months, day);
  if (+next <= +now) { n += 1; next = shiftMonths(b, (n + 1) * months, day); }
  let previous = shiftMonths(b, n * months, day);
  if (+previous > +now) { n -= 1; next = previous; previous = shiftMonths(b, n * months, day); }
  return { start: previous.toISOString(), end: next.toISOString(), estimated: true };
}

module.exports = { normalizeCycle, currentCycle, selectCycle, subscriptionCycle };
