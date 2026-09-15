const { readTokenFromDb, fetchUsageData } = require('./cursorApi');
const { fetchGptPublic } = require('./gptApi');
const { recordGptSample, readGptToday } = require('./gptLedger');
const { getApiDayWindow } = require('./dayWindow');

function fetchAndCompute() {
  return (async function () {
    let membershipType = 'unknown';
    let fetchError = null;
    let usageSource = null;
    let apiPercent = null;
    let resetDate = null;
    let summary = null;
    let todayUsage = null;

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
        todayUsage = usage.todayUsage;

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
      transient: true,
      percent: null,
    }));

    // Codex reports a rolling window, so today's share only exists locally.
    const dayWindow = getApiDayWindow(new Date());
    const dayKey = dayWindow.start.toISOString();
    const gptToday = gpt.ok && Number.isFinite(gpt.percent)
      ? recordGptSample({ windowKey: dayKey, percent: gpt.percent, resetAt: gpt.resetAt })
      : readGptToday(dayKey);

    if (!resetDate || apiPercent === null) {
      return {
        error: resetDate
          ? '无法获取 API 用量，请确认已登录 Cursor 并重试'
          : '无法获取计费周期/重置日，请确认已登录 Cursor 并重试',
        membershipType: membershipType,
        fetchError: fetchError,
        usageSource: usageSource,
        gpt: gpt,
        gptToday: gptToday,
      };
    }

    return {
      resetDate: resetDate,
      membershipType: membershipType,
      apiPercent: apiPercent,
      summary: summary,
      todayUsage: todayUsage,
      fetchError: fetchError,
      usageSource: usageSource,
      gpt: gpt,
      gptToday: gptToday,
    };
  })();
}

function numberOrNull(value) {
  return Number.isFinite(value) ? value : null;
}

/**
 * Public snapshot for the desktop app / stdout CLI.
 * First principle: never include token, userId, email, raw API bodies, or events.
 */
function toPublicSnapshot(data) {
  const s = data.summary || {};
  const today = data.todayUsage || {};
  const todayApi = today.api || {};
  const todayAuto = today.auto || {};
  const g = data.gpt || {};
  const gToday = data.gptToday || {};

  return {
    ok: !data.error,
    error: data.error || null,
    fetchError: data.fetchError || null,
    usageSource: data.usageSource || null,
    apiPercent: numberOrNull(data.apiPercent),
    apiUsedCents: numberOrNull(s.apiUsedCents),
    apiLimitCents: numberOrNull(s.apiLimitCents),
    autoPercent: numberOrNull(s.autoPercentUsed),
    autoUsedCents: numberOrNull(s.autoUsedCents),
    autoLimitCents: numberOrNull(s.autoLimitCents),
    todayApiPercent: numberOrNull(todayApi.percentOfPool),
    todayApiCents: numberOrNull(todayApi.usedCents),
    todayApiEvents: numberOrNull(todayApi.events),
    todayAutoPercent: numberOrNull(todayAuto.percentOfPool),
    todayAutoCents: numberOrNull(todayAuto.usedCents),
    todayAutoEvents: numberOrNull(todayAuto.events),
    todayTruncated: Boolean(today.truncated),
    todayWindowStart: today.windowStart || null,
    todayWindowEnd: today.windowEnd || null,
    cycleStart: s.billingCycleStart || null,
    cycleEnd: s.billingCycleEnd || data.resetDate || null,
    gptOk: Boolean(g.ok),
    gptError: g.error || null,
    gptTransient: Boolean(g.transient),
    gptStale: Boolean(g.stale),
    gptFetchedAt: g.fetchedAt || null,
    gptPlan: g.plan || null,
    gptPercent: numberOrNull(g.percent),
    gptResetAt: g.resetAt || null,
    gptLimitReached: typeof g.limitReached === 'boolean' ? g.limitReached : null,
    gptCycleStart: g.cycleStart || null,
    gptCycleEnd: g.cycleEnd || null,
    gptTodayPercent: numberOrNull(gToday.percent),
    gptTodayPartial: Boolean(gToday.partial),
  };
}

module.exports = { fetchAndCompute, toPublicSnapshot };
