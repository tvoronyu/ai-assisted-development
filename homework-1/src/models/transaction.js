const { randomUUID } = require('crypto');

// TODO (Implement phase): фабрика Transaction з auto-id, server timestamp, default status='completed'
function createTransaction({ fromAccount, toAccount, amount, currency, type, status }) {
  return {
    id: randomUUID(),
    fromAccount,
    toAccount,
    amount,
    currency,
    type,
    timestamp: new Date().toISOString(),
    status: status || 'completed',
  };
}

module.exports = { createTransaction };
