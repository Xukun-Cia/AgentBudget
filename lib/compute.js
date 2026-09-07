const { readTokenFromDb, fetchUsageData } = require('./cursorApi');
const { fetchGptPublic } = require('./gptApi');
const { calculateDailyBudget, getWorkdayTimeInfo } = require('./workdays');

const GPT_STALE_MAX_MS = 15 * 60 * 1000;

function coalesce(value, fallback) {
  return value !== undefined && value !== null ? value : fallback;
}

/** Keep a recent successful GPT reading across a transient failed refresh.
 * Authentication/configuration failures are never hidden, and stale readings
 * expire so the UI cannot present an old percentage indefinitely.
 */
function preserveLastGoodGpt(current, previous, nowMs) {
  const next = current || {};
  if (next.ok && Number.isFinite(next.percent)) {
    return { ...next, stale: false };
  }
  if (!next.transient || !previous || !previous.ok || !Number.isFinite(previous.percent)) {
    return next;
  }
  const fetchedMs = Date.parse(previous.fetchedAt || '');
  const clock = Number.isFinite(nowMs) ? nowMs : Date.now();
  if (!Number.isFinite(fetchedMs) || clock - fetchedMs > GPT_STALE_MAX_MS || clock < fetchedMs) {
    return next;
  }
  return {
    ...previous,
    ok: true,
    stale: true,
    transient: true,
    error: next.error || 'GPT 用量暂时刷新失败',
  };
}

function fetchAndCompute(options) {
  options = options || {};
  const refreshInterval = coalesce(options.refreshInterval, 60);
  const warningThreshold = coalesce(options.warningThreshold, 80);
  const criticalThreshold = coalesce(options.criticalThreshold, 95);

  return (async function () {
    let membershipType = 'unknown';
    let fetchError = null;
    let usageSource = null;
    let apiPercent = null;
    let resetDate = null;
    let summary = null;
    let todayApiUsage = null;

    try {
      const tokenResult = readTokenFromDb();
      if (tokenResult.error) {
        fetchError = tokenResult.error;
      } else {
        const usage = await fetchUsageData(
          tokenResult.sessionToken,
          tokenResult.userId,
          tokenResult.accessToken,
        );
        membershipType = usage.membershipType;
        usageSource = usage.usageSource;
        apiPercent = usage.apiUsedPercent;
        resetDate = usage.resetDate;
        summary = usage.summary;
        todayApiUsage = usage.todayApiUsage;

        if (usage.fetchErrors && usage.fetchErrors.length) {
          fetchError = usage.fetchErrors.join('; ');
        }
      }
    } catch (err) {
      fetchError = err.message || String(err);
    }

    const gpt = await fetchGptPublic().catch((err) => ({
      ok: false,
      error: err.message || String(err),
      plan: null,
      percent: null,
      resetAt: null,
      windowSeconds: null,
      allowed: null,
      limitReached: null,
      cycleStart: null,
      cycleEnd: null,
      source: null,
      windows: [],
      extras: [],
    }));

    if (!resetDate || apiPercent === null) {
      return {
        error: resetDate
          ? '无法获取 API 用量，请确认已登录 Cursor 并重试'
          : '无法获取计费周期/重置日，请确认已登录 Cursor 并重试',
        membershipType: membershipType,
        fetchError: fetchError,
        usageSource: usageSource,
        gpt: gpt,
        refreshInterval: refreshInterval,
        warningThreshold: warningThreshold,
        criticalThreshold: criticalThreshold,
      };
    }

    const cycleEnd = (summary && summary.billingCycleEnd != null)
      ? summary.billingCycleEnd
      : resetDate;
    const apiBudget = calculateDailyBudget(apiPercent, cycleEnd);
    const workdayTimeInfo = getWorkdayTimeInfo(new Date());

    return {
      resetDate: resetDate,
      membershipType: membershipType,
      apiPercent: apiPercent,
      apiBudget: apiBudget,
      summary: summary,
      todayApiUsage: todayApiUsage,
      fetchError: fetchError,
      usageSource: usageSource,
      workdayTimeInfo: workdayTimeInfo,
      gpt: gpt,
      refreshInterval: refreshInterval,
      warningThreshold: warningThreshold,
      criticalThreshold: criticalThreshold,
    };
  })();
}

/**
 * Public snapshot for the desktop app / stdout CLI.
 * First principle: never include token, userId, email, raw API bodies, or events.
 */
