-- The proposed fix: a GET fills note:<id> only if no newer version is cached. PATCH writes a
-- tombstone {v = new version} instead of deleting, kept longer than the slowest GET.
-- KEYS[1] note key; ARGV[1] body, ARGV[2] version read with it, ARGV[3] ttl seconds.
local cached = tonumber(redis.call('HGET', KEYS[1], 'v') or '0')
if cached > tonumber(ARGV[2]) then return 0 end
redis.call('HSET', KEYS[1], 'body', ARGV[1], 'v', ARGV[2])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
