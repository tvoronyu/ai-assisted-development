const store = new Map();

function add(tx) {
  store.set(tx.id, tx);
  return tx;
}

function getById(id) {
  return store.get(id);
}

function getAll() {
  return Array.from(store.values());
}

function clear() {
  store.clear();
}

function size() {
  return store.size;
}

module.exports = { add, getById, getAll, clear, size };
