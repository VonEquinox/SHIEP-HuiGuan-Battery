function showError(error) { wx.showModal({ title: '需要处理', content: [error.message || String(error), ...(error.missing_fields || [])].join('\n'), showCancel: false }); }
function lines(value) { return String(value || '').split(/[\n,，]/).map(item => item.trim()).filter(Boolean); }
function uuid() {
  // Submission IDs carry no authorization and need uniqueness only; never use
  // this function for sessions, QR signatures, secrets or access tokens.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, character => {
    const value = Math.floor(Math.random() * 16); return (character === 'x' ? value : value & 3 | 8).toString(16);
  });
}
function requireSession() {
  const app = getApp();
  if (!app.globalData.session || app.globalData.session.expiresAt <= Date.now()) {
    app.clearSession(); wx.reLaunch({ url: '/pages/login/index' }); return false;
  }
  return true;
}
function pretty(value) { return JSON.stringify(value, null, 2); }
module.exports = { showError, lines, uuid, requireSession, pretty };
