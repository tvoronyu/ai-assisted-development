const express = require('express');
const accountService = require('../services/accountService');

const router = express.Router();

// Task 1 — Balance
router.get('/:accountId/balance', (req, res, next) => {
  try {
    return res.status(200).json(accountService.balance(req.params.accountId));
  } catch (err) {
    return next(err);
  }
});

// Task 4A — Summary
router.get('/:accountId/summary', (req, res, next) => {
  try {
    return res.status(200).json(accountService.summary(req.params.accountId));
  } catch (err) {
    return next(err);
  }
});

// Task 4B — Interest
router.get('/:accountId/interest', (req, res, next) => {
  try {
    const { rate, days } = req.query;
    return res.status(200).json(accountService.interest(req.params.accountId, rate, days));
  } catch (err) {
    return next(err);
  }
});

module.exports = router;
