/**
 * Daily ledger for the Codex weekly quota.
 *
 * The quota service reports how much of a rolling window is used and nothing
 * else: there is no per-day figure and no amount of money to read. Today's
 * consumption therefore has to be reconstructed from samples taken on this
 * machine — each refresh adds the positive step since the previous sample, and
 * a rolled reset instant counts the whole new reading.
 *
 * The file holds percentages and timestamps only.
 */
const fs = require('fs');
const path = require('path');

const { secureWriteJson } = require('./privacy');
const { stateDir } = require('./localState');

const LEDGER_VERSION = 1;

/** A sample this close behind keeps the baseline across the 9:00 boundary. */
const CONTINUITY_MS = 15 * 60 * 1000;

function ledgerPath() {
  return path.join(stateDir(), 'codex-daily.json');
}

function round2(value) {
  return Math.round(value * 100) / 100;
}

function readLedger() {
  try {
    const parsed = JSON.parse(fs.readFileSync(ledgerPath(), 'utf8'));
    if (!parsed || parsed.version !== LEDGER_VERSION) return null;
    if (typeof parsed.window !== 'string') return null;
    return parsed;
  } catch (_) {
    return null;
  }
}

/** True when the stored sample is recent enough to serve as a baseline. */
function isContinuous(state, nowMs) {
  const seen = Date.parse((state && state.updatedAt) || '');
  if (!Number.isFinite(seen)) return false;
  return nowMs >= seen && nowMs - seen <= CONTINUITY_MS;
}

function startDay(windowKey, nowIso, percent, resetAt, partial) {
  return {
    version: LEDGER_VERSION,
    window: windowKey,
    todayPercent: 0,
    lastPercent: percent,
    lastResetAt: resetAt || null,
    partial: partial,
    baselineAt: nowIso,
    updatedAt: nowIso,
  };
}

/**
 * Today's consumption as recorded so far, without adding a sample.
 * `partial` means the baseline was taken mid-day, so the figure is a lower
 * bound rather than the full day.
 */
function readGptToday(windowKey) {
  const state = readLedger();
  if (!state || state.window !== windowKey) {
    return { percent: null, partial: true };
  }
  const percent = Number(state.todayPercent);
  return {
    percent: Number.isFinite(percent) ? percent : null,
    partial: Boolean(state.partial),
  };
}

/** Add one reading of the weekly window and return today's running total. */
function recordGptSample(options) {
  const opts = options || {};
  const windowKey = String(opts.windowKey || '');
  const percent = Number(opts.percent);
  if (!windowKey || !Number.isFinite(percent)) {
    return readGptToday(windowKey);
  }

  const nowMs = Number.isFinite(opts.nowMs) ? opts.nowMs : Date.now();
  const nowIso = new Date(nowMs).toISOString();
  const resetAt = opts.resetAt || null;

  let state = readLedger();
  if (!state || state.window !== windowKey) {
    const carried = state && isContinuous(state, nowMs);
    state = startDay(
      windowKey,
      nowIso,
      carried ? Number(state.lastPercent) : percent,
      carried ? state.lastResetAt : resetAt,
      !carried,
    );
  }

  const previous = Number(state.lastPercent);
  const rolled = Boolean(state.lastResetAt && resetAt && state.lastResetAt !== resetAt);
  let step = 0;
  if (rolled) {
    // The weekly window restarted at zero, so the new reading is all new spend.
    step = Math.max(0, percent);
  } else if (Number.isFinite(previous) && percent > previous) {
    step = percent - previous;
  }

  state.todayPercent = round2(Number(state.todayPercent) + step);
  state.lastPercent = percent;
  state.lastResetAt = resetAt;
  state.updatedAt = nowIso;

  try {
    secureWriteJson(ledgerPath(), state);
  } catch (_) {
    // A read-only home must not break the readout.
  }

  return { percent: state.todayPercent, partial: Boolean(state.partial) };
}

module.exports = {
  recordGptSample,
  readGptToday,
  ledgerPath,
  LEDGER_VERSION,
  CONTINUITY_MS,
};
