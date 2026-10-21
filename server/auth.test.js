import test from 'node:test';
import assert from 'node:assert/strict';
import { createAuthMiddleware, parseBasicAuth } from './auth.js';

function run(middleware, { path = '/api/applications', authorization } = {}) {
  const req = { path, headers: authorization ? { authorization } : {} };
  const res = {
    statusCode: 200,
    headers: {},
    body: null,
    status(code) { this.statusCode = code; return this; },
    type() { return this; },
    set(key, value) { this.headers[key] = value; return this; },
    send(body) { this.body = body; return this; },
  };
  let passed = false;
  middleware(req, res, () => { passed = true; });
  return { passed, res };
}

const basic = (user, password) => 'Basic ' + Buffer.from(`${user}:${password}`).toString('base64');
const configured = createAuthMiddleware('/x', { load: () => ({ user: 'cundo', password: 's3cret:avec' }) });

test('refuse sans identifiants et demande la connexion', () => {
  const { passed, res } = run(configured);
  assert.equal(passed, false);
  assert.equal(res.statusCode, 401);
  assert.match(res.headers['WWW-Authenticate'], /^Basic/);
});

test('accepte les bons identifiants, mot de passe contenant « : »', () => {
  assert.equal(run(configured, { authorization: basic('cundo', 's3cret:avec') }).passed, true);
});

test('refuse un mauvais mot de passe ou utilisateur', () => {
  assert.equal(run(configured, { authorization: basic('cundo', 'faux') }).passed, false);
  assert.equal(run(configured, { authorization: basic('autre', 's3cret:avec') }).passed, false);
  assert.equal(run(configured, { authorization: 'Bearer x' }).passed, false);
});

test('/api/health reste ouvert', () => {
  assert.equal(run(configured, { path: '/api/health' }).passed, true);
});

test('fermé par défaut sans configuration', () => {
  const closed = createAuthMiddleware('/x', { load: () => null });
  const { passed, res } = run(closed, { authorization: basic('a', 'b') });
  assert.equal(passed, false);
  assert.equal(res.statusCode, 503);
});

test('parseBasicAuth', () => {
  assert.deepEqual(parseBasicAuth(basic('u', 'p:q')), { user: 'u', password: 'p:q' });
  assert.equal(parseBasicAuth('Basic !!!'), null);
  assert.equal(parseBasicAuth(undefined), null);
});
