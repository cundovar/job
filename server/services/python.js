/**
 * services/python.js — Lancer un script Python du projet depuis le serveur.
 *
 * Les routes appelaient `execFile` chacune à leur façon (délai, taille de
 * sortie, message d'erreur). Ce module est le seul chemin : arguments en
 * tableau (jamais de shell), répertoire du projet, délai et taille bornés, et
 * une erreur qui porte la fin de stderr au lieu d'un « Command failed » muet.
 *
 * Les deux tâches longues (génération de CV, préparation de candidature)
 * gardent leur `spawn` dédié : elles suivent l'avancement et tuent le
 * processus à l'échéance, ce qu'un appel ponctuel n'a pas à faire.
 */
import { execFile } from 'child_process';
import { PROJECT_ROOT } from '../config.js';

export const PYTHON_BIN = process.env.CV_PYTHON_BIN || process.env.PYTHON_BIN || 'python3';
const DEFAULT_TIMEOUT_MS = 60_000;
const DEFAULT_MAX_BUFFER = 20 * 1024 * 1024;

/**
 * @param {string[]} args arguments passés à Python (ex. ['-m', 'agency_scout', 'list'])
 * @param {{ timeout?: number, maxBuffer?: number, bin?: string, acceptOutputOnError?: boolean }} [options]
 * @returns {Promise<string>} la sortie standard
 */
export function runPython(args, options = {}) {
  const {
    timeout = DEFAULT_TIMEOUT_MS,
    maxBuffer = DEFAULT_MAX_BUFFER,
    bin = PYTHON_BIN,
    // Certains scripts sortent avec un code non nul tout en écrivant un JSON
    // utile (applications.send renvoie 1 pour un dossier refusé) : la sortie
    // est alors rendue telle quelle au lieu d'une erreur.
    acceptOutputOnError = false,
  } = options;
  return new Promise((resolve, reject) => {
    execFile(bin, args, { cwd: PROJECT_ROOT, timeout, maxBuffer }, (err, stdout, stderr) => {
      if (!err) return resolve(stdout);
      if (acceptOutputOnError && stdout) return resolve(stdout);
      const detail = String(stderr || '').trim().slice(-1500);
      const error = new Error(detail ? `${err.message}\n${detail}` : err.message);
      error.code = err.code;
      error.stdout = stdout;
      reject(error);
    });
  });
}

/** Raccourci pour `python3 -m <module> ...args`. */
export function runPythonModule(module, args = [], options = {}) {
  return runPython(['-m', module, ...args], options);
}
