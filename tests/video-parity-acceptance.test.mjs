import test from 'node:test';
import assert from 'node:assert/strict';
import { assertFullJourney } from '../scripts/video-parity/acceptance.mjs';

// Explicit test fixture for the acceptance checker, never a product response.
function fixture() {
  const names = ['01-commitment', '02-diagnosis', '04-revision', '04b-bridge',
    '05-computation', '05b-request-reconstruction', '06-reconstruction', '09-transfer',
    '10-solo', '10b-solo-incorrect', '11-solo-answer'];
  const turns = names.map((name, index) => ({ name, episode: 'episode', turnId: `turn-${index}` }));
  const kinds = ['commitment', 'diagnosis_inference', 'student_attempt', 'teach_back',
    'transfer_verified', 'solo_assigned', 'transfer_failed', 'solo_verified'];
  const learning_evidence = kinds.map((kind, index) => ({id: `e-${index}`, kind,
    turn_id: kind === 'solo_verified' ? 'turn-10' : 'turn-1'}));
  return { resumed: false, episode: 'episode', turns, persisted: {
    conversation_id: 'episode', durable_phase: { phase: 'complete' },
    result: { conversation_id: 'episode', learning_loop_completed: true }, learning_evidence,
  } };
}

test('full journey requires every scene and episode-bound persisted evidence', () => {
  assert.doesNotThrow(() => assertFullJourney(fixture()));
  for (let index = 0; index < fixture().turns.length; index++) {
    const input = fixture(); input.turns.splice(index, 1);
    assert.throws(() => assertFullJourney(input), /Missing or out-of-order/);
  }
});

test('recovery, old course totals and incorrect Solo cannot count as full acceptance', () => {
  const resumed = fixture(); resumed.resumed = true;
  assert.throws(() => assertFullJourney(resumed), /resumed/);
  const foreign = fixture(); foreign.persisted.learning_evidence.forEach(item => { item.turn_id = 'old-turn'; });
  assert.throws(() => assertFullJourney(foreign), /Missing persisted/);
  const wrong = fixture(); wrong.persisted.learning_evidence.push({id:'bad',kind:'solo_verified',turn_id:'turn-9'});
  assert.throws(() => assertFullJourney(wrong));
  const duplicate = fixture(); duplicate.turns[1].turnId = duplicate.turns[0].turnId;
  assert.throws(() => assertFullJourney(duplicate), /Replayed/);
});
