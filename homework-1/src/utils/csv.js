function escapeCell(value) {
  if (value === null || value === undefined) return '';
  const str = String(value);
  if (/[",\n\r]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function toCSV(rows, headers) {
  if (!Array.isArray(rows)) return '';
  const cols = headers && headers.length > 0 ? headers : Object.keys(rows[0] || {});
  const head = cols.map(escapeCell).join(',');
  const body = rows.map((row) => cols.map((c) => escapeCell(row[c])).join(',')).join('\n');
  return rows.length === 0 ? head : `${head}\n${body}`;
}

module.exports = { toCSV, escapeCell };
