/**
 * Read ChatGPT / GPT App login on this machine and fetch a sanitized usage snapshot.
 * Never prints tokens, emails, user IDs, or raw API bodies.
 */
const fs = require('fs');
const https = require('https');
const os = require('os');
const path = require('path');

const AUTH_PATH = path.join(os.homedir(), '.codex', 'auth.json');

const PLAN_LABELS = {
  pro: 'Pro',
  plus: 'Plus',
  free: 'Free',
  team: 'Team',
  enterprise: 'Enterprise',
  business: 'Business',
  edu: 'Edu',
};

const EXTRA_LABELS = {
  'GPT-5.3-Codex-Spark': 'Codex Spark',
  'gpt-reserve': 'Reserve',
};

function authPath() {
  return process.env.CURSORBUDGET_GPT_AUTH || AUTH_PATH;
}

function jwtPayload(token) {
  if (!token || typeof token !== 'string') return null;
  const part = token.split('.')[1];
  if (!part) return null;
  try {
    const json = Buffer.from(part.replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8');
    return JSON.parse(json);
  } catch {
    return null;
  }
}

function planLabel(raw) {
  if (!raw) return null;
  const key = String(raw).toLowerCase();
  return PLAN_LABELS[key] || String(raw);
}

function readGptAuth() {
  const file = authPath();
  if (!fs.existsSync(file)) {
    return { error: '未找到 GPT App 登录态（请先打开并登录官方 GPT 应用）' };
  }
  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return { error: 'GPT 登录文件无法读取' };
  }
  const tokens = parsed.tokens || {};
  const access = tokens.access_token;
  if (!access) {
    return { error: 'GPT 登录态里没有 access token' };
  }
  const claims = jwtPayload(tokens.id_token) || {};
  const authClaims = claims['https://api.openai.com/auth'] || {};
  return {
    accessToken: access,
    accountId: tokens.account_id || authClaims.chatgpt_account_id || '',
    plan: planLabel(authClaims.chatgpt_plan_type),
    cycleStart: authClaims.chatgpt_subscription_active_start || null,
    cycleEnd: authClaims.chatgpt_subscription_active_until || null,
  };
}

function gptRequest(urlPath, accessToken, accountId) {
  return new Promise((resolve, reject) => {
    const headers = {
      Authorization: `Bearer ${accessToken}`,
      Accept: 'application/json',
      'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
      Origin: 'https://chatgpt.com',
      Referer: 'https://chatgpt.com/',
    };
    if (accountId) {
      headers['ChatGPT-Account-Id'] = accountId;
    }
    const req = https.request(
      {
        hostname: 'chatgpt.com',
        path: urlPath,
        method: 'GET',
        headers,
      },
      (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            try {
              resolve(JSON.parse(data));
            } catch {
              reject(new Error('GPT 用量响应不是 JSON'));
            }
            return;
          }
          if (res.statusCode === 401 || res.statusCode === 403) {
            reject(new Error('GPT 登录已过期，请打开 GPT App 再登录一次'));
            return;
          }
          reject(new Error(`GPT 用量 HTTP ${res.statusCode}`));
        });
      },
    );
    req.on('error', (err) => reject(new Error(err.message || String(err))));
    req.setTimeout(20000, () => {
      req.destroy();
      reject(new Error('GPT 用量请求超时'));
    });
    req.end();
  });
}

function finiteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function resetIso(value) {
  const seconds = finiteNumber(value);
  if (seconds == null) return null;
  try {
    return new Date(seconds * 1000).toISOString();
  } catch (_) {
    return null;
  }
}

function normalizeWindow(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const percent = finiteNumber(
    raw.usedPercent != null ? raw.usedPercent : raw.used_percent,
  );
  if (percent == null) return null;
  const minutes = finiteNumber(raw.windowDurationMins);
  const legacySeconds = finiteNumber(raw.limit_window_seconds);
  const windowSeconds = minutes != null ? minutes * 60 : legacySeconds;
  const resetAt = resetIso(raw.resetsAt != null ? raw.resetsAt : raw.reset_at);
  return { percent, resetAt, windowSeconds };
}

function windowKind(seconds) {
  if (!(seconds > 0)) return '限额';
  if (seconds >= 6 * 86400) return '周额度';
  if (seconds >= 3600) {
    const hours = Math.round(seconds / 3600);
    return `${hours} 小时额度`;
  }
  return '短时额度';
}

function displayGroupLabel(raw, fallback) {
  if (!raw) return fallback;
  return EXTRA_LABELS[raw] || String(raw);
}

