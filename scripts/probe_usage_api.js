#!/usr/bin/env node
/**
 * Local debug probe for Cursor usage APIs.
 * Writes only under ~/.config/cursorbudget/debug/ — never into the repo.
 * Does not print tokens, emails, or full response bodies to stdout.
 */
const { execFileSync } = require('child_process');
const https = require('https');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { redactPrivate, secureWriteJson } = require('../lib/privacy');

function debugDir() {
  const dir = path.join(os.homedir(), '.config', 'cursorbudget', 'debug');
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  try { fs.chmodSync(dir, 0o700); } catch (_) {}
  return dir;
}

function readToken() {
  const db = path.join(os.homedir(), '.config', 'Cursor', 'User', 'globalStorage', 'state.vscdb');
  const script = `
import sqlite3, json, base64
conn = sqlite3.connect(${JSON.stringify(db)})
cur = conn.cursor()
cur.execute("SELECT value FROM ItemTable WHERE key='cursorAuth/accessToken'")
row = cur.fetchone()
raw = row[0]
payload = json.loads(base64.urlsafe_b64decode(raw.split('.')[1] + '=='))
uid = payload['sub'].split('|')[1]
print(json.dumps({"userId": uid, "jwt": raw, "session": uid + "%3A%3A" + raw}))
`;
  return JSON.parse(execFileSync('python3', ['-c', script], { encoding: 'utf-8' }));
}

function req(url, headers, method = 'GET', body = null) {
  return new Promise((resolve) => {
    const u = new URL(url);
    const opts = { hostname: u.hostname, path: u.pathname + u.search, method, headers };
    const r = https.request(opts, (res) => {
      let d = '';
      res.on('data', (c) => (d += c));
      res.on('end', () => {
        let parsed = d;
        try { parsed = JSON.parse(d); } catch (_) {}
        resolve({ status: res.statusCode, body: parsed });
      });
    });
    r.on('error', (e) => resolve({ status: 0, error: e.message }));
    r.setTimeout(12000, () => { r.destroy(); resolve({ status: 0, error: 'timeout' }); });
    if (body) r.write(body);
    r.end();
  });
}

function bodyKeys(body) {
  if (!body || typeof body !== 'object') return [];
  return Object.keys(body).slice(0, 12);
}

async function main() {
  const { userId, jwt, session } = readToken();
  const authVariants = [
    { Cookie: `WorkosCursorSessionToken=${session}` },
    { Cookie: `WorkosCursorSessionToken=${jwt}` },
    { Authorization: `Bearer ${jwt}` },
    { Authorization: `Bearer ${session}` },
    {
      Cookie: `WorkosCursorSessionToken=${session}`,
      Authorization: `Bearer ${jwt}`,
    },
  ];

  const urls = [
    `https://cursor.com/api/usage?user=${userId}`,
    `https://cursor.com/api/usage-summary`,
    `https://cursor.com/api/usage-summary?user=${userId}`,
    `https://www.cursor.com/api/usage-summary`,
    `https://cursor.com/api/dashboard/usage`,
    `https://cursor.com/api/dashboard/get-user-analytics`,
    `https://cursor.com/api/dashboard/get-user-privacy-mode`,
    `https://cursor.com/api/auth/stripe`,
    `https://cursor.com/api/auth/me`,
    `https://cursor.com/api/auth/profile`,
    `https://cursor.com/api/billing/usage`,
    `https://cursor.com/api/billing/subscription`,
    `https://cursor.com/api/usage/limits`,
    `https://cursor.com/api/user/usage`,
    `https://api2.cursor.sh/auth/full_stripe_profile`,
    `https://api2.cursor.sh/auth/usage`,
    `https://api2.cursor.sh/aiserver.v1.AiService/GetUsage`,
  ];

  const out = [];
  for (const url of urls) {
    for (let i = 0; i < authVariants.length; i++) {
      const h = {
        ...authVariants[i],
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
        Origin: 'https://cursor.com',
        Referer: 'https://cursor.com/dashboard',
        Accept: 'application/json',
      };
      const r = await req(url, h);
      if (r.status === 200 && r.body && typeof r.body === 'object') {
        out.push(redactPrivate({ url, authIdx: i, status: r.status, body: r.body }, ''));
        console.log('OK', url.replace(userId, '<redacted>'), 'auth', i, 'keys', bodyKeys(r.body).join(','));
        break;
      }
      if (r.status && r.status !== 401 && r.status !== 404 && r.status !== 405) {
        console.log('?', url.replace(userId, '<redacted>'), 'auth', i, r.status);
      }
    }
  }

  const dest = path.join(debugDir(), 'probe-results.json');
  secureWriteJson(dest, out);
  console.log('\nWrote', out.length, 'successful endpoints to', dest);
}

main().catch((err) => {
  console.error(err.message || String(err));
  process.exit(1);
});
