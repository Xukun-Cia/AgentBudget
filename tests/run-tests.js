#!/usr/bin/env node
const assert = require('assert');
const { parseUsagePayload } = require('../lib/gptApi');
const { fmtGptPct } = require('../lib/usageDetails');
const { toPublicSnapshot } = require('../lib/compute');
const { redactPrivate } = require('../lib/privacy');

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
assert(legacy.windows.some((row) => row.label === 'Codex Spark 5 小时额度'));

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

assert.strictEqual(fmtGptPct(0), '0%');
assert.strictEqual(fmtGptPct(1), '1%');
assert.strictEqual(fmtGptPct(1.5), '1.5%');
assert.strictEqual(fmtGptPct(1.25), '1.25%');

const redacted = redactPrivate({
  nested: { email: 'private@example.com', accessToken: 'secret' },
  text: 'Bearer abcdefghijklmnopqrstuvwxyz',
}, '');
assert.strictEqual(redacted.nested.email, '<redacted>');
assert.strictEqual(redacted.nested.accessToken, '<redacted>');
assert.strictEqual(redacted.text, '<redacted>');

const publicJson = JSON.stringify(toPublicSnapshot({
  error: null,
  membershipType: 'ultra',
  gpt: {
    ok: true,
    percent: 1,
    accessToken: 'must-not-appear',
    accountId: 'must-not-appear',
    windows: legacy.windows,
  },
}));
assert(!publicJson.includes('must-not-appear'));
assert(!publicJson.includes('accessToken'));
assert(!publicJson.includes('accountId'));

console.log('All tests passed.');
