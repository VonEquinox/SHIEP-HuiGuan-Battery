const api = require('../../utils/api');
const { showError, requireSession } = require('../../utils/ui');
Page({
  data: { orderId: null, token: '', busy: false, verified: null },
  onLoad(query) { this.setData({ orderId: Number(query.id) }); },
  onShow() { requireSession(); },
  token(event) { this.setData({ token: event.detail.value }); },
  scan() { wx.scanCode({ onlyFromCamera: false, scanType: ['qrCode'], success: result => { this.setData({ token: result.result }); this.verify(); }, fail: error => showError(new Error((error.errMsg || '扫码不可用') + '；可在下方粘贴调度员提供的签名引用。')) }); },
  async verify() {
    if (this.data.busy) return; this.setData({ busy: true });
    try {
      const result = await api.request('/api/v2/orders/' + this.data.orderId + '/qr/verify', 'POST', { token: this.data.token.trim() });
      if (!result.verified) throw new Error('服务器未确认安装身份');
      const verified = { order_id: result.order_id, asset_id: result.asset_id, installation_id: result.installation_id, expires_at: result.expires_at };
      wx.setStorageSync(getApp().verifiedKey(this.data.orderId), verified);
      this.setData({ verified, token: '' });
    } catch (error) { wx.removeStorageSync(getApp().verifiedKey(this.data.orderId)); this.setData({ verified: null }); showError(error); } finally { this.setData({ busy: false }); }
  },
  done() { wx.navigateBack(); }
});
