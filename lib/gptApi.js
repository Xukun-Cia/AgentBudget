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

function windowPercent(rateLimit) {
  const win = rateLimit && rateLimit.primary_window;
  if (!win || typeof win.used_percent !== 'number' || !Number.isFinite(win.used_percent)) {
    return null;
  }
  return win.used_percent;
}

function resetAtIso(rateLimit) {
  const win = rateLimit && rateLimit.primary_window;
  if (!win) return null;
  if (typeof win.reset_at === 'number' && Number.isFinite(win.reset_at)) {
    return new Date(win.reset_at * 1000).toISOString();
  }
  return null;
}

function extrasFromUsage(body) {
  const rows = [];
  const list = Array.isArray(body.additional_rate_limits) ? body.additional_rate_limits : [];
  for (const item of list) {
    const percent = windowPercent(item.rate_limit);
    if (percent == null) continue;
    const raw = item.limit_name || item.metered_feature || 'extra';
    rows.push({
      label: EXTRA_LABELS[raw] || String(raw),
      percent,
    });
  }
  return rows;
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

  const rate = usage.rate_limit || {};
  const primary = rate.primary_window || {};
  return {
    ok: true,
    error: null,
    plan: planLabel(usage.plan_type) || auth.plan,
    percent: windowPercent(rate),
    resetAt: resetAtIso(rate),
    windowSeconds: Number.isFinite(primary.limit_window_seconds)
      ? primary.limit_window_seconds
      : null,
    allowed: typeof rate.allowed === 'boolean' ? rate.allowed : null,
    limitReached: typeof rate.limit_reached === 'boolean' ? rate.limit_reached : null,
    cycleStart: auth.cycleStart,
    cycleEnd: auth.cycleEnd,
    extras: extrasFromUsage(usage),
  };
}

module.exports = { fetchGptPublic, planLabel };
