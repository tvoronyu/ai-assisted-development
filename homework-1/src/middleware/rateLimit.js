const rateLimit = require('express-rate-limit');

function createRateLimiter(overrides = {}) {
  const windowMs = overrides.windowMs ?? Number(process.env.RATE_LIMIT_WINDOW_MS) ?? 60_000;
  const max = overrides.max ?? Number(process.env.RATE_LIMIT_MAX) ?? 100;

  return rateLimit({
    windowMs: Number.isFinite(windowMs) ? windowMs : 60_000,
    max: Number.isFinite(max) ? max : 100,
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: 'Too Many Requests' },
  });
}

module.exports = { createRateLimiter };
