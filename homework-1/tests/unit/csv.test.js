const { toCSV, escapeCell } = require('../../src/utils/csv');

describe('escapeCell', () => {
  test('leaves simple values as-is', () => {
    expect(escapeCell('hello')).toBe('hello');
    expect(escapeCell(42)).toBe('42');
  });

  test('quotes values with commas, quotes, or newlines', () => {
    expect(escapeCell('a,b')).toBe('"a,b"');
    expect(escapeCell('say "hi"')).toBe('"say ""hi"""');
    expect(escapeCell('line1\nline2')).toBe('"line1\nline2"');
  });

  test('handles null/undefined as empty string', () => {
    expect(escapeCell(null)).toBe('');
    expect(escapeCell(undefined)).toBe('');
  });
});

describe('toCSV', () => {
  test('serializes rows with headers', () => {
    const csv = toCSV(
      [
        { id: '1', amount: 10 },
        { id: '2', amount: 20 },
      ],
      ['id', 'amount'],
    );
    expect(csv).toBe('id,amount\n1,10\n2,20');
  });

  test('empty array returns just the header', () => {
    expect(toCSV([], ['a', 'b'])).toBe('a,b');
  });

  test('derives headers from first row if none provided', () => {
    const csv = toCSV([{ x: 1, y: 2 }]);
    expect(csv.split('\n')[0]).toBe('x,y');
  });
});
