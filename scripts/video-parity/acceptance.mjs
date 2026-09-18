/** Assertions over real run records. No answers, model substitutes or API mocks. */
import assert from 'node:assert/strict';

export function assertFullJourney({ resumed, turns, persisted, episode }) {
  assert.equal(resumed, false, 'A resumed run is recovery evidence, not a fresh full journey');
  const required = ['01-commitment', '02-diagnosis', '04-revision', '04b-bridge',
    '05-computation', '05b-request-reconstruction', '06-reconstruction', '09-transfer',
    '10-solo', '10b-solo-incorrect', '11-solo-answer'];
  let previous = -1;
  for (const name of required) {
    const index = turns.findIndex(turn => turn.name === name);
    assert.ok(index > previous, `Missing or out-of-order scene: ${name}`);
    previous = index;
  }
  assert.ok(turns.every(turn => turn.episode === episode), 'Cross-episode turn');
  assert.equal(new Set(turns.map(turn => turn.turnId)).size, turns.length, 'Replayed turn counted as a new scene');
  assert.equal(persisted.conversation_id, episode);
  assert.equal(persisted.result?.conversation_id, episode);
  assert.equal(persisted.durable_phase?.phase, 'complete');
  assert.equal(persisted.result?.learning_loop_completed, true);
  const evidence = persisted.learning_evidence;
  assert.ok(Array.isArray(evidence));
  assert.equal(new Set(evidence.map(item => item.id)).size, evidence.length);
  const turnIds = new Set(turns.map(turn => turn.turnId));
  for (const kind of ['commitment', 'diagnosis_inference', 'student_attempt', 'teach_back',
    'transfer_verified', 'solo_assigned', 'transfer_failed', 'solo_verified']) {
    assert.ok(evidence.some(item => item.kind === kind && turnIds.has(item.turn_id)),
      `Missing persisted evidence from this run: ${kind}`);
  }
  const soloTurn = turns.find(turn => turn.name === '11-solo-answer');
  assert.ok(evidence.some(item => item.kind === 'solo_verified' && item.turn_id === soloTurn.turnId));
  const incorrectTurn = turns.find(turn => turn.name === '10b-solo-incorrect');
  assert.ok(!evidence.some(item => item.kind === 'solo_verified' && item.turn_id === incorrectTurn.turnId));
}
