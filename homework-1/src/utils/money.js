// TODO (Implement phase): decimal-safe обчислення

function round2(value) {
  return Math.round(value * 100) / 100;
}

function hasAtMost2Decimals(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return false;
  return Number.isInteger(Math.round(value * 100)) && Math.abs(value * 100 - Math.round(value * 100)) < 1e-9;
}

module.exports = { round2, hasAtMost2Decimals };
