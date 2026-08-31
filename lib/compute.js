const { readTokenFromDb, fetchUsageData } = require('./cursorApi');
const { calculateDailyBudget, getWorkdayTimeInfo } = require('./workdays');

function fetchAndCompute(options = {}) {
  const refreshInterval = options.refreshInterval ?? 60;
  const warningThreshold = options.warningThreshold ?? 80;
  const criticalThreshold = options.criticalThreshold ?? 95;

  return (async () => {
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

        if (usage.fetchErrors?.length) {
          fetchError = usage.fetchErrors.join('; ');
        }
      }
    } catch (err) {
      fetchError = err.message || String(err);
    }

    if (!resetDate || apiPercent === null) {
      return {
        error: resetDate
          ? '无法获取 API 用量，请确认已登录 Cursor 并重试'
          : '无法获取计费周期/重置日，请确认已登录 Cursor 并重试',
        membershipType,
        fetchError,
        usageSource,
        refreshInterval,
        warningThreshold,
        criticalThreshold,
      };
    }

    const cycleEnd = summary?.billingCycleEnd ?? resetDate;
    const apiBudget = calculateDailyBudget(apiPercent, cycleEnd);
    const workdayTimeInfo = getWorkdayTimeInfo(new Date());

    return {
      resetDate,
      membershipType,
      apiPercent,
      apiBudget,
      summary,
      todayApiUsage,
      fetchError,
      usageSource,
      workdayTimeInfo,
      refreshInterval,
      warningThreshold,
      criticalThreshold,
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
    workdayLabel: data.workdayTimeInfo?.label || null,
    usageSource: data.usageSource || null,
    refreshInterval: data.refreshInterval ?? 60,
    warningThreshold: data.warningThreshold ?? 80,
    criticalThreshold: data.criticalThreshold ?? 95,
  };
}

module.exports = { fetchAndCompute, toPublicSnapshot };
