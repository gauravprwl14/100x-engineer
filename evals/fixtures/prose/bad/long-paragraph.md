# Offline mode

**Answer:** notes edited offline sync on reconnect.

The offline queue stores every edit in a local table and replays them in order once the
device is back online, which mostly works but has a few corner cases around attachments,
deleted notebooks and shared folders that the team discussed at length and decided to
handle later, after the beta, because the beta users rarely go offline for long.
