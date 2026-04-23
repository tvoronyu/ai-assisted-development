function errorHandler(err, _req, res, _next) {
  const status = err.status || 500;

  if (err.name === 'ValidationError') {
    return res.status(400).json({
      error: 'Validation failed',
      details: err.details || [],
    });
  }

  if (err.name === 'NotFoundError') {
    return res.status(404).json({ error: err.message });
  }

  if (err.name === 'BadRequestError') {
    return res.status(400).json({
      error: err.message,
      details: err.details || [],
    });
  }

  if (err.type === 'entity.parse.failed') {
    return res.status(400).json({ error: 'Invalid JSON body' });
  }

  console.error(err);
  return res.status(status).json({ error: err.message || 'Internal server error' });
}

function notFoundHandler(_req, res) {
  res.status(404).json({ error: 'Route not found' });
}

module.exports = { errorHandler, notFoundHandler };
