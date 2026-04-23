const request = require('supertest');
const { createApp } = require('../../src/app');
const memoryStore = require('../../src/storage/memoryStore');

const app = createApp({ enableRateLimit: false });

const validTx = {
  fromAccount: 'ACC-12345',
  toAccount: 'ACC-67890',
  amount: 100.5,
  currency: 'USD',
  type: 'transfer',
};

beforeEach(() => memoryStore.clear());

describe('POST /transactions', () => {
  test('201 on valid payload', async () => {
    const res = await request(app).post('/transactions').send(validTx);
    expect(res.status).toBe(201);
    expect(res.body.id).toBeDefined();
    expect(res.body.amount).toBe(100.5);
    expect(res.body.status).toBe('completed');
    expect(res.body.timestamp).toMatch(/^\d{4}-/);
  });

  test('400 with details on invalid payload', async () => {
    const res = await request(app)
      .post('/transactions')
      .send({ ...validTx, amount: -1, currency: 'XYZ' });
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/Validation failed/);
    expect(Array.isArray(res.body.details)).toBe(true);
    const fields = res.body.details.map((d) => d.field);
    expect(fields).toEqual(expect.arrayContaining(['amount', 'currency']));
  });

  test('400 on invalid JSON body', async () => {
    const res = await request(app)
      .post('/transactions')
      .set('Content-Type', 'application/json')
      .send('{not-json');
    expect(res.status).toBe(400);
  });
});

describe('GET /transactions', () => {
  test('returns empty array when no transactions', async () => {
    const res = await request(app).get('/transactions');
    expect(res.status).toBe(200);
    expect(res.body).toEqual([]);
  });

  test('lists created transactions', async () => {
    await request(app).post('/transactions').send(validTx);
    await request(app)
      .post('/transactions')
      .send({ ...validTx, type: 'deposit' });

    const res = await request(app).get('/transactions');
    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(2);
  });

  test('filters by accountId and type', async () => {
    await request(app).post('/transactions').send(validTx); // transfer ACC-12345 → ACC-67890
    await request(app)
      .post('/transactions')
      .send({ ...validTx, fromAccount: 'ACC-EXTRN', type: 'deposit' });

    const accFilter = await request(app).get('/transactions?accountId=ACC-12345');
    expect(accFilter.body).toHaveLength(1);

    const typeFilter = await request(app).get('/transactions?type=deposit');
    expect(typeFilter.body).toHaveLength(1);

    const combined = await request(app).get('/transactions?accountId=ACC-67890&type=deposit');
    expect(combined.body).toHaveLength(1);
  });
});

describe('GET /transactions/:id', () => {
  test('200 with transaction', async () => {
    const created = await request(app).post('/transactions').send(validTx);
    const res = await request(app).get(`/transactions/${created.body.id}`);
    expect(res.status).toBe(200);
    expect(res.body.id).toBe(created.body.id);
  });

  test('404 when not found', async () => {
    const res = await request(app).get('/transactions/nonexistent-id');
    expect(res.status).toBe(404);
    expect(res.body.error).toMatch(/not found/i);
  });
});

describe('GET /transactions/export?format=csv', () => {
  test('returns CSV with correct headers', async () => {
    await request(app).post('/transactions').send(validTx);
    const res = await request(app).get('/transactions/export?format=csv');
    expect(res.status).toBe(200);
    expect(res.headers['content-type']).toMatch(/text\/csv/);
    const lines = res.text.split('\n');
    expect(lines[0]).toBe('id,fromAccount,toAccount,amount,currency,type,timestamp,status');
    expect(lines).toHaveLength(2);
  });

  test('400 on unsupported format', async () => {
    const res = await request(app).get('/transactions/export?format=json');
    expect(res.status).toBe(400);
  });
});
