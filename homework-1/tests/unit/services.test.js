const memoryStore = require('../../src/storage/memoryStore');
const transactionService = require('../../src/services/transactionService');
const accountService = require('../../src/services/accountService');

beforeEach(() => memoryStore.clear());

function seed(data) {
  return transactionService.create(data);
}

describe('transactionService.create', () => {
  test('creates tx with generated id + timestamp + default status', () => {
    const tx = seed({
      fromAccount: 'ACC-AAAAA',
      toAccount: 'ACC-BBBBB',
      amount: 50,
      currency: 'USD',
      type: 'transfer',
    });
    expect(tx.id).toMatch(/[0-9a-f-]{36}/);
    expect(tx.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(tx.status).toBe('completed');
  });

  test('throws ValidationError on bad payload', () => {
    expect(() =>
      seed({ fromAccount: 'x', toAccount: 'y', amount: -1, currency: 'XYZ', type: 'xfer' }),
    ).toThrow(/Validation failed/);
  });
});

describe('transactionService.list filters', () => {
  beforeEach(() => {
    memoryStore.clear();
    seed({
      fromAccount: 'ACC-EXTRN',
      toAccount: 'ACC-AAAAA',
      amount: 100,
      currency: 'USD',
      type: 'deposit',
    });
    seed({
      fromAccount: 'ACC-AAAAA',
      toAccount: 'ACC-BBBBB',
      amount: 40,
      currency: 'USD',
      type: 'transfer',
    });
    seed({
      fromAccount: 'ACC-BBBBB',
      toAccount: 'ACC-EXTRN',
      amount: 10,
      currency: 'USD',
      type: 'withdrawal',
    });
  });

  test('no filters returns all', () => {
    expect(transactionService.list({})).toHaveLength(3);
  });

  test('filter by accountId', () => {
    const res = transactionService.list({ accountId: 'ACC-AAAAA' });
    expect(res).toHaveLength(2);
  });

  test('filter by type', () => {
    expect(transactionService.list({ type: 'deposit' })).toHaveLength(1);
  });

  test('filter by date range', () => {
    const future = '2099-01-01';
    expect(transactionService.list({ from: future })).toHaveLength(0);
    expect(transactionService.list({ to: '2000-01-01' })).toHaveLength(0);
  });

  test('combined filters', () => {
    const res = transactionService.list({ accountId: 'ACC-AAAAA', type: 'transfer' });
    expect(res).toHaveLength(1);
  });
});

describe('accountService.balance', () => {
  test('sums deposits, withdrawals, transfers', () => {
    seed({
      fromAccount: 'ACC-EXTRN',
      toAccount: 'ACC-AAAAA',
      amount: 1000,
      currency: 'USD',
      type: 'deposit',
    });
    seed({
      fromAccount: 'ACC-AAAAA',
      toAccount: 'ACC-BBBBB',
      amount: 250.75,
      currency: 'USD',
      type: 'transfer',
    });
    seed({
      fromAccount: 'ACC-AAAAA',
      toAccount: 'ACC-EXTRN',
      amount: 100,
      currency: 'USD',
      type: 'withdrawal',
    });

    const a = accountService.balance('ACC-AAAAA');
    expect(a.balance).toBe(649.25);
    expect(a.currency).toBe('USD');

    const b = accountService.balance('ACC-BBBBB');
    expect(b.balance).toBe(250.75);
  });

  test('throws NotFoundError when no transactions', () => {
    expect(() => accountService.balance('ACC-NOBODY')).toThrow(/not found|no transactions/i);
  });
});

describe('accountService.summary', () => {
  test('aggregates deposits, withdrawals, count, last date', () => {
    seed({
      fromAccount: 'ACC-EXTRN',
      toAccount: 'ACC-AAAAA',
      amount: 500,
      currency: 'USD',
      type: 'deposit',
    });
    seed({
      fromAccount: 'ACC-AAAAA',
      toAccount: 'ACC-EXTRN',
      amount: 100,
      currency: 'USD',
      type: 'withdrawal',
    });
    seed({
      fromAccount: 'ACC-BBBBB',
      toAccount: 'ACC-AAAAA',
      amount: 50,
      currency: 'USD',
      type: 'transfer',
    });

    const s = accountService.summary('ACC-AAAAA');
    expect(s.totalDeposits).toBe(550);
    expect(s.totalWithdrawals).toBe(100);
    expect(s.transactionCount).toBe(3);
    expect(s.lastTransactionDate).toBeTruthy();
  });
});

describe('accountService.interest', () => {
  beforeEach(() => {
    seed({
      fromAccount: 'ACC-EXTRN',
      toAccount: 'ACC-AAAAA',
      amount: 1000,
      currency: 'USD',
      type: 'deposit',
    });
  });

  test('computes simple interest', () => {
    const r = accountService.interest('ACC-AAAAA', 0.05, 365);
    expect(r.interest).toBe(50);
  });

  test('rejects negative rate or days', () => {
    expect(() => accountService.interest('ACC-AAAAA', -0.01, 30)).toThrow(/Validation/);
    expect(() => accountService.interest('ACC-AAAAA', 0.05, -1)).toThrow(/Validation/);
  });

  test('rejects non-numeric input', () => {
    expect(() => accountService.interest('ACC-AAAAA', 'abc', 30)).toThrow(/Validation/);
  });
});
