import { useEffect, useState } from "react";
import { NavLink, Routes, Route, useLocation } from "react-router-dom";
import {
  Activity,
  LayoutDashboard,
  Boxes,
  Database,
  Network,
  HeartPulse,
  ClipboardList,
  Settings,
  Bell,
  LogOut,
  Menu,
  ChevronRight,
  ShieldCheck,
} from "lucide-react";
import { api, setCsrf, type User, labels, useData } from "./api";
import { Notice, Field, Spinner, Badge } from "./components";
import { Dashboard, Assets, DataCenter } from "./pages/Foundation";
import { ModelCenter, HealthCenter } from "./pages/Intelligence";
import { Operations, SystemPage } from "./pages/Operations";

const nav = [
  ["/", "总览", LayoutDashboard],
  ["/assets", "资产中心", Boxes],
  ["/data", "数据中心", Database],
  ["/models", "模型中心", Network],
  ["/health", "健康中心", HeartPulse],
  ["/operations", "告警与工单", ClipboardList],
  ["/system", "系统管理", Settings],
] as const;
function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const status = useData("/status");
  return (
    <main className="login-page">
      <div className="login-story">
        <div className="brand">
          <span className="brand-icon">
            <Activity />
          </span>
          <strong>
            慧管电池<span>HUI GUAN · BATTERY</span>
          </strong>
        </div>
        <div>
          <span className="eyebrow">HEALTH INTELLIGENCE / OPERATIONS</span>
          <h1>
            每一次判断，
            <br />
            都有据可循。
          </h1>
          <p>
            从真实实验数据到健康评估，
            <br />
            再到可追溯的运维闭环。
          </p>
          <div className="login-grid">
            <span>01 / 数据</span>
            <span>02 / 模型</span>
            <span>03 / 运维</span>
          </div>
        </div>
        <small>实验数据驱动 · 模拟资产演示 · 无生产控制连接</small>
      </div>
      <div className="login-form">
        <div className="login-card">
          <ShieldCheck size={28} />
          <h2>进入工作台</h2>
          <p>使用管理员为你创建的本地账户。</p>
          {status.data?.initialized === false ? (
            <Notice>
              首次使用请在项目目录运行 <code>./manage.sh bootstrap</code>{" "}
              创建账户；系统没有默认口令。
            </Notice>
          ) : null}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              api<User>("/auth/login", "POST", { username, password })
                .then((u) => {
                  setCsrf(u.csrf);
                  onLogin(u);
                })
                .catch((e) => setError(e.message))
                .finally(() => setBusy(false));
            }}
          >
            <Field label="用户名">
              <input
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </Field>
            <Field label="密码">
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            {error && <Notice tone="error">{error}</Notice>}
            <button className="primary full" disabled={busy}>
              {busy ? "验证中…" : "安全登录"}
              <ChevronRight size={17} />
            </button>
          </form>
          <small>会话采用服务端身份校验。维修人员仅能处理获派工单。</small>
        </div>
      </div>
    </main>
  );
}
export function App() {
  const [user, setUser] = useState<User | null>(null),
    [ready, setReady] = useState(false),
    [mobile, setMobile] = useState(false);
  const location = useLocation();
  useEffect(() => {
    api<User>("/auth/me")
      .then((u) => {
        setCsrf(u.csrf);
        setUser(u);
      })
      .catch(() => {})
      .finally(() => setReady(true));
    const expired = () => {
      setUser(null);
      setCsrf("");
    };
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, []);
  useEffect(() => setMobile(false), [location.pathname]);
  if (!ready) return <Spinner />;
  if (!user) return <Login onLogin={setUser} />;
  const title = nav.find((n) => n[0] === location.pathname)?.[1] || "工作台";
  return (
    <div className="shell">
      <aside className={"sidebar " + (mobile ? "open" : "")}>
        <NavLink to="/" className="brand">
          <span className="brand-icon">
            <Activity size={23} />
          </span>
          <strong>
            慧管电池<span>BATTERY OPERATIONS</span>
          </strong>
        </NavLink>
        <div className="workspace-label">实验与运维工作区</div>
        <nav>
          {nav.map(([path, label, Icon]) => (
            <NavLink key={path} to={path} end={path === "/"}>
              <Icon size={19} />
              {label}
              <ChevronRight className="nav-chevron" size={14} />
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="connection-dot" />
          独立应用 / 本地运行
          <p>
            真实实验 · 模拟业务
            <br />
            未接入生产 BMS
          </p>
          <Badge value={user.role} />
        </div>
      </aside>
      {mobile && (
        <div className="sidebar-backdrop" onClick={() => setMobile(false)} />
      )}
      <div className="main-wrap">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-toggle"
              onClick={() => setMobile(!mobile)}
              aria-label="展开导航"
            >
              <Menu />
            </button>
            <span>工作台</span>
            <ChevronRight size={13} />
            <strong>{title}</strong>
          </div>
          <div className="top-actions">
            <span className="mode">
              <span />
              实验 / 仿真模式
            </span>
            <NavLink
              to="/system?tab=notifications"
              className="icon-button"
              aria-label="站内通知"
            >
              <Bell size={19} />
            </NavLink>
            <div className="user-label">
              <span className="avatar">{user.display_name.slice(0, 1)}</span>
              <span>
                {user.display_name}
                <small>{labels[user.role]}</small>
              </span>
            </div>
            <button
              className="icon-button"
              aria-label="退出登录"
              onClick={() =>
                void api("/auth/logout", "POST").finally(() => {
                  setUser(null);
                  setCsrf("");
                })
              }
            >
              <LogOut size={18} />
            </button>
          </div>
        </header>
        <main className="content">
          <Routes>
            <Route path="/" element={<Dashboard user={user} />} />
            <Route path="/assets" element={<Assets user={user} />} />
            <Route path="/data" element={<DataCenter user={user} />} />
            <Route path="/models" element={<ModelCenter user={user} />} />
            <Route path="/health" element={<HealthCenter user={user} />} />
            <Route path="/operations" element={<Operations user={user} />} />
            <Route path="/system" element={<SystemPage user={user} />} />
            <Route
              path="*"
              element={<Notice>页面不存在，请从左侧导航选择功能。</Notice>}
            />
          </Routes>
        </main>
        <footer className="footer">
          慧管电池 / 模型结果可追溯，业务状态可复核<span>v1.0 · 独立应用</span>
        </footer>
      </div>
    </div>
  );
}
