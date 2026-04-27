const request = require('supertest');
const { createApp } = require('../../src/app');

describe('rate limiting', () => {
  test('returns 429 after exceeding limit', async () => {
    const app = createApp({
      enableRateLimit: true,
      rateLimitOptions: { windowMs: 60_000, max: 3 },
    });

    for (let i = 0; i < 3; i++) {
      // eslint-disable-next-line no-await-in-loop
      const res = await request(app).get('/health');
      expect(res.status).toBe(200);
    }

    const blocked = await request(app).get('/health');
    expect(blocked.status).toBe(429);
    expect(blocked.body.error).toMatch(/Too Many Requests/);
  });
});
