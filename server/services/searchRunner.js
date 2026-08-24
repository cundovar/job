/**
 * searchRunner.js — Lance le pipeline Python (le même que le tool Hermes `job_today`)
 * en arrière-plan et expose son état pour que le front puisse l'afficher/le poller.
 */

import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import { PROJECT_ROOT } from '../config.js';

const CACHE_PATH = path.join(PROJECT_ROOT, 'data', 'jobs_cache.json');
const LOG_PATH = path.join(PROJECT_ROOT, 'data', 'logs', 'last_search.log');
const MAX_LOG_TAIL = 4000; // caractères conservés en mémoire pour /status

let state = {
  running: false,
  startedAt: null,
  finishedAt: null,
  exitCode: null,
  error: null,
  logTail: '',
};

function summarizeCache() {
  try {
    const raw = fs.readFileSync(CACHE_PATH, 'utf-8');
    const jobs = JSON.parse(raw);
    if (!Array.isArray(jobs)) return null;
    const stats = { total: jobs.length, postuler: 0, peut_etre: 0, passer: 0 };
    for (const job of jobs) {
      const reco = job?.ai_analysis?.recommandation;
      if (reco === 'POSTULER') stats.postuler++;
      else if (reco === 'PEUT-ÊTRE') stats.peut_etre++;
      else if (reco === 'PASSER') stats.passer++;
    }
    return stats;
  } catch {
    return null;
  }
}

export function getStatus() {
  return { ...state, lastResult: state.running ? null : summarizeCache() };
}

export function startSearch() {
  if (state.running) {
    return { alreadyRunning: true, ...getStatus() };
  }

  fs.mkdirSync(path.dirname(LOG_PATH), { recursive: true });
  const logStream = fs.createWriteStream(LOG_PATH, { flags: 'a' });

  state = {
    running: true,
    startedAt: new Date().toISOString(),
    finishedAt: null,
    exitCode: null,
    error: null,
    logTail: '',
  };

  const child = spawn('python3', ['-u', 'main.py'], {
    cwd: PROJECT_ROOT,
    env: process.env,
  });

  const appendTail = (chunk) => {
    state.logTail = (state.logTail + chunk).slice(-MAX_LOG_TAIL);
  };

  child.stdout.on('data', (chunk) => {
    logStream.write(chunk);
    appendTail(chunk.toString());
  });
  child.stderr.on('data', (chunk) => {
    logStream.write(chunk);
    appendTail(chunk.toString());
  });

  child.on('error', (err) => {
    state.running = false;
    state.finishedAt = new Date().toISOString();
    state.error = err.message;
    logStream.end();
  });

  child.on('close', (code) => {
    state.running = false;
    state.finishedAt = new Date().toISOString();
    state.exitCode = code;
    if (code !== 0) state.error = `Le pipeline a quitté avec le code ${code}`;
    logStream.end();
  });

  return { alreadyRunning: false, ...getStatus(), running: true };
}
