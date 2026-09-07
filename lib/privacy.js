/**
 * Privacy helpers shared by diagnostics and release checks.
 * Runtime UI data is still built from explicit allow-lists; this module is a
 * second line of defence for opt-in debug snapshots.
 */
const fs = require('fs');
const path = require('path');

const PRIVATE_KEY = /(?:authorization|cookie|token|jwt|session|email|user_?id|account_?id|payment|customer|profile)/i;
const JWT_VALUE = /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/;
const EMAIL_VALUE = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i;
const BEARER_VALUE = /\bBearer\s+[A-Za-z0-9._~+\/-]{12,}/i;

function redactPrivate(value, key) {
  if (key && PRIVATE_KEY.test(String(key))) return '<redacted>';
  if (Array.isArray(value)) return value.map((item) => redactPrivate(item, ''));
  if (value && typeof value === 'object') {
    const clean = {};
    for (const entry of Object.keys(value)) {
      clean[entry] = redactPrivate(value[entry], entry);
    }
    return clean;
  }
  if (typeof value === 'string') {
    if (JWT_VALUE.test(value) || EMAIL_VALUE.test(value) || BEARER_VALUE.test(value)) {
      return '<redacted>';
    }
  }
  return value;
}

function secureWriteJson(file, value) {
  const dir = path.dirname(file);
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  try { fs.chmodSync(dir, 0o700); } catch (_) {}
  fs.writeFileSync(file, `${JSON.stringify(redactPrivate(value, ''), null, 2)}\n`, {
    encoding: 'utf-8',
    mode: 0o600,
  });
  try { fs.chmodSync(file, 0o600); } catch (_) {}
}

module.exports = {
  PRIVATE_KEY,
  JWT_VALUE,
  EMAIL_VALUE,
  BEARER_VALUE,
  redactPrivate,
  secureWriteJson,
};
