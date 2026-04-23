const {
  validateTransaction,
  validateAmount,
  validateAccount,
  validateCurrency,
  validateType,
} = require('../../src/validators/transactionValidator');
const { isValidCurrency } = require('../../src/validators/currencies');

describe('validateAmount', () => {
  test.each([
    [100, null],
    [100.5, null],
    [100.55, null],
    [0.01, null],
  ])('accepts %p', (value, expected) => {
    expect(validateAmount(value)).toBe(expected);
  });

  test.each([
    [undefined, /required/i],
    [null, /required/i],
    ['100', /number/i],
    [-10, /positive/i],
    [0, /positive/i],
    [10.999, /2 decimal/i],
    [Number.NaN, /number/i],
  ])('rejects %p', (value, expected) => {
    expect(validateAmount(value)).toMatch(expected);
  });
});

describe('validateAccount', () => {
  test('accepts ACC-12345 format', () => {
    expect(validateAccount('ACC-12345', 'fromAccount')).toBeNull();
    expect(validateAccount('ACC-ABCDE', 'fromAccount')).toBeNull();
    expect(validateAccount('ACC-A1B2C3', 'fromAccount')).toBeNull();
  });

  test.each([
    [undefined],
    [''],
    ['ACC-123'],
    ['ACCT-12345'],
    ['12345'],
    ['ACC_12345'],
    [12345],
  ])('rejects %p', (value) => {
    expect(validateAccount(value, 'fromAccount')).toMatch(/fromAccount/);
  });
});

describe('validateCurrency', () => {
  test.each(['USD', 'EUR', 'GBP', 'UAH', 'usd'])('accepts %s', (c) => {
    expect(isValidCurrency(c)).toBe(true);
    expect(validateCurrency(c)).toBeNull();
  });

  test.each(['XYZ', '', null, undefined, 'US', 123])('rejects %p', (c) => {
    expect(validateCurrency(c)).toMatch(/currency/i);
  });
});

describe('validateType', () => {
  test.each(['deposit', 'withdrawal', 'transfer'])('accepts %s', (t) => {
    expect(validateType(t)).toBeNull();
  });

  test.each(['refund', '', null, undefined, 'DEPOSIT'])('rejects %p', (t) => {
    expect(validateType(t)).toMatch(/type/i);
  });
});

describe('validateTransaction', () => {
  const valid = {
    fromAccount: 'ACC-12345',
    toAccount: 'ACC-67890',
    amount: 100.5,
    currency: 'USD',
    type: 'transfer',
  };

  test('valid payload passes', () => {
    const res = validateTransaction(valid);
    expect(res.valid).toBe(true);
    expect(res.errors).toEqual([]);
  });

  test('collects all errors, not just first', () => {
    const res = validateTransaction({
      fromAccount: 'x',
      toAccount: 'y',
      amount: -1,
      currency: 'XYZ',
      type: 'xfer',
    });
    expect(res.valid).toBe(false);
    expect(res.errors.length).toBeGreaterThanOrEqual(5);
    const fields = res.errors.map((e) => e.field);
    expect(fields).toEqual(
      expect.arrayContaining(['amount', 'fromAccount', 'toAccount', 'currency', 'type']),
    );
  });

  test('status is optional, rejected if invalid', () => {
    expect(validateTransaction({ ...valid, status: 'completed' }).valid).toBe(true);
    expect(validateTransaction({ ...valid, status: 'bogus' }).valid).toBe(false);
  });

  test('null/undefined payload returns all required errors', () => {
    expect(validateTransaction(null).valid).toBe(false);
    expect(validateTransaction(undefined).valid).toBe(false);
  });
});
