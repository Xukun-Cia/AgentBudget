/**
 * Parse usage data and build status bar tooltips.
 */

const { formatDate, parseResetInstant } = require('./workdays');

/**
 * Fallback pool sizes when official spend + percents cannot be inverted.
 *
 * Ultra (2026-08, inverted from planUsage.totalSpend / totalPercentUsed):
 *   Other Models (API)  $500
 *   Cursor Models (Auto)$3000
 *   Total               $3500
 *
 * Prefer inferPoolLimitsFromSpend() — hardcoded values go stale.
 * plan.limit / includedAmountCents ($400 on Ultra) is the purchased
 * included allowance, not the % bar denominator.
 */
const PLAN_POOL_LIMITS = {
  ultra: { apiLimitCents: 50_000, autoLimitCents: 300_000 },
  // Docs: Other Models included; Auto not published — omit Auto dollars.
  'pro+': { apiLimitCents: 7_000 },
  pro_plus: { apiLimitCents: 7_000 },
  pro: { apiLimitCents: 2_000 },
};

/**
 * Invert % bar denominators from official spend + three percents:
 *   totalLimit = totalSpend / (totalPercent/100)
 *   apiUsed + autoUsed = totalSpend
 *   apiUsed = apiPercent/100 * apiLimit
 *   autoUsed = autoPercent/100 * autoLimit
 *   apiLimit + autoLimit = totalLimit
 */
function inferPoolLimitsFromSpend(summary) {
  if (!summary) return null;
  const totalSpend = summary.totalSpendCents;
  const apiPct = summary.apiUsedPercent;
  const autoPct = summary.autoPercentUsed;
  const totalPct = summary.totalPercentUsed;
  if (!(totalSpend > 0) || !(totalPct > 0)) return null;
  if (apiPct == null || autoPct == null) return null;
  if (!Number.isFinite(totalSpend) || !Number.isFinite(apiPct) || !Number.isFinite(autoPct) || !Number.isFinite(totalPct)) {
    return null;
  }

  const totalLimitCents = totalSpend / (totalPct / 100);
  const a = apiPct / 100;
  const b = autoPct / 100;
  if (!Number.isFinite(totalLimitCents) || totalLimitCents <= 0) return null;
  if (Math.abs(a - b) < 1e-12) return null;

  const apiLimitCents = (totalSpend - b * totalLimitCents) / (a - b);
  const autoLimitCents = totalLimitCents - apiLimitCents;
  if (!(apiLimitCents > 0) || !(autoLimitCents > 0)) return null;
  if (!Number.isFinite(apiLimitCents) || !Number.isFinite(autoLimitCents)) return null;

  return {
    apiLimitCents,
    autoLimitCents,
    totalLimitCents,
  };
}

/** Snap to the nearest $1; if within $5 of a $100 boundary, snap there. */
function snapLimitCents(cents) {
  const dollars = cents / 100;
  const nearestHundred = Math.round(dollars / 100) * 100;
  if (nearestHundred > 0 && Math.abs(dollars - nearestHundred) < 5) {
    return nearestHundred * 100;
  }
  return Math.round(dollars) * 100;
}

function centsToDollars(cents) {
  if (typeof cents !== 'number' || !Number.isFinite(cents)) return null;
  return cents / 100;
}

