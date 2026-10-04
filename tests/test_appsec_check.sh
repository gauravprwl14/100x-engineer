#!/usr/bin/env bash
# Regression suite for appsec_check.py: each check gets planted violations AND
# the safe forms a reviewer would accept (allowlisted, sanitised, parameterised,
# literal, test fixture), which must not be flagged. Plus diff-scoping, the
# severity contract, subfolder runs and the exit-2 refusal outside a repository.
# Secret-looking values below are synthetic; none is a real credential.
# Run: bash tests/test_appsec_check.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"; OUT="$(mktemp -d)"; NOREPO="$(mktemp -d)"
trap 'rm -rf "$TMP" "$OUT" "$NOREPO"' EXIT
AS="$ROOT/scripts/appsec_check.py"
cd "$TMP"; git init -q; git config user.email t@t; git config user.name t
mkdir -p src
printf 'export const ok = 1;\n' > src/base.ts
git add -A; git commit -qm init >/dev/null

PASS=0; FAIL=0
expect() { # expect <exit> <label> [args...]
  local exp="$1" label="$2"; shift 2
  python3 "$AS" "$@" >"$OUT/a.out" 2>&1; local got=$?
  if [ "$got" -eq "$exp" ]; then PASS=$((PASS+1)); printf '  ok   %-66s\n' "$label"
  else FAIL=$((FAIL+1)); printf '  FAIL %-66s exit exp=%s got=%s\n' "$label" "$exp" "$got"; sed 's/^/       /' "$OUT/a.out"; fi
}
has() { grep -q -- "$1" "$OUT/a.out" && { PASS=$((PASS+1)); printf '  ok   %-66s\n' "reported: $1"; } \
        || { FAIL=$((FAIL+1)); printf '  FAIL %-66s\n' "NOT reported: $1"; sed 's/^/       /' "$OUT/a.out"; }; }
reset_diff() { git checkout -q -- . ; git clean -qfd . ; }
# Builds a synthetic AWS-shaped id at runtime so this file never contains one.
AWS_ID="AKIA$(printf 'Q%.0s' 1 2 3 4)$(printf 'Z7%.0s' 1 2 3 4 5 6)"

# ----------------------------------------------------------------------- ssrf
cat > src/proxy.ts <<'EOF'
export async function proxy(req, res) {
  const r = await fetch(req.query.url);
  res.send(await r.text());
}
EOF
cat > src/hook.ts <<'EOF'
export async function preview(req) {
  const { target } = req.body;
  return axios.get(target);
}
EOF
cat > src/hook.py <<'EOF'
def fetch_avatar():
    url = request.args.get("avatar")
    return requests.get(url, timeout=5)
EOF
cat > src/nest.ts <<'EOF'
@Post('ping') ping(@Body() dto: PingDto) {
  return axios.post(dto.callbackUrl, { ok: true });
}
EOF
expect 1 "ssrf: query param, destructured body, request.args, @Body dto" --only ssrf
has "src/proxy.ts:2: outbound request to a URL from request input"
has "src/hook.ts:3:"
has "src/hook.py:3:"
has "src/nest.ts:2:"
has "OWASP API7:2023"
reset_diff

cat > src/ok_fixed.ts <<'EOF'
export async function user(req) {
  const a = await fetch(`${API_BASE}/users/${req.params.id}`);
  const b = await fetch('https://api.example.com/search?q=' + req.query.q);
  return fetch('/static/config.json');
}
EOF
cat > src/ok_allow.ts <<'EOF'
const ALLOWED_HOSTS = new Set(['hooks.example.com']);
export async function send(req) {
  const u = new URL(req.body.url);
  if (!ALLOWED_HOSTS.has(u.hostname)) throw new Error('blocked');
  return fetch(u);
}
EOF
mkdir -p test; printf 'it("x", async () => { await fetch(req.query.url); });\n' > test/proxy.ts
expect 0 "ssrf: fixed host, allowlist, test dir are clean" --only ssrf --strict
reset_diff

# ------------------------------------------------------------ mass-assignment
cat > src/users.ts <<'EOF'
export async function update(req) {
  const user = await repo.findOne(req.params.id);
  Object.assign(user, req.body);
  await prisma.user.update({ where: { id: req.params.id }, data: req.body });
  await User.create({ ...req.body, companyId: req.user.companyId });
  return repo.save(req.body);
}
EOF
expect 1 "mass-assignment: Object.assign, prisma data:, spread, direct save" --only mass-assignment
has "src/users.ts:3: Object.assign() of req.body onto an entity"
has "src/users.ts:4: raw request body passed to .update()"
has "src/users.ts:5: raw request body passed to .create()"
has "src/users.ts:6: raw request body passed to .save()"
reset_diff

cat > src/ok_users.ts <<'EOF'
export async function update(req) {
  const { name, email } = req.body;
  await prisma.user.update({ where: { id: req.params.id }, data: { name, email } });
  await repo.save({ title: req.body.title, ownerId: req.user.id });
  return Object.assign({}, defaults, { name });
}
EOF
expect 0 "mass-assignment: named fields and single-field reads are clean" --only mass-assignment,dto-spread-into-orm --strict
reset_diff

