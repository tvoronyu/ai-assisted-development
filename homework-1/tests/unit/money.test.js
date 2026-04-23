const { round2, hasAtMost2Decimals } = require('../../src/utils/money');

describe('round2', () => {
  test('rounds to 2 decimals', () => {
    expect(round2(1.239)).toBe(1.24);
    expect(round2(1.231)).toBe(1.23);
    expect(round2(10)).toBe(10);
    expect(round2(0)).toBe(0);
  });
});

describe('hasAtMost2Decimals', () => {
  test.each([
    [100, true],
    [100.1, true],
    [100.12, true],
    [0.01, true],
    [100.123, false],
    [100.001, false],
    ['10', false],
    [Number.NaN, false],
    [Number.POSITIVE_INFINITY, false],
  ])('%p → %p', (value, expected) => {
    expect(hasAtMost2Decimals(value)).toBe(expected);
  });
});
