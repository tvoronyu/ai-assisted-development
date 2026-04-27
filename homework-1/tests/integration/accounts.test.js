const request = require('supertest');
const { createApp } = require('../../src/app');
const memoryStore = require('../../src/storage/memoryStore');

const app = createApp({ enableRateLimit: false });

async function post(payload) {
  return request(app).post('/transactions').send(payload);
}

beforeEach(() => memoryStore.clear());

describe('GET /accounts/:accountId/balance', () => {
  test('404 if no transactions for account', async () => {
    const res = await request(app).get('/accounts/ACC-NOBODY/balance');
    expect(res.status).toBe(404);
  });

  test('computes balance across types', async () => {
    await post({
      fromAccount: 'ACC-EXTRN',
      toAccount: 'ACC-AAAAA',
      amount: 1000,
      currency: 'USD',
      type: 'deposit',
    });
    await post({
      fromAccount: 'ACC-AAAAA',
      toAccount: 'ACC-BBBBB',
      amount: 250,
      currency: 'USD',
      type: 'transfer',
    });
    await post({
      fromAccount: 'ACC-AAAAA',
      toAccount: 'ACC-EXTRN',
      amount: 100,
      currency: 'USD',
      type: 'withdrawal',
    });

    const res = await request(app).get('/accounts/ACC-AAAAA/balance');
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({
      accountId: 'ACC-AAAAA',
      balance: 650,
      currency: 'USD',
    });
  });
});

describe('GET /accounts/:accountId/summary', () => {
  test('aggregates deposits/withdrawals', async () => {
    await post({
      fromAccount: 'ACC-EXTRN',
      toAccount: 'ACC-AAAAA',
      amount: 500,
      currency: 'USD',
      type: 'deposit',
    });
    await post({
      fromAccount: 'ACC-AAAAA',
      toAccount: 'ACC-EXTRN',
      amount: 100,
      currency: 'USD',
      type: 'withdrawal',
    });

    const res = await request(app).get('/accounts/ACC-AAAAA/summary');
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({
      accountId: 'ACC-AAAAA',
      totalDeposits: 500,
      totalWithdrawals: 100,
      transactionCount: 2,
    });
    expect(res.body.lastTransactionDate).toBeDefined();
  });

  test('404 when account has no transactions', async () => {
    const res = await request(app).get('/accounts/ACC-NOBODY/summary');
    expect(res.status).toBe(404);
  });
});

describe('GET /accounts/:accountId/interest', () => {
  beforeEach(async () => {
    await post({
      fromAccount: 'ACC-EXTRN',
      toAccount: 'ACC-AAAAA',
      amount: 1000,
      currency: 'USD',
      type: 'deposit',
    });
  });

  test('200 with computed interest', async () => {
    const res = await request(app).get('/accounts/ACC-AAAAA/interest?rate=0.05&days=365');
    expect(res.status).toBe(200);
    expect(res.body.interest).toBe(50);
  });

  test('400 on negative rate', async () => {
    const res = await request(app).get('/accounts/ACC-AAAAA/interest?rate=-0.01&days=30');
    expect(res.status).toBe(400);
  });

  test('400 on non-numeric days', async () => {
    const res = await request(app).get('/accounts/ACC-AAAAA/interest?rate=0.05&days=abc');
    expect(res.status).toBe(400);
  });
});