function formatDollars(cents) {
  const d = centsToDollars(cents);
  if (d === null) return '—';
  return `$${d.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatDollarsFromPercent(percent, limitCents) {
  if (percent == null || limitCents == null) return '—';
  const used = (percent / 100) * limitCents;
  return `${formatDollars(used)} / ${formatDollars(limitCents)}`;
}

const TOOLTIP_LABEL_WIDTH = 6;

/** Fine-tune separator alignment for Latin labels vs CJK rows. */
const LABEL_PAD_ADJUST = {
  API: 1,
  Auto: -1,
};

/** Display width for mixed CJK / Latin (CJK counts as 2). */
function displayWidth(str) {
  let w = 0;
  for (const ch of str) {
    const code = ch.codePointAt(0);
    if (
      code > 0xff
      || (code >= 0x2e80 && code <= 0x9fff)
      || (code >= 0xf900 && code <= 0xfaff)
      || (code >= 0xff00 && code <= 0xffef)
    ) {
      w += 2;
    } else {
      w += 1;
    }
  }
  return w;
}

function tooltipRow(label, value) {
  const adjust = LABEL_PAD_ADJUST[label] || 0;
  const pad = Math.max(1, TOOLTIP_LABEL_WIDTH - displayWidth(label) + adjust);
  return `${label}${' '.repeat(pad)}│ ${value}`;
}

function applyPoolLimits(summary, membershipType) {
  if (!summary) return summary;

  const key = (membershipType || summary.membershipType || '').toLowerCase();
  const fallback = PLAN_POOL_LIMITS[key] || {};
  const inferred = inferPoolLimitsFromSpend(summary);

  let apiLimitCents = fallback.apiLimitCents;
  let autoLimitCents = fallback.autoLimitCents;
  let totalLimitCents = null;
  let poolLimitsSource = fallback.apiLimitCents != null ? 'fallback' : null;

  if (inferred) {
    apiLimitCents = snapLimitCents(inferred.apiLimitCents);
    autoLimitCents = snapLimitCents(inferred.autoLimitCents);
    totalLimitCents = apiLimitCents + autoLimitCents;
    poolLimitsSource = 'inferred';
  } else if (apiLimitCents != null && autoLimitCents != null) {
    totalLimitCents = apiLimitCents + autoLimitCents;
  }

  summary.poolLimitsSource = poolLimitsSource;

  if (summary.apiUsedPercent != null && apiLimitCents != null) {
    summary.apiLimitCents = apiLimitCents;
    summary.apiUsedCents = (summary.apiUsedPercent / 100) * apiLimitCents;
    summary.apiRemainingCents = apiLimitCents - summary.apiUsedCents;
  }

  if (summary.autoPercentUsed != null && autoLimitCents != null) {
    summary.autoLimitCents = autoLimitCents;
    summary.autoUsedCents = (summary.autoPercentUsed / 100) * autoLimitCents;
    summary.autoRemainingCents = autoLimitCents - summary.autoUsedCents;
  }

  if (totalLimitCents != null) {
    summary.totalLimitCents = totalLimitCents;
    if (summary.totalPercentUsed != null) {
      summary.totalUsedCents = (summary.totalPercentUsed / 100) * totalLimitCents;
    }
  }

  return summary;
}

function parseUsageSummaryRich(summary) {
  if (!summary || typeof summary !== 'object') return null;

  const individual = summary.individualUsage || {};
  const team = summary.teamUsage || {};
  const plan = individual.plan || team.plan || null;
  const onDemand = individual.onDemand || team.onDemand || null;
  const breakdown = plan && plan.breakdown ? plan.breakdown : {};

  let apiUsedPercent = plan && plan.apiPercentUsed != null ? plan.apiPercentUsed : null;
  if (apiUsedPercent === null && plan && plan.limit > 0 && typeof plan.used === 'number') {
    apiUsedPercent = (plan.used / plan.limit) * 100;
  }

  const billingCycleEnd = summary.billingCycleEnd || null;
  const resetInstant = billingCycleEnd ? parseResetInstant(billingCycleEnd) : null;
  const resetDate = resetInstant ? formatDate(resetInstant) : null;

  const membershipType = summary.membershipType || null;

  const base = {
    apiUsedPercent: apiUsedPercent,
    autoPercentUsed: plan && plan.autoPercentUsed != null ? plan.autoPercentUsed : null,
    totalPercentUsed: plan && plan.totalPercentUsed != null ? plan.totalPercentUsed : null,
    resetDate: resetDate,
    billingCycleStart: summary.billingCycleStart || null,
    billingCycleEnd: billingCycleEnd,
    membershipType: membershipType,
    // Purchased included allowance (Ultra $400); distinct from % pool sizes.
    includedLimitCents: plan && plan.limit != null ? plan.limit : null,
    includedUsedCents: plan && plan.used != null ? plan.used : null,
    includedBonusCents: breakdown.bonus != null ? breakdown.bonus : null,
    // Same accounting as planUsage.totalSpend (included + bonus).
    totalSpendCents: breakdown.total != null ? breakdown.total : null,
    onDemandEnabled: onDemand && onDemand.enabled != null ? onDemand.enabled : false,
    onDemandUsedCents: onDemand && onDemand.used != null ? onDemand.used : null,
    autoMessage: summary.autoModelSelectedDisplayMessage || '',
    apiMessage: summary.namedModelSelectedDisplayMessage || '',
    isUnlimited: summary.isUnlimited != null ? summary.isUnlimited : false,
  };

  return applyPoolLimits(base, membershipType);
}

/**
 * Fallback Cursor Models (first-party) bucket when Connect RPC autoBucketModels
 * is unavailable or stale. Official lists lag new Grok versions (e.g. 4.6);
 * isAutoModel also matches first-party families, not just this list.
 */
const DEFAULT_AUTO_BUCKET_MODELS = [
  'default',
  'composer-1',
  'composer-1-alpha',
  'composer-1.5',
  'composer-1.5-auto',
  'composer-2',
  'composer-2-fast',
  'composer-2.5',
  'composer-2.5-fast',
  'vega',
  'vega-medium',
  'vega-high',
  'vega-xhigh',
  'vega-fast-medium',
  'vega-fast-high',
  'vega-fast-xhigh',
  'grok-4.5',
  'cursor-grok-4.5',
  'grok-4.5-medium',
  'grok-4.5-fast-medium',
  'grok-4.5-high',
  'grok-4.5-fast-high',
  'grok-4.5-xhigh',
  'grok-4.5-fast-xhigh',
  // Connect RPC IDs (cursor- prefix + low/medium/high ordering)
  'cursor-grok-4.5-low',
  'cursor-grok-4.5-low-fast',
  'cursor-grok-4.5-medium',
  'cursor-grok-4.5-medium-fast',
  'cursor-grok-4.5-high',
  'cursor-grok-4.5-high-fast',
  'grok-4.6',
  'grok-4.6-medium',
  'grok-4.6-fast-medium',
  'grok-4.6-high',
  'grok-4.6-fast-high',
  'grok-4.6-xhigh',
  'grok-4.6-fast-xhigh',
  'cursor-grok-4.6-low',
  'cursor-grok-4.6-low-fast',
  'cursor-grok-4.6-medium',
  'cursor-grok-4.6-medium-fast',
  'cursor-grok-4.6-high',
  'cursor-grok-4.6-high-fast',
  'cursor-grok-4.6-xhigh',
  'cursor-grok-4.6-xhigh-fast',
];

/** Strip Cursor event prefix and lowercase for stable comparisons. */
function normalizeModelId(model) {
  return String(model).trim().toLowerCase().replace(/^cursor-/, '');
}

/**
 * Canonical token signature so event/bucket ID reorderings match.
 * e.g. cursor-grok-4.5-high-fast ↔ grok-4.5-fast-high
 */
function modelTokenSignature(model) {
  return normalizeModelId(model).split('-').filter(Boolean).sort().join('\0');
}

/** First-party Grok IDs: grok-4.5, grok-4.6-xhigh-fast, cursor-grok-4.6-… */
const GROK_FAMILY_RE = /^grok-\d+\.\d+(?:-|$)/;

/**
 * True if the usage-event model draws from the Cursor Models pool
 * (Auto / Composer / Grok / Vega), not the Other Models (API) pool.
 */
function isAutoModel(model, autoBucketModels = DEFAULT_AUTO_BUCKET_MODELS) {
  if (!model) return false;

  const normalized = normalizeModelId(model);
  const bucket = autoBucketModels || DEFAULT_AUTO_BUCKET_MODELS;

  if (bucket.includes(model) || bucket.includes(normalized)) return true;

  // Known Cursor Models families (covers stale/partial official bucket lists)
  if (normalized === 'default') return true;
  if (normalized.startsWith('composer-')) return true;
  if (normalized === 'vega' || normalized.startsWith('vega-')) return true;
  if (GROK_FAMILY_RE.test(normalized)) return true;

  // Soft-match when event IDs reorder tier/speed vs Connect bucket IDs
  const eventSig = modelTokenSignature(model);
  for (const id of bucket) {
    if (modelTokenSignature(id) === eventSig) return true;
  }

  return false;
}

const SKIPPED_USAGE_EVENT_KINDS = new Set([
  'USAGE_EVENT_KIND_ERRORED_NOT_CHARGED',
  'USAGE_EVENT_KIND_FREE_CREDIT',
  'USAGE_EVENT_KIND_USER_API_KEY',
]);

function shouldSkipUsageEvent(event) {
  return SKIPPED_USAGE_EVENT_KINDS.has(event && event.kind);
}

function eventCostCents(event) {
  const token = event.tokenUsage || {};
  if (event.chargedCents != null) return event.chargedCents;
  if (token.totalCents != null) return token.totalCents;
  return 0;
}

/** Sum API-pool spend for events in [windowStart, windowEnd). */
function computeTodayApiUsage(events, autoBucketModels, apiLimitCents) {
  let usedCents = 0;
  let apiEvents = 0;

  for (const event of events) {
    if (shouldSkipUsageEvent(event)) continue;
    if (isAutoModel(event.model, autoBucketModels)) continue;
    usedCents += eventCostCents(event);
    apiEvents += 1;
  }

  const percentOfPool = apiLimitCents > 0
    ? (usedCents / apiLimitCents) * 100
    : null;

  return {
    usedCents: Math.round(usedCents * 100) / 100,
    apiEvents,
    percentOfPool: percentOfPool != null ? Math.round(percentOfPool * 100) / 100 : null,
  };
}

function formatTodayUsageStatusBar(todayApiUsage) {
  if (!todayApiUsage || todayApiUsage.percentOfPool == null) return '今日 —';
  return `今日 ${fmtPct(todayApiUsage.percentOfPool)}`;
}

function buildTooltipLines(data) {
  const lines = [];
  const s = data.summary;

  lines.push(tooltipRow('Plan', data.membershipType));

  if (s && s.apiLimitCents != null) {
    lines.push(tooltipRow('API', `${formatDollarsFromPercent(data.apiPercent, s.apiLimitCents)}（Other Models）`));
  } else {
    lines.push(tooltipRow('API', fmtPct(data.apiPercent)));
  }

  if (s && s.autoLimitCents != null) {
    lines.push(tooltipRow('Auto', `${formatDollarsFromPercent(s.autoPercentUsed, s.autoLimitCents)}（Cursor Models）`));
  } else if (s && s.autoPercentUsed != null) {
    lines.push(tooltipRow('Auto', fmtPct(s.autoPercentUsed)));
  }

  if (s && s.includedLimitCents != null) {
    const included = `${formatDollars(s.includedUsedCents)} / ${formatDollars(s.includedLimitCents)}`;
    const bonus = s.includedBonusCents
      ? ` · bonus ${formatDollars(s.includedBonusCents)}`
      : '';
    lines.push(tooltipRow('套餐', `${included}${bonus}`));
  }

  if (s && s.billingCycleStart && s.billingCycleEnd) {
    lines.push(tooltipRow('周期', `${formatDateTime(s.billingCycleStart)} → ${formatDateTime(s.billingCycleEnd)}`));
  } else {
    const budget = data.apiBudget || {};
    const resetLabel = budget.resetAt
      ? formatDateTime(budget.resetAt)
      : data.resetDate || '—';
    lines.push(tooltipRow('重置', resetLabel));
  }

  lines.push(tooltipRow('用量', `API ${fmtPct(data.apiPercent)} · Auto ${fmtPct(s && s.autoPercentUsed)} · 总 ${fmtPct(s && s.totalPercentUsed)}`));

  if (data.todayApiUsage) {
    const t = data.todayApiUsage;
    const pct = t.percentOfPool != null ? fmtPct(t.percentOfPool) : '—';
    const trunc = t.truncated ? ' · 事件可能未拉全' : '';
    lines.push(tooltipRow('今日', `${formatDollars(t.usedCents)} · ${pct}（9:00→9:00）${trunc}`));
  }

  const gpt = data.gpt || {};
  if (gpt.ok) {
    const reset = gpt.resetAt ? formatDateTime(gpt.resetAt) : '—';
    lines.push(tooltipRow('GPT', `${gpt.plan || '—'} · 周限 ${fmtPct(gpt.percent)} · 重置 ${reset}`));
    if (gpt.cycleStart && gpt.cycleEnd) {
      lines.push(tooltipRow('GPT周期', `${formatDateTime(gpt.cycleStart)} → ${formatDateTime(gpt.cycleEnd)}`));
    }
  } else if (gpt.error) {
    lines.push(tooltipRow('GPT', gpt.error));
  }

  const workday = formatWorkdayFooter(data.workdayTimeInfo);
  lines.push(tooltipRow('刷新', `${data.refreshInterval}s · ${workday}`));

  if (data.fetchError) {
    lines.push('');
    lines.push(`⚠ ${data.fetchError}`);
  }

  return lines.join('\n');
}

function formatWorkdayFooter(info) {
  if (!info || !info.label) return '—';
  const m = info.label.match(/^(\d{2}:\d{2}:\d{2})（(.+)）$/);
  if (m) return `${m[1]}（${m[2]}）`;
  return info.label;
}

function fmtPct(v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return `${v.toFixed(2)}%`;
}

function formatDateTime(iso) {
  try {
    return new Date(iso).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return String(iso);
  }
}

module.exports = {
  parseUsageSummaryRich,
  applyPoolLimits,
  inferPoolLimitsFromSpend,
  computeTodayApiUsage,
  isAutoModel,
  shouldSkipUsageEvent,
  buildTooltipLines,
  formatDollars,
  formatTodayUsageStatusBar,
  fmtPct,
  DEFAULT_AUTO_BUCKET_MODELS,
  PLAN_POOL_LIMITS,
  SKIPPED_USAGE_EVENT_KINDS,
};
