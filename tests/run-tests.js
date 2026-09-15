#!/usr/bin/env node
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), 'agentbudget-test-'));
process.env.AGENTBUDGET_STATE_DIR = stateDir;

const { parseUsagePayload } = require('../lib/gptApi');
const { toPublicSnapshot } = require('../lib/compute');
const { redactPrivate } = require('../lib/privacy');
const { computeTodayUsage, isAutoModel } = require('../lib/usageDetails');
const { recordGptSample, readGptToday } = require('../lib/gptLedger');

const legacy = parseUsagePayload({
  plan_type: 'pro',
  rate_limit: {
    primary_window: { used_percent: 2, limit_window_seconds: 18000, reset_at: 10 },
    secondary_window: { used_percent: 7, limit_window_seconds: 604800, reset_at: 20 },
  },
  additional_rate_limits: [{
    limit_name: 'GPT-5.3-Codex-Spark',
    rate_limit: {
      primary_window: { used_percent: 3, limit_window_seconds: 18000, reset_at: 30 },
      secondary_window: { used_percent: 4, limit_window_seconds: 604800, reset_at: 40 },
    },
  }],
}, {});
assert.strictEqual(legacy.main.percent, 7);
assert.strictEqual(legacy.main.kind, '周额度');
assert.strictEqual(legacy.windows.length, 4);

const official = parseUsagePayload({
  rateLimitsByLimitId: {
    codex: {
      limitId: 'codex', planType: 'pro',
      primary: { usedPercent: 1, windowDurationMins: 10080, resetsAt: 50 },
    },
    codex_bengalfox: {
      limitId: 'codex_bengalfox', limitName: 'GPT-5.3-Codex-Spark',
      primary: { usedPercent: 6, windowDurationMins: 300, resetsAt: 60 },
      secondary: { usedPercent: 8, windowDurationMins: 10080, resetsAt: 70 },
    },
  },
}, {});
assert.strictEqual(official.main.percent, 1);
assert.strictEqual(official.plan, 'Pro');
assert.strictEqual(official.source, 'codex-app-server');
assert.strictEqual(official.windows.length, 3);

// Today's events split into the two Cursor pools.
assert.strictEqual(isAutoModel('cursor-grok-4.6-xhigh-fast'), true);
assert.strictEqual(isAutoModel('claude-opus-5'), false);
const today = computeTodayUsage(
  [
    { model: 'claude-opus-5', chargedCents: 120 },
    { model: 'gpt-5.6-sol-high', chargedCents: 80 },
    { model: 'composer-2.5', chargedCents: 300 },
    { model: 'claude-opus-5', chargedCents: 999, kind: 'USAGE_EVENT_KIND_ERRORED_NOT_CHARGED' },
  ],
  undefined,
  25_000,
  300_000,
);
assert.strictEqual(today.api.usedCents, 200);
assert.strictEqual(today.api.events, 2);
assert.strictEqual(today.api.percentOfPool, 0.8);
assert.strictEqual(today.auto.usedCents, 300);
assert.strictEqual(today.auto.events, 1);
assert.strictEqual(today.auto.percentOfPool, 0.1);

// Codex daily ledger: only positive steps count, and a rolled window restarts.
const day = '2026-09-15T01:00:00.000Z';
const t0 = Date.parse(day);
let ledger = recordGptSample({ windowKey: day, percent: 37, resetAt: 'A', nowMs: t0 });
assert.strictEqual(ledger.percent, 0);
assert.strictEqual(ledger.partial, true, 'a fresh baseline can only be a lower bound');
ledger = recordGptSample({ windowKey: day, percent: 39, resetAt: 'A', nowMs: t0 + 60_000 });
assert.strictEqual(ledger.percent, 2);
ledger = recordGptSample({ windowKey: day, percent: 38, resetAt: 'A', nowMs: t0 + 120_000 });
assert.strictEqual(ledger.percent, 2, 'a decrease without a reset is not consumption');
ledger = recordGptSample({ windowKey: day, percent: 3, resetAt: 'B', nowMs: t0 + 180_000 });
assert.strictEqual(ledger.percent, 5, 'a rolled weekly window counts the new reading');
assert.strictEqual(readGptToday(day).percent, 5);
assert.strictEqual(readGptToday('2026-09-16T01:00:00.000Z').percent, null);

// Crossing 9:00 while sampling keeps the baseline, so the new day is exact.
const nextDay = '2026-09-16T01:00:00.000Z';
ledger = recordGptSample({ windowKey: nextDay, percent: 4, resetAt: 'B', nowMs: t0 + 240_000 });
assert.strictEqual(ledger.percent, 1);
assert.strictEqual(ledger.partial, false);

// A lapse longer than the continuity window cannot claim an exact day.
ledger = recordGptSample({
  windowKey: '2026-09-17T01:00:00.000Z',
  percent: 9,
  resetAt: 'B',
  nowMs: t0 + 3 * 3600_000,
});
assert.strictEqual(ledger.percent, 0);
assert.strictEqual(ledger.partial, true);

const ledgerFile = path.join(stateDir, 'codex-daily.json');
assert.strictEqual(fs.statSync(ledgerFile).mode & 0o777, 0o600);
const ledgerText = fs.readFileSync(ledgerFile, 'utf8');
assert(!/token|email|account/i.test(ledgerText), 'the ledger holds percentages only');

const redacted = redactPrivate({
  nested: { email: 'private@example.com', accessToken: 'secret' },
  text: 'Bearer abcdefghijklmnopqrstuvwxyz',
}, '');
assert.strictEqual(redacted.nested.email, '<redacted>');
assert.strictEqual(redacted.nested.accessToken, '<redacted>');
assert.strictEqual(redacted.text, '<redacted>');

const fetchedAt = '2026-09-07T01:00:00.000Z';
const publicJson = JSON.stringify(toPublicSnapshot({
  error: null,
  membershipType: 'ultra',
  todayUsage: today,
  gpt: {
    ok: true,
    percent: 1,
    transient: false,
    stale: false,
    fetchedAt,
    cycleStart: '2026-09-07T01:31:51+00:00',
    cycleEnd: '2026-10-07T01:31:51+00:00',
    accessToken: 'must-not-appear',
    accountId: 'must-not-appear',
    windows: legacy.windows,
  },
  gptToday: { percent: 2, partial: false },
}));
assert(!publicJson.includes('must-not-appear'));
assert(!publicJson.includes('accessToken'));
assert(!publicJson.includes('accountId'));
assert(!publicJson.includes('membershipType'));
const publicData = JSON.parse(publicJson);
assert.strictEqual(publicData.gptFetchedAt, fetchedAt);
assert.strictEqual(publicData.gptStale, false);
assert.strictEqual(publicData.gptCycleEnd, '2026-10-07T01:31:51+00:00');
assert.strictEqual(publicData.todayApiCents, 200);
assert.strictEqual(publicData.todayAutoEvents, 1);
assert.strictEqual(publicData.gptTodayPercent, 2);
assert.strictEqual(publicData.gptTodayPartial, false);

fs.rmSync(stateDir, { recursive: true, force: true });
console.log('All tests passed.');
