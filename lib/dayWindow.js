/**
 * Day boundaries and instant parsing shared by the usage readers.
 *
 * The ledger day runs 9:00 → 9:00 so an overnight session is still billed to
 * the day it started on.
 */

const DAY_START_HOUR = 9;

function formatDate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/**
 * Parse a billing instant: epoch ms (number or digit string), ISO datetime,
 * or a legacy YYYY-MM-DD date.
 */
function parseResetInstant(value) {
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (value == null) return null;
  if (typeof value === 'number') {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  if (typeof value === 'string') {
    if (/^\d+$/.test(value)) {
      const d = new Date(Number(value));
      return Number.isNaN(d.getTime()) ? null : d;
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      const d = new Date(`${value}T00:00:00`);
      return Number.isNaN(d.getTime()) ? null : d;
    }
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  return null;
}

/** Ledger day window: today 9:00 → tomorrow 9:00. */
function getApiDayWindow(now = new Date()) {
  const start = new Date(now);
  start.setHours(DAY_START_HOUR, 0, 0, 0);
  if (now < start) {
    start.setDate(start.getDate() - 1);
  }
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return { start, end };
}

module.exports = {
  formatDate,
  parseResetInstant,
  getApiDayWindow,
  DAY_START_HOUR,
};
