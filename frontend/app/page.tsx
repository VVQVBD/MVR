"use client";

import { useEffect, useState } from "react";

import { DisputesWidget } from "@/components/disputes-widget";
import { ObjectsTable } from "@/components/objects-table";
import { RoleSwitcher } from "@/components/role-switcher";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useSession } from "@/store/session";

type Tab = "risks" | "objects";

export default function Page() {
  const token = useSession((s) => s.token);
  const role = useSession((s) => s.role);
  const [tab, setTab] = useState<Tab>("risks");
  // sessionStorage читается только в браузере — до этого не рендерим зависящий от сессии контент
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);

  return (
    <main className="container space-y-6 py-6">
      <header className="space-y-3">
        <div>
          <h1 className="text-xl font-semibold">IC Group — договоры, объекты и риски</h1>
          <p className="text-sm text-muted-foreground">
            Выберите роль: данные отбирает сервер, интерфейс только показывает то, что роли разрешено.
          </p>
        </div>
        <RoleSwitcher />
      </header>

      {hydrated && !token && (
        <Card>
          <CardContent className="p-4 text-sm text-muted-foreground">Выберите роль, чтобы увидеть данные.</CardContent>
        </Card>
      )}

      {hydrated && token && (
        <>
          <nav className="flex gap-1.5 border-b pb-3" aria-label="Разделы">
            <Button variant={tab === "risks" ? "secondary" : "ghost"} size="sm" onClick={() => setTab("risks")} aria-current={tab === "risks" ? "page" : undefined}>
              Расхождения и риски
            </Button>
            <Button variant={tab === "objects" ? "secondary" : "ghost"} size="sm" onClick={() => setTab("objects")} aria-current={tab === "objects" ? "page" : undefined}>
              Объекты и субподрядчики
            </Button>
          </nav>
          {/* key={role}: при смене роли фильтры прошлой роли сбрасываются */}
          {tab === "risks" ? <DisputesWidget key={role} /> : <ObjectsTable key={role} />}
        </>
      )}
    </main>
  );
}
