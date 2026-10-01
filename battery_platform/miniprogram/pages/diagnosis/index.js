const api = require('../../utils/api');
const { showError, requireSession, pretty } = require('../../utils/ui');
const environment = require('../../environment');
Page({
  data: { orderId: null, inspection: null, reports: [], observations: [], latestRun: null, busy: false },
  onLoad(query) { this.setData({ orderId: Number(query.id) }); },
  onShow() { if (!requireSession()) return; this.refresh(); this.timer = setInterval(() => this.refresh(false), environment.pollIntervalMs); },
  onHide() { clearInterval(this.timer); }, onUnload() { clearInterval(this.timer); },
  onPullDownRefresh() { this.refresh(); },
  async refresh(alert = true) {
    if (this.data.busy || !requireSession()) return; this.setData({ busy: true });
    try {
      const inspection = await api.request('/api/v2/orders/' + this.data.orderId + '/inspection');
      const reports = inspection.reports.slice().reverse().map(value => {
        const report = value.report || {};
        return Object.assign({}, value, { report, summaryText: typeof report.summary === 'string' ? report.summary : pretty(report.summary || report.status),
          factItems: (report.facts || []).map(item => ({ text: item.statement || item.text || pretty(item), references: (item.evidence_ids || item.evidence_refs || []).join('、') })),
          hypothesisItems: (report.hypotheses || []).map(item => ({ text: item.statement || item.cause || item.hypothesis || pretty(item), status: item.status || '未确认', refs: pretty(item.supporting_evidence_ids || item.evidence_ids || []) })),
          unknownItems: (report.unknowns || report.unresolved_items || []).map(item => typeof item === 'string' ? item : pretty(item)),
          nextTests: (report.recommended_tests || []).map(item => ({ text: typeof item === 'string' ? item : item.test_id || item.name, reason: typeof item === 'object' ? item.reason || item.purpose : '' })) });
      });
      const observations = inspection.observations.slice().reverse().map(item => Object.assign({}, item, { measurementsText: pretty(item.measurements), factsText: pretty(item.candidate_facts || []) }));
      const local = getApp().outbox().list().filter(item => item.order_id === this.data.orderId && item.status === 'synced' && item.result && item.result.run_id).reverse();
      let latestRun = null;
      if (local.length) { const result = await api.request('/api/v2/agent/runs/' + local[0].result.run_id); latestRun = { status: result.status || result.run && result.run.status || result.job && result.job.status, detail: pretty(result.job || result.run || result) }; }
      this.setData({ inspection, reports, observations, latestRun });
    } catch (error) { if (alert) showError(error); } finally { this.setData({ busy: false }); wx.stopPullDownRefresh(); }
  },
  inspect() { wx.navigateTo({ url: '/pages/inspection/index?id=' + this.data.orderId }); },
  order() { wx.redirectTo({ url: '/pages/order/index?id=' + this.data.orderId }); }
});
