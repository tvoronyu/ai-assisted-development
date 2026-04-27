const express = require('express');
const transactionService = require('../services/transactionService');
const { toCSV } = require('../utils/csv');

const router = express.Router();

// Task 4C — CSV export (must come before /:id to avoid route collision)
router.get('/export', (req, res, next) => {
  try {
    const format = (req.query.format || 'csv').toString().toLowerCase();
    if (format !== 'csv') {
      return res.status(400).json({ error: 'Unsupported format (only csv is supported)' });
    }
    const rows = transactionService.list(req.query);
    const headers = ['id', 'fromAccount', 'toAccount', 'amount', 'currency', 'type', 'timestamp', 'status'];
    const csv = toCSV(rows, headers);
    res.set('Content-Type', 'text/csv; charset=utf-8');
    res.set('Content-Disposition', 'attachment; filename="transactions.csv"');
    return res.status(200).send(csv);
  } catch (err) {
    return next(err);
  }
});

// Task 1 — Create
router.post('/', (req, res, next) => {
  try {
    const tx = transactionService.create(req.body);
    return res.status(201).json(tx);
  } catch (err) {
    return next(err);
  }
});

// Task 1 + 3 — List with filters
router.get('/', (req, res, next) => {
  try {
    const list = transactionService.list(req.query);
    return res.status(200).json(list);
  } catch (err) {
    return next(err);
  }
});

// Task 1 — Get by id
router.get('/:id', (req, res, next) => {
  try {
    const tx = transactionService.getById(req.params.id);
    return res.status(200).json(tx);
  } catch (err) {
    return next(err);
  }
});

module.exports = router;
