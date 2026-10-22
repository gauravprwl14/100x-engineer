// A made-up notes service: cache-aside reads, write-then-invalidate updates.
const CACHE_TTL_SECONDS = 300;

const cacheKey = (id) => `note:${id}`;

async function getNote(db, cache, id) {
  const cached = await cache.get(cacheKey(id));
  if (cached) return cached;
  const note = await db.query('SELECT body FROM notes WHERE id = $1', [id]);
  await cache.set(cacheKey(id), note, { ttl: CACHE_TTL_SECONDS });
  return note;
}

async function patchNote(db, cache, id, body) {
  await db.query('UPDATE notes SET body = $2 WHERE id = $1', [id, body]);
  await cache.del(cacheKey(id));
}

module.exports = { getNote, patchNote };