function addGroupWindows(rows, options) {
  const rate = options.rate || {};
  const candidates = [
    rate.primary || rate.primary_window,
    rate.secondary || rate.secondary_window,
  ];
  for (const raw of candidates) {
    const win = normalizeWindow(raw);
    if (!win) continue;
    const kind = windowKind(win.windowSeconds);
    const prefix = options.mainGroup ? 'GPT' : options.label;
    rows.push({
      label: `${prefix} ${kind}`,
      group: options.label,
      groupKey: options.groupKey,
      mainGroup: Boolean(options.mainGroup),
      kind,
      percent: win.percent,
      resetAt: win.resetAt,
      windowSeconds: win.windowSeconds,
      limitReached: typeof rate.limitReached === 'boolean'
        ? rate.limitReached
        : (typeof rate.limit_reached === 'boolean' ? rate.limit_reached : null),
    });
  }
}

function chooseMainWindow(windows) {
  const base = windows.filter((row) => row.mainGroup);
  const candidates = base.length ? base : windows;
  if (!candidates.length) return null;
  const weekly = candidates.filter((row) => row.windowSeconds >= 6 * 86400);
  const pool = weekly.length ? weekly : candidates;
  return pool.slice().sort((a, b) => (b.windowSeconds || 0) - (a.windowSeconds || 0))[0];
}

function parseLegacyUsage(body, auth) {
  const windows = [];
  addGroupWindows(windows, {
    rate: body.rate_limit || {},
    label: 'GPT',
    groupKey: 'codex',
    mainGroup: true,
  });
  const list = Array.isArray(body.additional_rate_limits) ? body.additional_rate_limits : [];
  for (const item of list) {
    const rawLabel = item.limit_name || item.metered_feature || 'extra';
    addGroupWindows(windows, {
      rate: item.rate_limit || {},
      label: displayGroupLabel(rawLabel, '额外限额'),
      groupKey: String(rawLabel),
      mainGroup: false,
    });
  }
  const main = chooseMainWindow(windows);
  const rate = body.rate_limit || {};
  return {
    plan: planLabel(body.plan_type) || auth.plan,
    windows,
    main,
    allowed: typeof rate.allowed === 'boolean' ? rate.allowed : null,
    limitReached: typeof rate.limit_reached === 'boolean' ? rate.limit_reached : null,
    source: 'chatgpt-usage',
  };
}

function parseOfficialUsage(body, auth) {
  const windows = [];
  const groups = body.rateLimitsByLimitId && typeof body.rateLimitsByLimitId === 'object'
    ? body.rateLimitsByLimitId
    : null;
  const entries = groups
    ? Object.keys(groups).map((key) => [key, groups[key]])
    : [['codex', body.rateLimits || {}]];
  let plan = auth.plan;
  for (const pair of entries) {
    const key = pair[0];
    const rate = pair[1] || {};
    const mainGroup = key === 'codex' || rate.limitId === 'codex';
    const rawLabel = rate.limitName || rate.limit_name || key;
    const label = mainGroup ? 'GPT' : displayGroupLabel(rawLabel, String(rawLabel));
    addGroupWindows(windows, { rate, label, groupKey: key, mainGroup });
    if (!plan && rate.planType) plan = planLabel(rate.planType);
  }
  const main = chooseMainWindow(windows);
  const mainPair = main ? entries.find((pair) => pair[0] === main.groupKey) : null;
  const base = body.rateLimits || (mainPair ? mainPair[1] : null) || {};
  return {
    plan,
    windows,
    main,
    allowed: typeof base.allowed === 'boolean' ? base.allowed : null,
    limitReached: base.rateLimitReachedType != null,
    source: 'codex-app-server',
  };
}

function parseUsagePayload(body, auth) {
  const safeAuth = auth || {};
  if (body && (body.rateLimits || body.rateLimitsByLimitId)) {
    return parseOfficialUsage(body, safeAuth);
  }
  return parseLegacyUsage(body || {}, safeAuth);
}

function emptyGpt(error) {
  return {
    ok: false,
    error: error || '无法读取 GPT 用量',
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
  };
}

async function fetchGptPublic() {
  const auth = readGptAuth();
  if (auth.error) return emptyGpt(auth.error);

  let usage;
  try {
    usage = await gptRequest('/backend-api/wham/usage', auth.accessToken, auth.accountId);
  } catch (err) {
    const failed = emptyGpt(err.message || String(err));
    failed.plan = auth.plan;
    failed.cycleStart = auth.cycleStart;
    failed.cycleEnd = auth.cycleEnd;
    return failed;
  }

  const parsed = parseUsagePayload(usage, auth);
  const main = parsed.main;
  return {
    ok: true,
    error: null,
    plan: parsed.plan,
    percent: main ? main.percent : null,
    resetAt: main ? main.resetAt : null,
    windowSeconds: main ? main.windowSeconds : null,
    allowed: parsed.allowed,
    limitReached: parsed.limitReached,
    cycleStart: auth.cycleStart,
    cycleEnd: auth.cycleEnd,
    source: parsed.source,
    windows: parsed.windows.map((row) => ({ ...row, isMain: row === main })),
    extras: parsed.windows.filter((row) => row !== main),
  };
}

module.exports = { fetchGptPublic, parseUsagePayload, planLabel, windowKind };
