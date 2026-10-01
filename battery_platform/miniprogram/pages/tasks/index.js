const api = require('../../utils/api');
const { showError, requireSession } = require('../../utils/ui');
const environment = require('../../environment');
Page({
  data: { tasks: [], status: '', busy: false, username: '', pending: 0, limitNotice: '' },
  onShow() {
    if (!requireSession()) return;
    this.setData({ username: getApp().globalData.session.user.display_name }); this.refresh();
    this.timer = setInterval(() => this.refresh(false), environment.pollIntervalMs);
  },
  onHide() { clearInterval(this.timer); }, onUnload() { clearInterval(this.timer); },
  async refresh(alert = true) {
    if (this.data.busy || !requireSession()) return;
    this.setData({ busy: true });
    try {
      const result = await api.request('/api/orders' + (this.data.status ? '?status=' + encodeURIComponent(this.data.status) : ''));
      const tasks = result.slice().sort((a, b) => String(a.due_at || '9999').localeCompare(String(b.due_at || '9999')));
      this.setData({ tasks, pending: getApp().outbox().pending().length, limitNotice: result.length >= 300 ? '当前 V1 列表达到 300 项上限，请按状态筛选并在 Web 查看完整任务。' : '' });
    } catch (error) { if (alert) showError(error); } finally { this.setData({ busy: false }); wx.stopPullDownRefresh(); }
  },
  onPullDownRefresh() { this.refresh(); },
  filter(event) { this.setData({ status: event.currentTarget.dataset.status || '' }); this.refresh(); },
  open(event) { wx.navigateTo({ url: '/pages/order/index?id=' + event.currentTarget.dataset.id }); },
  outbox() { wx.navigateTo({ url: '/pages/outbox/index' }); },
  async logout() { try { await api.request('/api/v2/demo-mobile/logout', 'POST'); } catch (_) {} getApp().clearSession(); wx.reLaunch({ url: '/pages/login/index' }); }
});
