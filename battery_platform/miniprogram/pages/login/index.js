const api = require('../../utils/api');
const { showError } = require('../../utils/ui');
const environment = require('../../environment');
Page({
  data: { apiBaseUrl: '', username: '', password: '', busy: false, connection: '尚未检测', mode: '平台测试账号认证' },
  onLoad() { this.setData({ apiBaseUrl: getApp().globalData.apiBaseUrl }); },
  field(event) { this.setData({ [event.currentTarget.dataset.field]: event.detail.value }); },
  saveEnvironment() {
    const base = api.validateBaseUrl(this.data.apiBaseUrl, environment.allowSimulatorHttp);
    const app = getApp();
    if (app.globalData.apiBaseUrl !== base) app.clearSession();
    app.globalData.apiBaseUrl = base; wx.setStorageSync('hg_api_base', base);
  },
  async checkConnection() {
    try { this.saveEnvironment(); const result = await api.request('/api/status'); this.setData({ connection: '后端可达 · ' + (result.version || '连接已建立') }); }
    catch (error) { this.setData({ connection: '连接未建立' }); showError(error); }
  },
  async login() {
    if (this.data.busy) return;
    this.setData({ busy: true });
    try {
      this.saveEnvironment();
      const result = await api.request('/api/v2/demo-mobile/login', 'POST', { username: this.data.username.trim(), password: this.data.password });
      if (!result.user || result.user.role !== 'technician') throw new Error('服务端未返回授权技术员身份');
      getApp().setSession(result); this.setData({ password: '' });
      wx.reLaunch({ url: '/pages/tasks/index' });
    } catch (error) { showError(error); } finally { this.setData({ busy: false }); }
  }
});
