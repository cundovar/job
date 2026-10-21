/**
 * Protection de l'application par mot de passe (HTTP Basic).
 *
 * L'app est exposée sur internet (jobs.varascundo.com) : sans cette garde,
 * n'importe qui pouvait lire les candidatures, modifier une lettre, approuver
 * puis envoyer un mail via Brevo. Le navigateur affiche sa fenêtre de
 * connexion et renvoie ensuite les identifiants à chaque requête, y compris
 * les fetch du front (même origine) : le front n'a rien à changer.
 *
 * Identifiants, par ordre de priorité :
 *   1. variables APP_USER et APP_PASSWORD (Coolify ou .env) ;
 *   2. fichier data/.app_auth.json {"user": "...", "password": "..."}
 *      (data/ est monté dans le conteneur et ignoré par Git).
 *
 * Sans identifiants configurés, l'app refuse tout (fermée par défaut) :
 * une configuration oubliée ne doit jamais rouvrir l'accès public.
 */
import crypto from 'crypto';
import fs from 'fs';
import path from 'path';

const OPEN_PATHS = new Set(['/api/health']);

function loadCredentials(projectRoot) {
  const user = process.env.APP_USER;
  const password = process.env.APP_PASSWORD;
  if (user && password) return { user, password };
  const file = path.join(projectRoot, 'data', '.app_auth.json');
  try {
    const parsed = JSON.parse(fs.readFileSync(file, 'utf-8'));
    if (parsed && typeof parsed.user === 'string' && typeof parsed.password === 'string'
      && parsed.user && parsed.password) {
      return { user: parsed.user, password: parsed.password };
    }
  } catch {
    // fichier absent ou illisible : traité comme « non configuré »
  }
  return null;
}

function sameSecret(a, b) {
  // Comparaison à temps constant sur des empreintes de même longueur.
  const ha = crypto.createHash('sha256').update(String(a)).digest();
  const hb = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(ha, hb);
}

export function parseBasicAuth(header) {
  if (typeof header !== 'string' || !header.startsWith('Basic ')) return null;
  let decoded;
  try {
    decoded = Buffer.from(header.slice(6).trim(), 'base64').toString('utf-8');
  } catch {
    return null;
  }
  const separator = decoded.indexOf(':');
  if (separator < 0) return null;
  return { user: decoded.slice(0, separator), password: decoded.slice(separator + 1) };
}

export function createAuthMiddleware(projectRoot, { load = loadCredentials } = {}) {
  return (req, res, next) => {
    if (OPEN_PATHS.has(req.path)) return next();
    // Relu à chaque requête : changer le mot de passe ne demande pas de redémarrage.
    const expected = load(projectRoot);
    if (!expected) {
      return res
        .status(503)
        .type('text/plain; charset=utf-8')
        .send('Accès fermé : aucun identifiant configuré (APP_USER/APP_PASSWORD ou data/.app_auth.json).');
    }
    const given = parseBasicAuth(req.headers.authorization);
    const userOk = given && sameSecret(given.user, expected.user);
    const passwordOk = given && sameSecret(given.password, expected.password);
    if (userOk && passwordOk) return next();
    res.set('WWW-Authenticate', 'Basic realm="jobs", charset="UTF-8"');
    return res.status(401).type('text/plain; charset=utf-8').send('Authentification requise.');
  };
}
