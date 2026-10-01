const test = require('node:test');
const assert = require('node:assert/strict');
const { createOutbox } = require('../utils/outbox');
const { validateBaseUrl, normalizeError } = require('../utils/api');
function fixture() {
  const db = new Map(); let time = 100; let sequence = 0;
  const queue = createOutbox({ key: 'test-user-1', newId: () => 'rebased-id-' + (++sequence), now: () => time,
    storage: { get: key => db.get(key), set: (key, value) => db.set(key, JSON.parse(JSON.stringify(value))) } });
  return { queue, db, advance: () => { time += 100000; } };
}
const body = id => ({ client_submission_id: id, installation_id: 'installation-1', round: 1, order_version: 3, attachment_ids: [], free_text: '独立仪表仍需复核' });
test('identical enqueue is deduplicated; different content with same UUID is rejected', () => {
  const { queue } = fixture(); queue.enqueue('observation', 7, body('stable-id-1')); queue.enqueue('observation', 7, body('stable-id-1'));
  assert.equal(queue.list().length, 1);
  assert.throws(() => queue.enqueue('observation', 7, Object.assign(body('stable-id-1'), { free_text: 'different' })), /内容不同/);
});
test('lost observation response retries immutable payload and same id, then completes once', async () => {
  const { queue, advance } = fixture(); queue.enqueue('observation', 7, body('stable-id-1'));
  const calls = []; let attempts = 0; let serverWrites = 0; const seen = new Map();
  const transport = { async send(kind, order, value) {
    calls.push(JSON.parse(JSON.stringify(value)));
    if (!seen.has(value.client_submission_id)) { seen.set(value.client_submission_id, { observation_id: ++serverWrites }); }
    if (++attempts === 1) throw new Error('response lost after server commit');
    return seen.get(value.client_submission_id);
  } };
  await queue.sync(transport); assert.equal(queue.list()[0].status, 'queued');
  advance(); await queue.sync(transport); assert.equal(queue.list()[0].status, 'synced'); assert.equal(serverWrites, 1); assert.deepEqual(calls[0], calls[1]);
});
test('same-order dependencies stop on conflict even when created at same millisecond', async () => {
  const { queue } = fixture(); queue.enqueue('observation', 7, body('stable-id-1')); queue.enqueue('round', 7, body('stable-id-2'));
  let attempts = 0; const transport = { async send() { attempts++; throw Object.assign(new Error('version conflict'), { statusCode: 409 }); } };
  await queue.sync(transport); await queue.sync(transport);
  assert.equal(attempts, 1); assert.equal(queue.list()[0].status, 'conflict'); assert.equal(queue.list()[1].status, 'queued');
});
test('explicit conflict rebase retains original and refuses changed installation or round', async () => {
  const { queue } = fixture(); queue.enqueue('observation', 7, body('stable-id-1'));
  await queue.sync({ async send() { throw Object.assign(new Error('version conflict'), { statusCode: 409 }); } });
  assert.throws(() => queue.rebase('stable-id-1', { installation_id: 'other-installation', round: 1, order_version: 4 }, true), /安装身份/);
  assert.throws(() => queue.rebase('stable-id-1', { installation_id: 'installation-1', round: 2, order_version: 4 }, true), /轮次/);
  assert.throws(() => queue.rebase('stable-id-1', { installation_id: 'installation-1', round: 1, order_version: 4 }, false), /人工核对/);
  const revised = queue.rebase('stable-id-1', { installation_id: 'installation-1', round: 1, order_version: 4 }, true);
  assert.equal(revised.body.order_version, 4); assert.notEqual(revised.id, 'stable-id-1'); assert.equal(revised.supersedes_id, 'stable-id-1'); assert.equal(queue.list()[0].status, 'superseded');
});
test('attachments saved once are reused on observation retry', async () => {
  const { queue, advance } = fixture(); queue.enqueue('observation', 7, body('stable-id-1'), [{ path: '/persistent/photo.jpg', client_file_id: 'file-id-1' }]);
  let uploads = 0; let sends = 0; const transport = { async upload() { uploads++; return { id: 22 }; }, async send(kind, order, value) { assert.deepEqual(value.attachment_ids, [22]); if (++sends === 1) throw new Error('network'); return { observation_id: 2 }; } };
  await queue.sync(transport); advance(); await queue.sync(transport); assert.equal(uploads, 1); assert.equal(queue.list()[0].status, 'synced');
});
test('ambiguous photo upload stops until explicit reconciliation', async () => {
  const { queue, advance } = fixture(); queue.enqueue('observation', 7, body('stable-id-1'), [{ path: '/persistent/photo.jpg', client_file_id: 'file-id-1' }]);
  let uploads = 0; const transport = { async upload() { uploads++; throw Object.assign(new Error('upload response lost'), { uploadUncertain: true }); }, async send() { throw new Error('must not post'); } };
  await queue.sync(transport); advance(); await queue.sync(transport);
  assert.equal(uploads, 1); assert.equal(queue.list()[0].status, 'upload_uncertain');
  queue.reconcileFile('stable-id-1', 'file-id-1', 22);
  await queue.sync({ async send(kind, order, value) { assert.deepEqual(value.attachment_ids, [22]); return { observation_id: 2 }; } });
  assert.equal(queue.list()[0].status, 'synced');
});
test('permissions and format errors are blocked instead of retried', async () => {
  for (const statusCode of [401,403,422]) {
    const { queue, advance } = fixture(); queue.enqueue('observation', 7, body('stable-id-1')); let attempts = 0;
    const transport = { async send() { attempts++; throw Object.assign(new Error('invalid'), { statusCode, missing_fields: ['instrument_id'] }); } };
    await queue.sync(transport); advance(); await queue.sync(transport); assert.equal(attempts, 1); assert.equal(queue.list()[0].status, 'blocked');
  }
});
test('concurrent sync calls share one flight and preserve submission uniqueness', async () => {
  const { queue } = fixture(); queue.enqueue('observation', 7, body('stable-id-1')); let calls = 0;
  await Promise.all([queue.sync({ async send() { calls++; return { id: 1 }; } }), queue.sync({ async send() { calls++; return { id: 1 }; } })]);
  assert.equal(calls, 1);
});
test('process interruption recovers sending record using the persisted same payload', async () => {
  const { queue, db } = fixture(); queue.enqueue('observation', 7, body('stable-id-1'));
  const rows = db.get('test-user-1'); rows[0].status = 'sending'; rows[0].sent_body = body('stable-id-1'); db.set('test-user-1', rows);
  await queue.sync({ async send(kind, order, value) { assert.equal(value.client_submission_id,'stable-id-1'); return { observation_id:33 }; } });
  assert.equal(queue.list()[0].status,'synced');
});
test('blocked observation can return to a draft without deleting its source record', async () => {
  const { queue } = fixture(); queue.enqueue('observation',7,body('stable-id-1'));
  await queue.sync({async send(){throw Object.assign(new Error('missing instrument'),{statusCode:422});}});
  const draft=queue.editBlocked('stable-id-1',{installation_id:'installation-1',round:1});
  assert.equal(draft.body.free_text,'独立仪表仍需复核'); assert.equal(queue.list()[0].status,'superseded');
});
test('phone endpoint rejects loopback HTTP and malformed URLs; simulator opt-in is explicit', () => {
  assert.equal(validateBaseUrl('https://battery.example.com/'), 'https://battery.example.com');
  for (const value of ['http://127.0.0.1:8787','https://localhost:8787','https://battery.example.com/api','https://user:secret@battery.example.com','https://battery.example.com?token=secret']) assert.throws(() => validateBaseUrl(value));
  assert.equal(validateBaseUrl('http://127.0.0.1:8787',true),'http://127.0.0.1:8787');
  const error = normalizeError({ statusCode:422,data:{ message:'本轮信息不完整',detail:{missing_fields:['test:T_TIME_ALIGN']},missing_fields:[] } });
  assert.deepEqual(error.missing_fields,['test:T_TIME_ALIGN']);
});
