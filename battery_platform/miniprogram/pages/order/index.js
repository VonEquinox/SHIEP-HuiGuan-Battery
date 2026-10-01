const api = require('../../utils/api');
const { showError, requireSession, uuid } = require('../../utils/ui');
Page({
  data: { orderId: null, order: {}, inspection: null, legacy: false, note: '', busy: false, verified: null, pending: 0, events: [] },
  onLoad(query) { this.setData({ orderId: Number(query.id) }); },
  onShow() { if (requireSession()) this.refresh(); },
  onPullDownRefresh() { this.refresh(); },
  async refresh() {
    try {
      const order = await api.request('/api/orders/' + this.data.orderId);
      let inspection = null; let legacy = false;
      try { inspection = await api.request('/api/v2/orders/' + this.data.orderId + '/inspection'); }
      catch (error) { if (error.statusCode === 409) legacy = true; else throw error; }
      const app = getApp(); let verified = wx.getStorageSync(app.verifiedKey(this.data.orderId)) || null;
      const validAssets = inspection && inspection.assets || [];
      if (verified && (!validAssets.some(asset => asset.asset_id === verified.asset_id && asset.current_installation_id === verified.installation_id) || verified.expires_at * 1000 <= Date.now())) verified = null;
      this.setData({ order, inspection, legacy, verified, pending: app.outbox().pending(this.data.orderId).length, events: (order.events || []).slice().reverse() });
      wx.setStorageSync('hg_inspection:' + app.namespace() + ':' + this.data.orderId, inspection);
    } catch (error) { showError(error); } finally { wx.stopPullDownRefresh(); }
  },
  note(event) { this.setData({ note: event.detail.value }); },
  async transition(event) {
    if (this.data.busy) return; this.setData({ busy: true });
    try { await api.request('/api/orders/' + this.data.orderId + '/transition', 'POST', { action: event.currentTarget.dataset.action, version: this.data.order.version, note: this.data.note }); await this.refresh(); }
    catch (error) { showError(error); } finally { this.setData({ busy: false }); }
  },
  navigate(event) { wx.navigateTo({ url: '/pages/' + event.currentTarget.dataset.page + '/index?id=' + this.data.orderId }); },
  async submitRound() {
    try {
      const value = this.data.inspection;
      if (!value || !value.current_round) throw new Error('当前没有开放轮次');
      if (!this.data.verified) throw new Error('请先扫码核验当前安装身份');
      if (getApp().outbox().pending(this.data.orderId).length) throw new Error('请先同步或处理本工单待提交记录，再完成本轮');
      getApp().outbox().enqueue('round', this.data.orderId, { round: value.current_round, order_version: this.data.order.version, installation_id: this.data.verified.installation_id, client_submission_id: uuid() });
      await getApp().sync(); await this.refresh();
      wx.navigateTo({ url: '/pages/outbox/index?id=' + this.data.orderId });
    } catch (error) { showError(error); }
  }
});
