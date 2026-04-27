const { isValidCurrency } = require('./currencies');
const { hasAtMost2Decimals } = require('../utils/money');

const ACCOUNT_REGEX = /^ACC-[A-Za-z0-9]{5,}$/;
const VALID_TYPES = new Set(['deposit', 'withdrawal', 'transfer']);
const VALID_STATUSES = new Set(['pending', 'completed', 'failed']);

function validateAmount(amount) {
  if (amount === undefined || amount === null) {
    return 'Amount is required';
  }
  if (typeof amount !== 'number' || !Number.isFinite(amount)) {
    return 'Amount must be a number';
  }
  if (amount <= 0) {
    return 'Amount must be a positive number';
  }
  if (!hasAtMost2Decimals(amount)) {
    return 'Amount must have at most 2 decimal places';
  }
  return null;
}

function validateAccount(value, field) {
  if (value === undefined || value === null || value === '') {
    return `${field} is required`;
  }
  if (typeof value !== 'string' || !ACCOUNT_REGEX.test(value)) {
    return `${field} must match format ACC-XXXXX (alphanumeric, min 5 chars)`;
  }
  return null;
}

function validateCurrency(currency) {
  if (!currency) return 'Currency is required';
  if (!isValidCurrency(currency)) {
    return 'Invalid currency code (must be ISO 4217, e.g. USD, EUR, GBP)';
  }
  return null;
}

function validateType(type) {
  if (!type) return 'Type is required';
  if (!VALID_TYPES.has(type)) {
    return `Type must be one of: ${[...VALID_TYPES].join(', ')}`;
  }
  return null;
}

function validateStatus(status) {
  if (status === undefined) return null;
  if (!VALID_STATUSES.has(status)) {
    return `Status must be one of: ${[...VALID_STATUSES].join(', ')}`;
  }
  return null;
}

function validateTransaction(payload) {
  const errors = [];
  const p = payload || {};

  const amountErr = validateAmount(p.amount);
  if (amountErr) errors.push({ field: 'amount', message: amountErr });

  const fromErr = validateAccount(p.fromAccount, 'fromAccount');
  if (fromErr) errors.push({ field: 'fromAccount', message: fromErr });

  const toErr = validateAccount(p.toAccount, 'toAccount');
  if (toErr) errors.push({ field: 'toAccount', message: toErr });

  const currencyErr = validateCurrency(p.currency);
  if (currencyErr) errors.push({ field: 'currency', message: currencyErr });

  const typeErr = validateType(p.type);
  if (typeErr) errors.push({ field: 'type', message: typeErr });

  const statusErr = validateStatus(p.status);
  if (statusErr) errors.push({ field: 'status', message: statusErr });

  return { valid: errors.length === 0, errors };
}

module.exports = {
  validateTransaction,
  validateAmount,
  validateAccount,
  validateCurrency,
  validateType,
  ACCOUNT_REGEX,
  VALID_TYPES,
};
