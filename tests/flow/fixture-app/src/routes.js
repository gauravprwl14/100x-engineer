const { getNote, patchNote } = require('./notes');

function mount(router, db, cache) {
  router.get('/notes/:id', async (req, res) => res.json(await getNote(db, cache, req.params.id)));
  router.patch('/notes/:id', async (req, res) => {
    await patchNote(db, cache, req.params.id, req.body.body);
    res.status(204).end();
  });
}

module.exports = { mount };
