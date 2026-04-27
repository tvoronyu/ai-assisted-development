// TODO (Implement phase): розширити або підʼєднати пакет currency-codes
const SUPPORTED_CURRENCIES = new Set([
  'USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'CNY', 'UAH', 'PLN',
  'SEK', 'NOK', 'DKK', 'CZK', 'HUF', 'RON', 'TRY', 'ILS', 'INR', 'SGD',
  'HKD', 'KRW', 'MXN', 'BRL', 'ZAR', 'NZD', 'AED', 'SAR', 'THB', 'MYR',
]);

function isValidCurrency(code) {
  return typeof code === 'string' && SUPPORTED_CURRENCIES.has(code.toUpperCase());
}

module.exports = { SUPPORTED_CURRENCIES, isValidCurrency };