function toPublicSnapshot(data) {
  const s = data.summary || {};
  const t = data.todayApiUsage || {};
  const b = data.apiBudget || {};
  const workday = data.workdayTimeInfo || {};
  const g = data.gpt || {};

  return {
    ok: !data.error,
    error: data.error || null,
    fetchError: data.fetchError || null,
    remainingDays: Number.isFinite(b.remainingDays) ? b.remainingDays : null,
    apiPercent: Number.isFinite(data.apiPercent) ? data.apiPercent : null,
    todayPercent: Number.isFinite(t.percentOfPool) ? t.percentOfPool : null,
    todayCents: Number.isFinite(t.usedCents) ? t.usedCents : null,
    todayEvents: Number.isFinite(t.apiEvents) ? t.apiEvents : null,
    todayTruncated: Boolean(t.truncated),
    todayWindowStart: t.windowStart || null,
    todayWindowEnd: t.windowEnd || null,
    dailyBudget: Number.isFinite(b.dailyBudget) ? b.dailyBudget : null,
    isLastStretch: Boolean(b.isLastStretch),
    remainingPercent: Number.isFinite(b.remainingPercent) ? b.remainingPercent : null,
    membershipType: data.membershipType || 'unknown',
    apiUsedCents: Number.isFinite(s.apiUsedCents) ? s.apiUsedCents : null,
    apiLimitCents: Number.isFinite(s.apiLimitCents) ? s.apiLimitCents : null,
    autoPercent: Number.isFinite(s.autoPercentUsed) ? s.autoPercentUsed : null,
    autoUsedCents: Number.isFinite(s.autoUsedCents) ? s.autoUsedCents : null,
    autoLimitCents: Number.isFinite(s.autoLimitCents) ? s.autoLimitCents : null,
    includedUsedCents: Number.isFinite(s.includedUsedCents) ? s.includedUsedCents : null,
    includedLimitCents: Number.isFinite(s.includedLimitCents) ? s.includedLimitCents : null,
    bonusCents: Number.isFinite(s.includedBonusCents) ? s.includedBonusCents : null,
    cycleStart: s.billingCycleStart || null,
    cycleEnd: s.billingCycleEnd || data.resetDate || null,
    workdayLabel: workday.label || null,
    usageSource: data.usageSource || null,
    gptOk: Boolean(g.ok),
    gptError: g.error || null,
    gptTransient: Boolean(g.transient),
    gptStale: Boolean(g.stale),
    gptFetchedAt: g.fetchedAt || null,
    gptPlan: g.plan || null,
    gptPercent: Number.isFinite(g.percent) ? g.percent : null,
    gptResetAt: g.resetAt || null,
    gptWindowSeconds: Number.isFinite(g.windowSeconds) ? g.windowSeconds : null,
    gptAllowed: typeof g.allowed === 'boolean' ? g.allowed : null,
    gptLimitReached: typeof g.limitReached === 'boolean' ? g.limitReached : null,
    gptCycleStart: g.cycleStart || null,
    gptCycleEnd: g.cycleEnd || null,
    gptSource: g.source || null,
    gptWindows: Array.isArray(g.windows)
      ? g.windows
          .filter((row) => row && typeof row.label === 'string' && Number.isFinite(row.percent))
          .map((row) => ({
            label: String(row.label).slice(0, 48),
            group: typeof row.group === 'string' ? String(row.group).slice(0, 40) : null,
            kind: typeof row.kind === 'string' ? String(row.kind).slice(0, 24) : null,
            percent: row.percent,
            resetAt: row.resetAt || null,
            windowSeconds: Number.isFinite(row.windowSeconds) ? row.windowSeconds : null,
            limitReached: typeof row.limitReached === 'boolean' ? row.limitReached : null,
            isMain: Boolean(row.isMain),
          }))
      : [],
    gptExtras: Array.isArray(g.extras)
      ? g.extras
          .filter((row) => row && typeof row.label === 'string' && Number.isFinite(row.percent))
          .map((row) => ({
            label: String(row.label).slice(0, 48),
            percent: row.percent,
            resetAt: row.resetAt || null,
            windowSeconds: Number.isFinite(row.windowSeconds) ? row.windowSeconds : null,
            limitReached: typeof row.limitReached === 'boolean' ? row.limitReached : null,
          }))
      : [],
    refreshInterval: coalesce(data.refreshInterval, 60),
    warningThreshold: coalesce(data.warningThreshold, 80),
    criticalThreshold: coalesce(data.criticalThreshold, 95),
  };
}

module.exports = { fetchAndCompute, preserveLastGoodGpt, toPublicSnapshot };
