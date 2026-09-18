/** Real persisted state/retry check; works for incomplete episodes too. */
import { chromium, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';

const episode = process.env.QA_VIDEO_RESUME;
const session = process.env.QA_VIDEO_SESSION_FILE;
const snapshot = process.env.QA_VIDEO_RECOVERY_SNAPSHOT;
if (!episode || !session || !snapshot) throw new Error('Authorized session, episode and snapshot path required');
const base = process.env.BASE_URL ?? 'http://127.0.0.1:3000';
const query = new URLSearchParams({
  course_id: process.env.QA_VIDEO_COURSE ?? '7c33796f-8d45-5fd7-93b9-13ae8c7572eb',
  curriculum_edition_id: process.env.QA_VIDEO_EDITION ?? '5dd085cb-831c-5ed1-ae01-327f700dc12a',
}).toString();
const browser = await chromium.launch();
try {
  const context = await browser.newContext({storageState: session, viewport: {width: 1366, height: 768}});
  const page = await context.newPage();
  await page.addInitScript(({episode, query}) => {
    const scope = new URLSearchParams(query);
    localStorage.setItem('qa_course_key', `${scope.get('course_id')}:${scope.get('curriculum_edition_id')}`);
    localStorage.setItem('qa_conversation_id', episode);
  }, {episode, query});
  const start = performance.now();
  await page.goto(`${base}/agent`);
  await expect(page.getByTestId('learning-phase')).toBeVisible();
  const restoreMs = performance.now() - start;
  const read = () => page.evaluate(async url => {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`state HTTP ${response.status}`);
    return response.json();
  }, `/api/teaching/threads/${episode}/state?${query}`);
  const before = await read();
  expect(before.conversation_id).toBe(episode);
  const fingerprint = state => ({
    episode: state.conversation_id, turn: state.turn_id, phase: state.durable_phase,
    evidence: state.learning_evidence, result: state.result,
  });
  if (process.env.QA_VIDEO_COMPARE === '1') {
    expect(fingerprint(before)).toEqual(JSON.parse(readFileSync(snapshot, 'utf8')));
  } else writeFileSync(snapshot, JSON.stringify(fingerprint(before), null, 2));
  if (process.env.QA_VIDEO_REPLAY_REQUEST) {
    const body = readFileSync(process.env.QA_VIDEO_REPLAY_REQUEST, 'utf8');
    const responses = await page.evaluate(async ({query, body}) => Promise.all([0, 1].map(async () => {
      const response = await fetch(`/api/teaching/turns/stream?${query}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body,
      });
      return {status: response.status, text: await response.text()};
    })), {query, body});
    for (const response of responses) {
      expect(response.status).toBe(200);
      expect(response.text).toContain(before.turn_id);
      expect(response.text).toContain('workflow.completed');
    }
    expect(fingerprint(await read())).toEqual(fingerprint(before));
  }
  await page.reload();
  await expect(page.getByTestId('learning-phase')).toHaveAttribute('data-phase', before.durable_phase.phase);
  expect(fingerprint(await read())).toEqual(fingerprint(before));
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await page.screenshot({path: `${snapshot}.${process.env.QA_VIDEO_COMPARE === '1' ? 'after' : 'before'}.png`});
  console.log(JSON.stringify({episode, turn: before.turn_id, phase: before.durable_phase.phase,
    evidenceCount: before.learning_evidence.length, restoreMs, compared: process.env.QA_VIDEO_COMPARE === '1',
    concurrentReplays: process.env.QA_VIDEO_REPLAY_REQUEST ? 2 : 0}));
} finally { await browser.close(); }
