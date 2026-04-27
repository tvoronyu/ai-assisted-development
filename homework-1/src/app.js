const express = require('express');
const transactionsRouter = require('./routes/transactions');
const accountsRouter = require('./routes/accounts');
const { errorHandler, notFoundHandler } = require('./middleware/errorHandler');
const { createRateLimiter } = require('./middleware/rateLimit');

function createApp({ enableRateLimit = true, rateLimitOptions } = {}) {
  const app = express();
  app.use(express.json());

  if (enableRateLimit) {
    app.use(createRateLimiter(rateLimitOptions));
  }

  app.get('/health', (_req, res) => res.json({ status: 'ok' }));

  app.use('/transactions', transactionsRouter);
  app.use('/accounts', accountsRouter);

  app.use(notFoundHandler);
  app.use(errorHandler);

  return app;
}

module.exports = { createApp };
