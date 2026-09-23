"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { apiClient } from "@/lib/api-client";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("editor@example.com");
  const [password, setPassword] = useState("demo-password");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await apiClient.login({ email, password });
      router.replace("/app");
    } catch {
      setError("登录失败，请检查邮箱与密码");
      setLoading(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="brand-mark" aria-hidden="true">A</div>
        <div className="login-heading">
          <p className="eyebrow">AIPY 内容工作台</p>
          <h1 id="login-title">登录你的团队空间</h1>
          <p>统一管理素材、内容任务与人工审核。</p>
        </div>

        <form className="form-stack" onSubmit={onSubmit}>
          <label>
            工作邮箱
            <input
              name="email"
              type="email"
              value={email}
              autoComplete="email"
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            密码
            <input
              name="password"
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && <p className="login-error" role="alert">{error}</p>}
          <button className="button button-primary button-wide" type="submit" disabled={loading}>
            {loading ? "登录中…" : "进入工作台"}
            {!loading && <ArrowRight size={17} aria-hidden="true" />}
          </button>
        </form>

        <p className="login-note">
          <ShieldCheck size={16} aria-hidden="true" />
          演示账号 editor@example.com / demo-password
        </p>
      </section>
    </main>
  );
}
