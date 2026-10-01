// Pure persistent queue. Storage and network are injected for real Node tests.
function copy(value) { return JSON.parse(JSON.stringify(value)); }
function createOutbox(options) {
  const storage = options.storage;
  const clock = options.now || Date.now;
  const newId = options.newId;
  const key = options.key;
  let active = null;
  function read() { return storage.get(key) || []; }
  function write(rows) { storage.set(key, rows); }
  function update(id, patch) {
    const rows = read(); const item = rows.find(row => row.id === id);
    if (!item) throw new Error('本地提交记录不存在');
    Object.assign(item, patch, { updated_at: clock() }); write(rows); return copy(item);
  }
  function enqueue(kind, orderId, body, files) {
    if (!body.client_submission_id) throw new Error('提交必须携带稳定 client_submission_id');
    const rows = read(); const id = body.client_submission_id;
    const fingerprint = JSON.stringify({ kind, orderId, body, files: files || [] });
    const existing = rows.find(row => row.id === id);
    if (existing) {
      if (existing.fingerprint !== fingerprint) throw new Error('同一提交 ID 的内容不同，请合并草稿');
      return copy(existing);
    }
    const item = { id, kind, order_id: Number(orderId), body: copy(body), files: copy(files || []),
      fingerprint, status: 'queued', attempts: 0, created_at: clock(), updated_at: clock(), next_retry_at: 0,
      result: null, error: null, sent_body: null };
    rows.push(item); write(rows); return copy(item);
  }
  async function perform(transport) {
    const rows = read();
    // A process interruption cannot leave a record permanently marked sending.
    for (const item of rows) if (item.status === 'sending') item.status = 'queued';
    write(rows);
    for (const original of read()) {
      if (original.status !== 'queued' || original.next_retry_at > clock()) continue;
      const currentRows = read();
      const blockers = currentRows.slice(0, currentRows.findIndex(item => item.id === original.id)).filter(item => item.order_id === original.order_id && !['synced', 'superseded'].includes(item.status));
      if (blockers.length) continue;
      let item = update(original.id, { status: 'sending', attempts: original.attempts + 1, error: null });
      try {
        if (!item.sent_body) {
          const attachments = (item.body.attachment_ids || []).slice();
          for (let i = 0; i < item.files.length; i++) {
            let file = item.files[i];
            if (!file.attachment_id) {
              const result = await transport.upload(item.order_id, file);
              if (!result.attachment_id && !result.id) throw new Error('上传未返回附件 ID');
              file.attachment_id = Number(result.attachment_id || result.id);
              item.files[i] = file; item = update(item.id, { files: item.files });
            }
            if (!attachments.includes(file.attachment_id)) attachments.push(file.attachment_id);
          }
          const body = copy(item.body);
          if (item.kind === 'observation' || item.kind === 'attachment') body.attachment_ids = attachments;
          item = update(item.id, { sent_body: body });
        }
        const result = await transport.send(item.kind, item.order_id, item.sent_body);
        update(item.id, { status: 'synced', result, error: null });
      } catch (error) {
        const status = Number(error.statusCode || 0);
        const retryable = !status || status === 429 || status >= 500;
        update(item.id, { status: status === 409 ? 'conflict' : error.uploadUncertain ? 'upload_uncertain' : retryable ? 'queued' : 'blocked',
          error: { message: error.message || '同步失败', statusCode: status, missing_fields: error.missing_fields || [] },
          next_retry_at: clock() + Math.min(60000, 1000 * Math.pow(2, Math.min(item.attempts, 6))) });
      }
    }
    return read();
  }
  function sync(transport) {
    if (!active) active = perform(transport).finally(() => { active = null; });
    return active;
  }
  function retry(id) {
    const item = read().find(row => row.id === id);
    if (!item || item.status !== 'queued') throw new Error('冲突和无权限项需先核对，不能自动重试');
    return update(id, { next_retry_at: 0 });
  }
  function rebase(id, snapshot, confirmed) {
    const item = read().find(row => row.id === id);
    if (!confirmed || !item || !['conflict', 'blocked'].includes(item.status)) throw new Error('必须先人工核对冲突内容');
    if (snapshot.installation_id !== item.body.installation_id || snapshot.round !== item.body.round) throw new Error('安装身份或轮次已改变，禁止覆盖；请重新扫码创建当前轮草稿');
    if (!Number.isInteger(snapshot.order_version)) throw new Error('服务器版本无效');
    const body = Object.assign(copy(item.sent_body || item.body), { order_version: snapshot.order_version, client_submission_id: newId() });
    update(id, { status: 'superseded' });
    const revised = enqueue(item.kind, item.order_id, body, item.files);
    return update(revised.id, { supersedes_id: id });
  }
  function reconcileFile(id, fileId, attachmentId) {
    const item = read().find(row => row.id === id);
    if (!item || item.status !== 'upload_uncertain') throw new Error('此记录没有待核对的上传');
    const file = item.files.find(row => row.client_file_id === fileId);
    if (!file || !Number.isInteger(attachmentId) || attachmentId < 1) throw new Error('请输入已核对的当前工单附件 ID');
    file.attachment_id = attachmentId;
    return update(id, { files: item.files, status: 'queued', next_retry_at: 0 });
  }
  function confirmUploadNotPresent(id, confirmed) {
    const item = read().find(row => row.id === id);
    if (!confirmed || !item || item.status !== 'upload_uncertain') throw new Error('请先核对服务端附件记录');
    return update(id, { status: 'queued', next_retry_at: 0 });
  }
  function editBlocked(id, snapshot) {
    const item = read().find(row => row.id === id);
    if (!item || !['blocked', 'conflict'].includes(item.status) || item.kind !== 'observation') throw new Error('只可恢复未提交的观察记录');
    if (snapshot.installation_id !== item.body.installation_id || snapshot.round !== item.body.round) throw new Error('身份或轮次已改变，不能把旧测量改写到新安装');
    update(id, { status: 'superseded' }); return copy(item);
  }
  return { list: () => copy(read()), enqueue, sync, retry, rebase, reconcileFile,
    confirmUploadNotPresent,
    editBlocked,
    pending: orderId => read().filter(item => (!orderId || item.order_id === Number(orderId)) && !['synced', 'superseded'].includes(item.status)) };
}
module.exports = { createOutbox };
