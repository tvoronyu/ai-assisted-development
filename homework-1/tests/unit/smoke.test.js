const { createApp } = require('../../src/app');

describe('scaffold smoke', () => {
  test('createApp returns Express app', () => {
    const app = createApp({ enableRateLimit: false });
    expect(typeof app).toBe('function');
    expect(typeof app.use).toBe('function');
  });
});
