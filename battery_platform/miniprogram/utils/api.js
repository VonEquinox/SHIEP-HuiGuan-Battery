const defaults = require('../environment');
function validateBaseUrl(value, simulatorHttp) {
  const base = String(value || '').trim().replace(/\/+$/, '');
  if (!/^https:\/\/[a-z0-9.-]+(?::\d+)?$/i.test(base) && !(simulatorHttp && /^http:\/\/(localhost|127\.0\.0\.1)(?::\d+)?$/i.test(base))) {
    throw new Error('请输入可由手机访问的 HTTPS 后端地址，不包含路径；模拟器 HTTP 需单独显式配置');
  }
  if (!simulatorHttp && /^https:\/\/(localhost|127\.0\.0\.1|\[::1\])(?::|$)/i.test(base)) throw new Error('手机上的 localhost 指向手机自身，请配置可达的 HTTPS 地址');
  return base;
}
function normalizeError(response) {
  const data = response.data || {}; const detail = data.detail;
  const error = new Error(data.message || (typeof detail === 'string' ? detail : detail && detail.message) || '请求失败');
  error.statusCode = response.statusCode; error.request_id = data.request_id;
  error.missing_fields = data.missing_fields && data.missing_fields.length ? data.missing_fields : detail && detail.missing_fields || [];
  return error;
}
function request(path, method, data, extra) {
  const app = getApp(); const session = app.globalData.session;
  const base = validateBaseUrl(app.globalData.apiBaseUrl, defaults.allowSimulatorHttp);
  const headers = Object.assign({ 'Content-Type': 'application/json' }, extra || {});
  if (session) headers.Authorization = 'Bearer ' + session.token;
  return new Promise((resolve, reject) => wx.request({ url: base + path, method: method || 'GET', data,
    timeout: 15000, header: headers,
    success(response) {
      if (response.statusCode >= 200 && response.statusCode < 300) resolve(response.data);
      else { if (response.statusCode === 401) app.clearSession(); reject(normalizeError(response)); }
    }, fail(problem) { reject(Object.assign(new Error(problem.errMsg || '网络不可用，草稿保留在本机'), { statusCode: 0 })); }
  }));
}
function upload(orderId, file) {
  const app = getApp(); const session = app.globalData.session;
  if (!session) return Promise.reject(Object.assign(new Error('请重新登录'), { statusCode: 401 }));
  return new Promise((resolve, reject) => wx.uploadFile({ url: app.globalData.apiBaseUrl + '/api/orders/' + orderId + '/attachments', filePath: file.path, name: 'file',
    header: { Authorization: 'Bearer ' + session.token, 'Idempotency-Key': file.client_file_id }, timeout: 20000,
    success(response) {
      let data; try { data = JSON.parse(response.data); } catch (_) { data = { detail: '上传响应格式错误' }; }
      if (response.statusCode >= 200 && response.statusCode < 300) resolve(data);
      else reject(normalizeError({ statusCode: response.statusCode, data }));
    }, fail(problem) { reject(Object.assign(new Error((problem.errMsg || '上传连接中断') + '；请核对服务器附件再继续，避免重复上传'), { statusCode: 0, uploadUncertain: true })); }
  }));
}
const transport = { upload, send(kind, orderId, body) {
  if (kind === 'attachment') return Promise.resolve({ attachment_ids: body.attachment_ids || [], status: 'uploaded' });
  const path = kind === 'round' ? '/api/v2/orders/' + orderId + '/rounds/' + body.round + '/submit' : '/api/v2/orders/' + orderId + '/observations';
  const payload = Object.assign({}, body);
  if (kind === 'round') delete payload.round;
  return request(path, 'POST', payload, { 'Idempotency-Key': body.client_submission_id });
} };
module.exports = { request, upload, transport, validateBaseUrl, normalizeError };
