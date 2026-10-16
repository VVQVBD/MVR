"use client";

import { FormEvent, useEffect, useState } from "react";
import { Client, Dispute, FacilityObject, Finding, Me, Schedule, formatMoney, formatShift, formatSource, get, login } from "@/lib/api";

type Tab = "disputes" | "checks" | "objects";

const ROLE_LABEL: Record<Me["role"], string> = {
  executive: "руководитель",
  manager: "менеджер",
  client: "клиент",
  subcontractor: "субподрядчик",
};

function Sev({ value }: { value: string }) {
  return <span className={`sev sev-${value}`}>{value}</span>;
}

function Login({ onToken }: { onToken: (t: string) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      onToken(await login(email, password));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <form className="login" onSubmit={submit}>
      <input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input placeholder="Пароль" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <button type="submit">Войти</button>
      {error && <div className="error">{error}</div>}
    </form>
  );
}

function Disputes({ token }: { token: string }) {
  const [items, setItems] = useState<Dispute[]>([]);
  const [severity, setSeverity] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const q = severity ? `?severity=${severity}` : "";
    get<Dispute[]>(`/disputed-conditions${q}`, token).then(setItems).catch((e) => setError(e.message));
  }, [token, severity]);

  return (
    <>
      <nav>
        <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="">Все уровни</option>
          <option value="critical">critical</option>
          <option value="high">high</option>
          <option value="medium">medium</option>
          <option value="low">low</option>
        </select>
      </nav>
      {error && <div className="error">{error}</div>}
      <div className="card">
        <table>
          <thead>
            <tr><th>Код</th><th>Клиент</th><th>Тема</th><th>Уровень</th><th>Проблема</th><th>Что спросить</th><th>Источники</th></tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id}>
                <td>{d.id}</td>
                <td>{d.client_name ?? "—"}</td>
                <td>{d.topic}</td>
                <td><Sev value={d.severity} /></td>
                <td>{d.issue}</td>
                <td>{d.ask ?? "—"}</td>
                <td>
                  <ul className="sources">
                    {d.sources.map((s) => <li key={s.id} title={s.note ?? undefined}>{formatSource(s)}</li>)}
                  </ul>
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={7} className="muted">Нет записей</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Checks({ token }: { token: string }) {
  const [items, setItems] = useState<Finding[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    get<Finding[]>("/checks", token).then(setItems).catch((e) => setError(e.message));
  }, [token]);

  return (
    <>
      {error && <div className="error">{error}</div>}
      <div className="card">
        <table>
          <thead><tr><th>Уровень</th><th>Тип</th><th>Клиент</th><th>Документ</th><th>Описание</th></tr></thead>
          <tbody>
            {items.map((f, i) => (
              <tr key={i}>
                <td><Sev value={f.severity} /></td>
                <td>{f.kind}</td>
                <td>{f.client_code}</td>
                <td>{f.contract_number ?? "—"}</td>
                <td>{f.message}</td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={5} className="muted">Проверки не нашли проблем</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Objects({ token, role }: { token: string; role: Me["role"] }) {
  const isSubcontractor = role === "subcontractor";
  const [clients, setClients] = useState<Client[]>([]);
  const [clientId, setClientId] = useState("");
  const [objects, setObjects] = useState<FacilityObject[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (isSubcontractor) return;
    get<Client[]>("/clients", token).then(setClients).catch((e) => setError(e.message));
  }, [token, isSubcontractor]);

  useEffect(() => {
    const q = clientId ? `?client_id=${clientId}` : "";
    get<FacilityObject[]>(`/objects${q}`, token).then(setObjects).catch((e) => setError(e.message));
  }, [token, clientId]);

  useEffect(() => {
    get<Schedule[]>("/schedules", token).then(setSchedules).catch((e) => setError(e.message));
  }, [token]);

  const clientName = (id?: number) => clients.find((c) => c.id === id)?.name ?? "—";
  const shiftsOf = (id: number) => schedules.filter((s) => s.facility_object_id === id);
  const columns = isSubcontractor ? 5 : 8;

  return (
    <>
      {!isSubcontractor && clients.length > 1 && (
        <nav>
          <select value={clientId} onChange={(e) => setClientId(e.target.value)}>
            <option value="">Все клиенты</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </nav>
      )}
      {error && <div className="error">{error}</div>}
      <div className="card">
        <table>
          <thead>
            <tr>
              {!isSubcontractor && <th>Клиент</th>}
              <th>Объект</th>
              <th>Город</th>
              <th>Площадь, м²</th>
              <th>График</th>
              {!isSubcontractor && <th>Тариф в месяц</th>}
              {!isSubcontractor && <th>НДС</th>}
              <th>Субподрядчик</th>
            </tr>
          </thead>
          <tbody>
            {objects.map((o) => (
              <tr key={o.id}>
                {!isSubcontractor && <td>{clientName(o.client_company_id)}</td>}
                <td>{o.name}<div className="muted">{o.services}</div></td>
                <td>{o.city}</td>
                <td>{o.area_m2 != null ? Number(o.area_m2).toLocaleString("ru-RU") : "—"}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {shiftsOf(o.id).length ? shiftsOf(o.id).map((s) => <div key={s.id}>{formatShift(s)}</div>) : <span className="muted">нет в графике</span>}
                </td>
                {!isSubcontractor && (
                  <td style={{ whiteSpace: "nowrap" }}>{o.monthly_tariff != null ? formatMoney(o.monthly_tariff) : "по заявке"}</td>
                )}
                {!isSubcontractor && <td className="muted">{o.vat_note ?? "—"}</td>}
                <td>{o.subcontractor ? `${o.subcontractor.code ?? ""} ${o.subcontractor.name}`.trim() : <span className="muted">{isSubcontractor ? "вы" : "не назначен"}</span>}</td>
              </tr>
            ))}
            {objects.length === 0 && <tr><td colSpan={columns} className="muted">Нет объектов</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default function Page() {
  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [tab, setTab] = useState<Tab>("disputes");

  useEffect(() => {
    try {
      setToken(sessionStorage.getItem("token"));
    } catch {}
  }, []);

  useEffect(() => {
    if (!token) return setMe(null);
    get<Me>("/auth/me", token)
      .then((u) => {
        setMe(u);
        if (u.role === "subcontractor") setTab("objects");
      })
      .catch(() => saveToken(null));
  }, [token]);

  const isStaff = me?.role === "executive" || me?.role === "manager";
  const canSeeDisputes = isStaff || me?.role === "client";

  function saveToken(t: string | null) {
    setToken(t);
    try {
      t ? sessionStorage.setItem("token", t) : sessionStorage.removeItem("token");
    } catch {}
  }

  return (
    <main>
      <h1>IC Group — договоры и спорные условия</h1>
      {!token ? (
        <Login onToken={saveToken} />
      ) : (
        <>
          <nav>
            {canSeeDisputes && (
              <button className={tab === "disputes" ? "active" : ""} onClick={() => setTab("disputes")}>Спорные условия</button>
            )}
            {isStaff && (
              <button className={tab === "checks" ? "active" : ""} onClick={() => setTab("checks")}>Автопроверки</button>
            )}
            <button className={tab === "objects" ? "active" : ""} onClick={() => setTab("objects")}>Объекты</button>
            <button onClick={() => saveToken(null)}>Выйти</button>
            {me && <span className="muted" style={{ alignSelf: "center" }}>{me.email} · {ROLE_LABEL[me.role]}</span>}
          </nav>
          {me && tab === "disputes" && canSeeDisputes && <Disputes token={token} />}
          {me && tab === "checks" && isStaff && <Checks token={token} />}
          {me && tab === "objects" && <Objects token={token} role={me.role} />}
        </>
      )}
    </main>
  );
}