printf 'export const f = (dto: CreateTagDto) => this.repo.save({ ...dto, companyId });\n' > src/tags.ts
expect 0 "dto-spread-into-orm: advisory, exits 0 without --strict" --only dto-spread-into-orm
has "src/tags.ts:1: ...dto spread into .save()"
expect 1 "dto-spread-into-orm: fails under --strict" --only dto-spread-into-orm --strict
reset_diff

# ---------------------------------------------------------------- unsafe-html
cat > src/Post.tsx <<'EOF'
export const Post = ({ post }) => <div dangerouslySetInnerHTML={{ __html: post.body }} />;
export function render(el, html) { el.innerHTML = html; }
EOF
printf '<template><div v-html="comment.text"></div></template>\n' > src/Comment.vue
expect 1 "unsafe-html: dangerouslySetInnerHTML, innerHTML, v-html" --only unsafe-html
has "src/Post.tsx:1: dangerouslySetInnerHTML with a non-literal value"
has "src/Post.tsx:2: .innerHTML"
has "src/Comment.vue:1: v-html"
reset_diff

cat > src/OkPost.tsx <<'EOF'
export const A = ({ post }) => <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(post.body) }} />;
export const B = () => <div dangerouslySetInnerHTML={{ __html: '<b>static</b>' }} />;
export function clear(el) { el.innerHTML = ''; }
EOF
expect 0 "unsafe-html: sanitised and literal values are clean" --only unsafe-html --strict
reset_diff

# ----------------------------------------------------------------- sql-concat
cat > src/db.ts <<'EOF'
export async function find(id, name) {
  await db.query(`SELECT * FROM users WHERE id = ${id}`);
  await pool.query("SELECT * FROM users WHERE name = '" + name + "'");
  const q = `DELETE FROM sessions WHERE user_id = ${id}`;
  await knex.raw(q);
  return repo.createQueryBuilder('u').where(`u.name = '${name}'`).getMany();
}
EOF
cat > src/db.py <<'EOF'
def find(cur, uid):
    cur.execute(f"SELECT * FROM users WHERE id = {uid}")
EOF
expect 1 "sql-concat: template, concat, one-hop var, query builder, f-string" --only sql-concat
has "src/db.ts:2: SQL built from interpolated values passed to query()"
has "src/db.ts:3:"
has "src/db.ts:5: SQL built from interpolated values passed to knex.raw()"
has "src/db.ts:6: SQL built from interpolated values passed to where()"
has "src/db.py:2:"
reset_diff

cat > src/ok_db.ts <<'EOF'
export async function find(id, name) {
  await db.query('SELECT * FROM users WHERE id = $1', [id]);
  await prisma.$queryRaw`SELECT * FROM users WHERE id = ${id}`;
  await db.query(sql`SELECT * FROM users WHERE name = ${name}`);
  await repo.createQueryBuilder('u').where('u.name = :name', { name }).getMany();
  return runner.execute(`deploy ${name}`);
}
EOF
printf 'def find(cur, uid):\n    cur.execute("SELECT * FROM users WHERE id = %%s", (uid,))\n' > src/ok_db.py
expect 0 "sql-concat: bind params, tagged templates, non-SQL execute are clean" --only sql-concat --strict
reset_diff

# ----------------------------------------------------------- hardcoded-secret
printf 'export const aws = "%s";\n' "$AWS_ID" > src/aws.ts
printf 'const k = `-----BEGIN RSA PRIVATE KEY-----\nabc\n`;\n' > src/key.ts
printf 'export const config = { apiKey: "q8Fz3Lm7Rt4Vw8Yz1Ab3CdEf" };\n' > src/stripe.ts
printf 'deploy:\n  token: "ghx9Lm2Qp7Rt4Vw8Yz1Ab3Cd"\n' > ci.yml
expect 1 "hardcoded-secret: AWS id, PEM key, generic apiKey, YAML token" --only hardcoded-secret
has "src/aws.ts:1: AWS access key id"
has "src/key.ts:1: PEM private key block"
has "src/stripe.ts:1: credential-looking literal"
has "ci.yml:2: credential-looking literal"
reset_diff

cat > src/ok_cfg.ts <<'EOF'
export const config = {
  apiKey: process.env.STRIPE_KEY,
  passwordField: "user_password_input_1",
  tokenUrl: "https://auth.example.com/oauth/token",
  secret: "your-secret-goes-here-1234",
  awsDocsKey: "AKIAIOSFODNN7EXAMPLE",
};
EOF
mkdir -p fixtures; printf 'export const apiKey = "q8Fz3Lm7Rt4Vw8Yz1Ab3CdEf";\n' > fixtures/keys.ts
printf 'API_TOKEN="q8Fz3Lm7Rt4Vw8Yz1Ab3CdEf"\n' > config.example
expect 0 "hardcoded-secret: env lookups, names, URLs, placeholders, fixtures clean" --only hardcoded-secret --strict
reset_diff

