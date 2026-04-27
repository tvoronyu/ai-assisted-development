const memoryStore = require('../storage/memoryStore');
const { round2 } = require('../utils/money');
const { NotFoundError, BadRequestError } = require('../errors');

function collectAccountTransactions(accountId) {
  return memoryStore
    .getAll()
    .filter((t) => t.fromAccount === accountId || t.toAccount === accountId);
}

function computeBalance(accountId, txs) {
  let balance = 0;
  for (const t of txs) {
    if (t.status && t.status !== 'completed') continue;
    const amount = Number(t.amount);
    switch (t.type) {
      case 'deposit':
        if (t.toAccount === accountId) balance += amount;
        break;
      case 'withdrawal':
        if (t.fromAccount === accountId) balance -= amount;
        break;
      case 'transfer':
        if (t.fromAccount === accountId) balance -= amount;
        if (t.toAccount === accountId) balance += amount;
        break;
      default:
        break;
    }
  }
  return round2(balance);
}

function balance(accountId) {
  const txs = collectAccountTransactions(accountId);
  if (txs.length === 0) {
    throw new NotFoundError(`Account ${accountId} has no transactions`);
  }
  const currencies = [...new Set(txs.map((t) => t.currency))];
  return {
    accountId,
    balance: computeBalance(accountId, txs),
    currency: currencies.length === 1 ? currencies[0] : currencies,
    transactionCount: txs.length,
  };
}

function summary(accountId) {
  const txs = collectAccountTransactions(accountId);
  if (txs.length === 0) {
    throw new NotFoundError(`Account ${accountId} has no transactions`);
  }

  let totalDeposits = 0;
  let totalWithdrawals = 0;

  for (const t of txs) {
    if (t.status && t.status !== 'completed') continue;
    const amount = Number(t.amount);
    if (t.type === 'deposit' && t.toAccount === accountId) {
      totalDeposits += amount;
    } else if (t.type === 'withdrawal' && t.fromAccount === accountId) {
      totalWithdrawals += amount;
    } else if (t.type === 'transfer') {
      if (t.toAccount === accountId) totalDeposits += amount;
      if (t.fromAccount === accountId) totalWithdrawals += amount;
    }
  }

  const lastTransactionDate = txs
    .map((t) => t.timestamp)
    .sort()
    .slice(-1)[0];

  return {
    accountId,
    totalDeposits: round2(totalDeposits),
    totalWithdrawals: round2(totalWithdrawals),
    transactionCount: txs.length,
    lastTransactionDate,
  };
}

function interest(accountId, rate, days) {
  const rateNum = Number(rate);
  const daysNum = Number(days);

  const details = [];
  if (!Number.isFinite(rateNum) || rateNum < 0) {
    details.push({ field: 'rate', message: 'Rate must be a non-negative number' });
  }
  if (!Number.isFinite(daysNum) || daysNum < 0) {
    details.push({ field: 'days', message: 'Days must be a non-negative number' });
  }
  if (details.length > 0) {
    throw new BadRequestError('Validation failed', details);
  }

  const info = balance(accountId); // throws 404 if no transactions
  const interestAmount = round2(info.balance * rateNum * (daysNum / 365));

  return {
    accountId,
    balance: info.balance,
    currency: info.currency,
    rate: rateNum,
    days: daysNum,
    interest: interestAmount,
  };
}

module.exports = { balance, summary, interest, computeBalance };
