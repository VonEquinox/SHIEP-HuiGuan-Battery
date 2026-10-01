const api = require('../../utils/api');
const { showError, requireSession, uuid, lines } = require('../../utils/ui');
const initialForm = () => ({ metric: '', value: '', unit: '', method: '', measured_at: new Date().toISOString(), instrument_id: '', calibration_status: 'unknown', result: 'observed', provenance: 'synthetic', observed_symptoms: '', performed_actions: '', confirmed_hypotheses: '', excluded_hypotheses: '', unresolved_items: '', assertion_targets: '', free_text: '' });
Page({
  data: { orderId: null, inspection: null, tests: [], testIndex: 0, resultIndex: 0, provenanceIndex: 0, calibrationIndex: 1,
    results: ['observed', 'inconclusive', 'failed', 'out_of_range', 'refused', 'requires_authorization'], resultLabels: ['已观察', '无区分力', '检查失败', '超出量程', '现场拒绝/无法执行', '需要追加授权'],
    provenances: ['synthetic', 'experimental_replay', 'measured_declared'], provenanceLabels: ['合成测试记录', '实验信号回放', '现场声明测量（尚未独立核验）'], calibrations: ['calibrated', 'unknown', 'expired', 'not_applicable'], calibrationLabels: ['已校准', '未知', '过期', '不适用'],
    form: initialForm(), files: [], busy: false, offline: false, legacy: false },
  onLoad(query) { this.setData({ orderId: Number(query.id) }); },
  async onShow() {
    if (!requireSession()) return;
    const app = getApp(); let inspection;
    try { inspection = await api.request('/api/v2/orders/' + this.data.orderId + '/inspection'); }
    catch (error) {
      if (error.statusCode === 409) {
        const legacyDraft = wx.getStorageSync(app.draftKey(this.data.orderId));
        this.setData({ legacy: true, files: legacyDraft && legacyDraft.legacy ? legacyDraft.files : [] }); return;
      }
      if (error.statusCode && error.statusCode !== 503) { showError(error); return; }
      inspection = wx.getStorageSync('hg_inspection:' + app.namespace() + ':' + this.data.orderId);
      this.setData({ offline: true });
    }
    if (!inspection) { showError(new Error('没有可用的授权快照，请联网获取工单后再保存本轮草稿')); return; }
    const round = (inspection.rounds || []).find(item => item.round === inspection.current_round);
    const authorized = round && round.authorized_tests || [];
    const tests = inspection.allowed_tests.filter(test => authorized.includes(test.test_id) && !test.needs_new_authorization);
    const draft = wx.getStorageSync(app.draftKey(this.data.orderId));
    const compatible = draft && draft.installation_ids.join() === inspection.assets.map(item => item.installation_id).join() && draft.round === inspection.current_round;
    const form = compatible ? draft.form : initialForm();
    const testIndex = compatible ? Math.max(0, tests.findIndex(item => item.test_id === draft.test_id)) : 0;
    if (!form.method && tests[testIndex]) form.method = tests[testIndex].sop_id || '';
    if (!form.unit && tests[testIndex]) form.unit = (tests[testIndex].units || [])[0] || '';
    this.setData({ inspection, tests, form, testIndex, files: compatible ? draft.files : [], resultIndex: this.data.results.indexOf(form.result), provenanceIndex: this.data.provenances.indexOf(form.provenance), calibrationIndex: this.data.calibrations.indexOf(form.calibration_status) });
  },
  field(event) { this.setData({ ['form.' + event.currentTarget.dataset.field]: event.detail.value }); this.saveDraft(false); },
  select(event) {
    const kind = event.currentTarget.dataset.kind; const index = Number(event.detail.value);
    if (kind === 'test') {
      const test = this.data.tests[index]; this.setData({ testIndex: index, 'form.method': test.sop_id || '', 'form.unit': (test.units || [])[0] || '' });
    } else {
      const map = { result: ['results', 'resultIndex'], provenance: ['provenances', 'provenanceIndex'], calibration_status: ['calibrations', 'calibrationIndex'] };
      const pair = map[kind]; this.setData({ [pair[1]]: index, ['form.' + kind]: this.data[pair[0]][index] });
    }
    this.saveDraft(false);
  },
  saveDraft(notify = true) {
    const value = this.data.inspection;
    if (!value) {
      if (this.data.legacy) wx.setStorageSync(getApp().draftKey(this.data.orderId), { legacy: true, files: this.data.files, saved_at: Date.now() });
      return;
    }
    wx.setStorageSync(getApp().draftKey(this.data.orderId), { form: this.data.form, files: this.data.files, test_id: this.data.tests[this.data.testIndex] && this.data.tests[this.data.testIndex].test_id,
      installation_ids: value.assets.map(item => item.installation_id), round: value.current_round, order_version: value.order.version, saved_at: Date.now() });
    if (notify) wx.showToast({ title: '草稿仅保存本机', icon: 'none' });
  },
  persistImage(tempPath, size) {
    if (size > 5 * 1024 * 1024) { showError(new Error('单个照片不能超过 5 MiB')); return; }
    wx.getImageInfo({ src: tempPath, success: info => {
      if (info.width * info.height > 16000000) { showError(new Error('照片超过 1600 万像素，请选择压缩后的图片')); return; }
      const extension = info.type === 'png' ? 'png' : info.type === 'jpeg' || info.type === 'jpg' ? 'jpg' : '';
      if (!extension) { showError(new Error('仅支持 PNG 或 JPEG 证据')); return; }
      const clientFileId = uuid(); const path = wx.env.USER_DATA_PATH + '/hg-' + clientFileId + '.' + extension;
      wx.getFileSystemManager().copyFile({ srcPath: tempPath, destPath: path, success: () => {
        this.setData({ files: this.data.files.concat([{ path, client_file_id: clientFileId, size: size || null }]) }); this.saveDraft(false);
      }, fail: error => showError(new Error(error.errMsg || '无法保存附件草稿')) });
    }, fail: error => showError(new Error(error.errMsg || '无法读取图片')) });
  },
  photo() {
    if (this.data.files.length >= 10) { showError(new Error('本地单次提交最多 10 张照片')); return; }
    if (wx.chooseMedia) wx.chooseMedia({ count: 1, mediaType: ['image'], sourceType: ['album', 'camera'], sizeType: ['compressed'], success: result => { const file = result.tempFiles[0]; this.persistImage(file.tempFilePath, file.size); }, fail: error => showError(new Error((error.errMsg || '相机/相册未授权') + '；可使用下方文件选择或文字观察。')) });
    else wx.chooseImage({ count: 1, sizeType: ['compressed'], sourceType: ['album', 'camera'], success: result => this.persistImage(result.tempFilePaths[0], result.tempFiles[0].size), fail: showError });
  },
  file() { wx.chooseMessageFile({ count: 1, type: 'image', success: result => this.persistImage(result.tempFiles[0].path, result.tempFiles[0].size), fail: error => showError(new Error((error.errMsg || '未选择文件') + '；仍可填写文字观察，必需附件不能用文字冒充。')) }); },
  removePhoto(event) { this.setData({ files: this.data.files.filter(file => file.client_file_id !== event.currentTarget.dataset.id) }); this.saveDraft(false); },
  async queue() {
    if (this.data.busy) return; this.setData({ busy: true });
    try {
      const app = getApp(); const value = this.data.inspection; const form = this.data.form;
      if (this.data.legacy) {
        if (!this.data.files.length) throw new Error('请先选择本次证据照片');
        app.outbox().enqueue('attachment', this.data.orderId, { client_submission_id: uuid() }, this.data.files);
      } else {
        const verified = wx.getStorageSync(app.verifiedKey(this.data.orderId));
        if (!verified || verified.expires_at * 1000 <= Date.now() || !value.assets.some(asset => asset.asset_id === verified.asset_id && asset.current_installation_id === verified.installation_id)) throw new Error('请联网扫码核验当前安装身份，再保存待同步测量');
        const test = this.data.tests[this.data.testIndex];
        if (!test || !value.current_round) throw new Error('当前没有可执行的已授权检查');
        const measurements = [];
        if (form.value !== '') {
          const number = Number(form.value);
          if (!Number.isFinite(number) || !form.metric.trim() || !form.unit.trim() || !form.method.trim()) throw new Error('数值必须为有限值（允许 0），并填写指标、单位与获批方法');
          if (!form.instrument_id.trim()) throw new Error('数值测量需要填写设备编号');
          if (test.units && test.units.length && !test.units.includes(form.unit.trim())) throw new Error('单位不在授权检查模板内：' + test.units.join('、'));
          measurements.push({ metric: form.metric.trim(), value: number, unit: form.unit.trim(), method: form.method.trim() });
        }
        if (!Number.isFinite(Date.parse(form.measured_at))) throw new Error('请填写有效的 ISO 测量时间（含时区）');
        if (form.result === 'observed' && !measurements.length && !form.free_text.trim() && !lines(form.observed_symptoms).length) throw new Error('需要实际观察；无法执行时选择失败/拒绝/无区分力');
        const body = { installation_id: verified.installation_id, asset_id: verified.asset_id, round: value.current_round, order_version: value.order.version, test_id: test.test_id,
          measured_at: form.measured_at, instrument_id: form.instrument_id.trim() || 'not_recorded', calibration_status: form.calibration_status, measurements, free_text: form.free_text,
          attachment_ids: [], result: form.result, provenance: form.provenance, client_submission_id: uuid() };
        for (const key of ['observed_symptoms', 'performed_actions', 'confirmed_hypotheses', 'excluded_hypotheses', 'unresolved_items', 'assertion_targets']) body[key] = lines(form[key]);
        app.outbox().enqueue('observation', this.data.orderId, body, this.data.files);
      }
      wx.removeStorageSync(app.draftKey(this.data.orderId));
      this.setData({ files: [], form: initialForm() });
      await app.sync(); wx.redirectTo({ url: '/pages/outbox/index?id=' + this.data.orderId });
    } catch (error) { showError(error); } finally { this.setData({ busy: false }); }
  }
});
