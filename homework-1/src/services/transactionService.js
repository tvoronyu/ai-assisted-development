const memoryStore = require('../storage/memoryStore');
const { createTransaction } = require('../models/transaction');
const { validateTransaction } = require('../validators/transactionValidator');
const { ValidationError, NotFoundError } = require('../errors');

function create(payload) {
  const { valid, errors } = validateTransaction(payload);
  if (!valid) throw new ValidationError(errors);

  const tx = createTransaction(payload);
  return memoryStore.add(tx);
}

function getById(id) {
  const tx = memoryStore.getById(id);
  if (!tx) throw new NotFoundError(`Transaction ${id} not found`);
  return tx;
}

function list(filters = {}) {
  const { accountId, type, from, to } = filters;

  let result = memoryStore.getAll();

  if (accountId) {
    result = result.filter((t) => t.fromAccount === accountId || t.toAccount === accountId);
  }

  if (type) {
    result = result.filter((t) => t.type === type);
  }

  if (from) {
    const fromDate = new Date(from);
    if (!Number.isNaN(fromDate.getTime())) {
      result = result.filter((t) => new Date(t.timestamp) >= fromDate);
    }
  }

  if (to) {
    const toDate = new Date(to);
    if (!Number.isNaN(toDate.getTime())) {
      // include full day for YYYY-MM-DD format
      const raw = String(to);
      if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
        toDate.setUTCHours(23, 59, 59, 999);
      }
      result = result.filter((t) => new Date(t.timestamp) <= toDate);
    }
  }

  return result;
}

module.exports = { create, getById, list };
