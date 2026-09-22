import { ArrowRight, ShieldCheck } from "lucide-react";
import Link from "next/link";

export default function LoginPage() {
  return (
    <main className="login-shell">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="brand-mark" aria-hidden="true">A</div>
        <div className="login-heading">
          <p className="eyebrow">AIPY 内容工作台</p>
          <h1 id="login-title">登录你的团队空间</h1>
          <p>统一管理素材、内容任务与人工审核。</p>
        </div>

        <form className="form-stack">
          <label>
            工作邮箱
            <input name="email" type="email" defaultValue="editor@example.com" autoComplete="email" />
          </label>
          <label>
            密码
            <input name="password" type="password" defaultValue="demo-password" autoComplete="current-password" />
          </label>
          <Link className="button button-primary button-wide" href="/app">
            进入工作台
            <ArrowRight size={17} aria-hidden="true" />
          </Link>
        </form>

        <p className="login-note">
          <ShieldCheck size={16} aria-hidden="true" />
          演示环境使用静态会话，不会提交登录信息
        </p>
      </section>
    </main>
  );
}
