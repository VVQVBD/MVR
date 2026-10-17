"use client";

import { Loader2, LogIn, X } from "lucide-react";
import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import { useOperatorSession } from "@/store/operator-session";

export function OperatorLoginModal({ onClose }: { onClose: () => void }) {
  const setSession = useOperatorSession((s) => s.setSession);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const { access_token } = await api.login(email, password);
      setSession(access_token, email);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось войти");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/70 p-5" role="dialog" aria-modal>
      <div className="w-full max-w-sm rounded-2xl border border-slate-800 bg-[#0d121c] p-6 shadow-2xl">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200">Вход для оператора</h2>
          <button onClick={onClose} aria-label="Закрыть" className="text-slate-500 hover:text-white">
            <X size={16} />
          </button>
        </div>
        <form onSubmit={submit} className="mt-5 space-y-3">
          <label className="block text-xs text-slate-400">
            Email
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input mt-1"
              placeholder="op900@icgroup.local"
            />
          </label>
          <label className="block text-xs text-slate-400">
            Пароль
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input mt-1"
            />
          </label>
          {error && <p className="text-xs text-rose-300">{error}</p>}
          <button
            type="submit"
            disabled={pending}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-400 py-2.5 text-xs font-bold text-slate-950 disabled:opacity-60"
          >
            {pending ? <Loader2 size={14} className="animate-spin" /> : <LogIn size={14} />}
            Войти
          </button>
          <p className="text-[10px] text-slate-500">
            Логин создаётся в бекенде: <code>python -m scripts.create_user email пароль operator --operator-code OP-XXX</code>
          </p>
        </form>
      </div>
    </div>
  );
}
