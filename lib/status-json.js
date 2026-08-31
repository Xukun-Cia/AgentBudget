#!/usr/bin/env node
/**
 * Print a sanitized usage snapshot as one JSON object on stdout.
 * Never prints tokens, user IDs, emails, or raw API payloads.
 */
const { fetchAndCompute, toPublicSnapshot } = require('./compute');

fetchAndCompute({ logRaw: false })
  .then((data) => {
    process.stdout.write(`${JSON.stringify(toPublicSnapshot(data))}\n`);
  })
  .catch((err) => {
    process.stdout.write(`${JSON.stringify({
      ok: false,
      error: err.message || String(err),
      fetchError: null,
    })}\n`);
    process.exitCode = 1;
  });