# ------------------------------------------- pathological input stays linear
timed() { # timed <max-seconds> <exit> <label> [args...]: whole run under the bound
  local max="$1" exp="$2" label="$3"; shift 3
  local secs; secs=$(python3 -c '
import subprocess, sys, time
t = time.monotonic()
with open(sys.argv[2], "w") as f:
    rc = subprocess.run([sys.executable, sys.argv[1]] + sys.argv[3:], stdout=f, stderr=subprocess.STDOUT).returncode
print(f"{time.monotonic() - t:.2f} {rc}")' "$AS" "$OUT/a.out" "$@")
  local el="${secs% *}" got="${secs#* }"
  if [ "$got" -eq "$exp" ] && python3 -c "import sys; sys.exit(not float(sys.argv[1]) < float(sys.argv[2]))" "$el" "$max"; then
    PASS=$((PASS+1)); printf '  ok   %-66s\n' "$label (${el}s)"
  else FAIL=$((FAIL+1)); printf '  FAIL %-66s exit exp=%s got=%s in %ss (max %ss)\n' "$label" "$exp" "$got" "$el" "$max"; sed 's/^/       /' "$OUT/a.out" | head -20; fi
}
python3 -c 'print("const s = \"" + "token-" * 8500 + "\";")' > src/redos_secret.ts
printf 'export const config = { apiKey: "q8Fz3Lm7Rt4Vw8Yz1Ab3CdEf" };\n' >> src/redos_secret.ts
timed 3 1 "redos: 50KB token-token-... line, full run, secret still caught"
has "src/redos_secret.ts:2: credential-looking literal"
reset_diff

python3 -c 'print("a" * 200000)' > src/redos_word.ts
timed 1 0 "redos: 200KB single word, full run" --strict
reset_diff

python3 -c 'print("db.query(\"" + "select " * 60000 + "\" + id);")' > src/redos_sql.ts
printf 'export const q = (id) => db.query(`SELECT * FROM t WHERE id = ${id}`);\n' >> src/redos_sql.ts
timed 1 1 "redos: 420KB of SQL verbs with no clause, full run, concat still caught"
has "src/redos_sql.ts:2: SQL built from interpolated values"
reset_diff

# --------------------------------------------------- nest-controller-no-guard
printf "@Controller('albums')\nexport class AlbumsController {}\n" > src/albums.controller.ts
expect 0 "nest-controller-no-guard: advisory without a global guard" --only nest-controller-no-guard
has "src/albums.controller.ts:1: @Controller with no @UseGuards"
reset_diff

printf "@UseGuards(AuthGuard)\n@Controller('albums')\nexport class AlbumsController {}\n" > src/albums.controller.ts
expect 0 "nest-controller-no-guard: @UseGuards on the controller is clean" --only nest-controller-no-guard --strict
reset_diff

printf "providers: [{ provide: APP_GUARD, useClass: JwtGuard }]\n" > src/app.module.ts
git add -A; git commit -qm guard >/dev/null
printf "@Controller('tags')\nexport class TagsController {}\n" > src/tags.controller.ts
expect 0 "nest-controller-no-guard: a registered APP_GUARD silences it" --only nest-controller-no-guard --strict
reset_diff

# ------------------------------------------------------------- diff scoping
printf 'export const q = (id) => db.query(`SELECT * FROM t WHERE id = ${id}`);\n' > src/legacy.ts
git add -A; git commit -qm legacy >/dev/null
printf 'export const extra = 1;\n' >> src/legacy.ts
expect 0 "diff-scoping: untouched pre-existing finding is not re-flagged" --only sql-concat --strict
git checkout -q -- src/legacy.ts

# ---------------------------------------------- subfolder run and refusals
mkdir -p apps/api/src; printf 'export const a = 1;\n' > apps/api/src/a.ts
git add -A; git commit -qm api >/dev/null
printf 'export const a = (req) => fetch(req.body.url);\n' > apps/api/src/a.ts
( cd apps/api && python3 "$AS" --only ssrf ) >"$OUT/a.out" 2>&1; got=$?
[ "$got" -eq 1 ] && { PASS=$((PASS+1)); echo "  ok   subfolder run sees the root-relative diff"; } \
  || { FAIL=$((FAIL+1)); echo "  FAIL subfolder run exit=$got"; cat "$OUT/a.out"; }
has "apps/api/src/a.ts:1"
git checkout -q -- apps/api/src/a.ts

( cd "$NOREPO" && python3 "$AS" ) >"$OUT/a.out" 2>&1; got=$?
[ "$got" -eq 2 ] && { PASS=$((PASS+1)); echo "  ok   outside a git repo exits 2"; } \
  || { FAIL=$((FAIL+1)); echo "  FAIL outside a git repo exit=$got"; }
has "not inside a git repository"
expect 2 "unresolvable --base exits 2" --base no-such-ref
expect 2 "unknown --only check exits 2" --only nope
expect 0 "clean tree: no changes to inspect"
has "no changes to inspect"

echo
echo "appsec_check: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
