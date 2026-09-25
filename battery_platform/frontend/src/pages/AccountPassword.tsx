import { useState } from "react";
import { api, type User, type Row } from "../api";
import { Modal, Field, Notice, useAction } from "../components";

export function AccountPassword({
  user,
  target,
}: {
  user: User;
  target?: Row;
}) {
  const [open, setOpen] = useState(false);
  const action = useAction();
  const identifier = target?.id || user.id;
  const own = identifier === user.id;
  return (
    <>
      <button onClick={() => setOpen(true)}>
        {own ? "修改我的密码" : "重置密码"}
      </button>
      {open && (
        <Modal
          title={
            own ? "修改我的密码" : "重置 " + target?.display_name + " 的密码"
          }
          onClose={() => setOpen(false)}
        >
          <Notice>
            密码不会写入审计日志或浏览器存储。提交后撤销目标账户的所有已有会话。
          </Notice>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void action.run(async () => {
                if (f.get("new_password") !== f.get("confirm"))
                  throw new Error("两次新密码不一致");
                await api(`/users/${identifier}/password`, "POST", {
                  new_password: f.get("new_password"),
                  current_password: own ? f.get("current_password") : null,
                });
                setOpen(false);
                if (own) window.dispatchEvent(new Event("session-expired"));
              }, "密码已重置，原有会话已失效");
            }}
          >
            {own && (
              <Field label="当前密码">
                <input
                  type="password"
                  name="current_password"
                  autoComplete="current-password"
                  required
                />
              </Field>
            )}
            <Field label="新密码（至少12字符）">
              <input
                type="password"
                name="new_password"
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
                required
              />
            </Field>
            <Field label="确认新密码">
              <input
                type="password"
                name="confirm"
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
                required
              />
            </Field>
            <button className="primary" disabled={action.busy}>
              确认修改密码
            </button>
          </form>
          {action.error && <Notice tone="error">{action.error}</Notice>}
        </Modal>
      )}
    </>
  );
}
