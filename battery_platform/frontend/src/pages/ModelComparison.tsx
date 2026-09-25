import { useState } from "react";
import { api, useData, type Row, labels } from "../api";
import {
  Panel,
  Modal,
  Notice,
  Field,
  Hash,
  Empty,
  useAction,
} from "../components";

export function ModelComparison() {
  const jobs = useData<Row[]>("/jobs", 5000);
  const [open, setOpen] = useState(false),
    [selected, setSelected] = useState<number[]>([]),
    [report, setReport] = useState<any>(null);
  const action = useAction();
  const eligible =
    jobs.data?.filter(
      (j) => j.kind === "evaluation" && j.status === "succeeded",
    ) || [];
  return (
    <Panel
      title="同样本模型对比"
      subtitle="仅比较相同输入快照集合的已完成评估，防止拿不同电芯的误差横向排名。"
      actions={<button onClick={() => setOpen(true)}>比较已保存评估</button>}
    >
      <p>
        分别为需要比较的模型提交“评估已有模型”任务，选择相同数据集、电芯和样本范围。系统会重新核对样本身份，并从保存的预测逐行重算指标。
      </p>
      {open && (
        <Modal title="比较已完成评估任务" wide onClose={() => setOpen(false)}>
          {action.feedback}
          <Notice>
            最多选择5项。训练样本重叠与标签来源仍会显示；更小的误差不自动证明模型泛化更好。
          </Notice>
          {eligible.length < 2 ? (
            <Empty>
              至少需要两个已完成的评估任务。推理和训练任务不能直接混入比较。
            </Empty>
          ) : (
            <>
              <div className="checks">
                {eligible.map((j) => (
                  <label key={j.id}>
                    <input
                      type="checkbox"
                      checked={selected.includes(j.id)}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, j.id]
                            : selected.filter((id) => id !== j.id),
                        )
                      }
                    />
                    JOB-{j.id} / 模型 #{j.payload.model_id} /{" "}
                    {j.payload.cell_id || "指定样本集合"}
                  </label>
                ))}
              </div>
              <button
                className="primary"
                disabled={
                  selected.length < 2 || selected.length > 5 || action.busy
                }
                onClick={() =>
                  void action.run(async () => {
                    setReport(
                      await api("/comparisons?job_ids=" + selected.join(",")),
                    );
                  }, "已从相同样本的保存预测重算")
                }
              >
                核对样本并比较
              </button>
            </>
          )}
          {report && (
            <>
              <Notice>{report.caveat}</Notice>
              <p>
                共同样本：{report.sample_count} ·{" "}
                <Hash value={report.comparison_source_hash} />
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>模型 / 任务</th>
                      <th>MAE / pp</th>
                      <th>RMSE / pp</th>
                      <th>标签样本 / 电芯</th>
                      <th>评估范围</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.comparisons.map((r: any) => (
                      <tr key={r.job_id}>
                        <td>
                          <strong>{r.model_name}</strong>
                          <small>JOB-{r.job_id}</small>
                        </td>
                        <td>{r.cell_macro_mae_pp.toFixed(4)}</td>
                        <td>{r.cell_macro_rmse_pp.toFixed(4)}</td>
                        <td>
                          {r.rows} / {r.cells}
                        </td>
                        <td>{labels[r.scope] || r.scope}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Modal>
      )}
    </Panel>
  );
}
