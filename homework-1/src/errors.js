class ValidationError extends Error {
  constructor(details) {
    super('Validation failed');
    this.name = 'ValidationError';
    this.status = 400;
    this.details = details;
  }
}

class NotFoundError extends Error {
  constructor(message = 'Resource not found') {
    super(message);
    this.name = 'NotFoundError';
    this.status = 404;
  }
}

class BadRequestError extends Error {
  constructor(message = 'Bad request', details) {
    super(message);
    this.name = 'BadRequestError';
    this.status = 400;
    this.details = details;
  }
}

module.exports = { ValidationError, NotFoundError, BadRequestError };
