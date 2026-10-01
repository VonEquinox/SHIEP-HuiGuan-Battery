const environment = require('./environment');
const { createOutbox } = require('./utils/outbox');
const { uuid } = require('./utils/ui');
App({
  globalData: { apiBaseUrl: '', session: null, network: true },
  onLaunch() {
    this.globalData.apiBaseUrl = wx.getStorageSync('hg_api_base') || environment.apiBaseUrl;
    wx.onNetworkStatusChange(change => {
      this.globalData.network = change.isConnected;
      if (change.isConnected && this.globalData.session) this.sync().catch(() => {});
    });
    wx.getNetworkType({ success: result => { this.globalData.network = result.networkType !== 'none'; } });
  },
  setSession(result) {
    this.globalData.session = { token: result.token, user: result.user, expiresAt: Date.now() + result.expires_in * 1000 };
    this.sync().catch(() => {});
  },
  clearSession() { clearTimeout(this._retryTimer); this.globalData.session = null; },
  namespace() {
    const session = this.globalData.session;
    if (!session) throw new Error('请先登录');
    return encodeURIComponent(this.globalData.apiBaseUrl) + ':' + session.user.id;
  },
  outbox() {
    return createOutbox({ key: 'hg_outbox:' + this.namespace(), newId: uuid,
      storage: { get: key => wx.getStorageSync(key), set: (key, value) => wx.setStorageSync(key, value) } });
  },
  draftKey(orderId) { return 'hg_draft:' + this.namespace() + ':' + orderId; },
  verifiedKey(orderId) { return 'hg_verified:' + this.namespace() + ':' + orderId; },
  sync() {
    if (!this.globalData.session) return Promise.reject(new Error('请登录后同步'));
    if (!this._syncPromise) {
      clearTimeout(this._retryTimer);
      this._syncPromise = this.outbox().sync(require('./utils/api').transport).then(rows => {
        const eligible = rows.filter((item, index) => item.status === 'queued' && !rows.slice(0, index).some(previous => previous.order_id === item.order_id && !['synced', 'superseded'].includes(previous.status)));
        if (this.globalData.session && this.globalData.network && eligible.length) {
          const next = Math.min(...eligible.map(item => item.next_retry_at || Date.now()));
          this._retryTimer = setTimeout(() => { if (this.globalData.session && this.globalData.network) this.sync().catch(() => {}); }, Math.max(1000, next - Date.now()));
        }
        return rows;
      }).finally(() => { this._syncPromise = null; });
    }
    return this._syncPromise;
  }
});
