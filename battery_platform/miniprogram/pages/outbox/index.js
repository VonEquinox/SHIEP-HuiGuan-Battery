const api = require('../../utils/api');
const { requireSession, showError, pretty } = require('../../utils/ui');
const labels = { queued: '待同步 · 尚未提交', sending: '同步中', synced: '服务器已接收', conflict: '版本冲突 · 未提交', blocked: '校验或权限问题 · 未提交', upload_uncertain: '上传响应中断 · 待核对', superseded: '旧草稿已保留，由新提交替代' };
Page({
  data: { orderId: null, records: [], busy: false, review: null, attachmentId: '' },
  onLoad(query) { this.setData({ orderId: query.id ? Number(query.id) : null }); },
  onShow() { if (requireSession()) this.refresh(); },
  refresh() { if (!requireSession()) return; const records = getApp().outbox().list().filter(item => !this.data.orderId || item.order_id === this.data.orderId).reverse().map(item => Object.assign({}, item, { label: labels[item.status], bodyText: pretty(item.sent_body || item.body), resultText: item.result ? pretty(item.result) : '' })); this.setData({ records }); },
  async sync() { if (this.data.busy) return; this.setData({ busy: true }); try { await getApp().sync(); } catch (error) { showError(error); } finally { this.setData({ busy: false }); this.refresh(); } },
  async retry(event) { try { getApp().outbox().retry(event.currentTarget.dataset.id); await this.sync(); } catch (error) { showError(error); } },
  async review(event) {
    try {
      const item = getApp().outbox().list().find(record => record.id === event.currentTarget.dataset.id);
      const order = await api.request('/api/orders/' + item.order_id);
      let inspection = null;
      try { inspection = await api.request('/api/v2/orders/' + item.order_id + '/inspection'); } catch (error) { if (error.statusCode !== 409) throw error; }
      const asset = inspection && inspection.assets.find(row => row.installation_id === item.body.installation_id && row.current_installation_id === item.body.installation_id);
      this.setData({ review: { item, order, inspection, snapshot: { installation_id: asset && asset.current_installation_id, round: inspection && inspection.current_round, order_version: order.version },
        serverObservations: pretty(inspection && inspection.observations || []), attachments: order.attachments || [], draftText: pretty(item.sent_body || item.body) }, attachmentId: '' });
    } catch (error) { showError(error); }
  },
  async rebase() { try { const review = this.data.review; getApp().outbox().rebase(review.item.id, review.snapshot, true); this.setData({ review: null }); this.refresh(); } catch (error) { showError(error); } },
  editDraft() {
    try {
      const app = getApp(); const review = this.data.review;
      const item = app.outbox().editBlocked(review.item.id, review.snapshot); const body = item.sent_body || item.body;
      const first = (body.measurements || [])[0] || {}; const form = Object.assign({}, body, { metric: first.metric || '', value: first.value == null ? '' : String(first.value), unit: first.unit || '', method: first.method || '' });
      for (const key of ['observed_symptoms', 'performed_actions', 'confirmed_hypotheses', 'excluded_hypotheses', 'unresolved_items', 'assertion_targets']) form[key] = (body[key] || []).join('\n');
      // Uploaded IDs remain on their persisted file records, so reopening cannot
      // turn a successful upload into another physical attachment submission.
      wx.setStorageSync(app.draftKey(item.order_id), { form, files: item.files, test_id: body.test_id, installation_ids: review.inspection.assets.map(asset => asset.installation_id), round: review.inspection.current_round, order_version: review.order.version, saved_at: Date.now() });
      wx.redirectTo({ url: '/pages/inspection/index?id=' + item.order_id });
    } catch (error) { showError(error); }
  },
  attachmentId(event) { this.setData({ attachmentId: event.detail.value }); },
  async reconcile() {
    try {
      const review = this.data.review; const id = Number(this.data.attachmentId);
      if (!review.attachments.some(item => item.id === id)) throw new Error('附件必须存在于服务器返回的当前工单列表');
      const file = review.item.files.find(item => !item.attachment_id);
      if (!file) throw new Error('没有待核对的本地附件');
      getApp().outbox().reconcileFile(review.item.id, file.client_file_id, id); this.setData({ review: null }); this.refresh();
    } catch (error) { showError(error); }
  },
  async notPresent() {
    try { getApp().outbox().confirmUploadNotPresent(this.data.review.item.id, true); this.setData({ review: null }); this.refresh(); } catch (error) { showError(error); }
  },
  openOrder(event) { wx.navigateTo({ url: '/pages/order/index?id=' + event.currentTarget.dataset.id }); }
});
