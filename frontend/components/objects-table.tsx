"use client";

import { AlertTriangle, CalendarX, CheckCircle2 } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useClients, useObjects, useSchedules } from "@/hooks/queries";
import { formatArea, formatKzt } from "@/lib/api";
import { hasPricing, type FacilityObject, type FacilityObjectFull, type Schedule, type VatBasis } from "@/lib/types";
import { cn } from "@/lib/utils";

type Status = "dropped" | "unassigned" | "ok";

interface Row {
  object: FacilityObject;
  status: Status;
  unassigned: boolean;
  inSchedule: boolean;
}

const VAT_LABEL: Record<VatBasis, string> = {
  included: "с НДС",
  excluded: "без НДС, сверху",
  unknown: "не указан",
};

function vatText(o: FacilityObjectFull): string {
  const rate = o.vat_rate ? ` ${Number(o.vat_rate)}%` : "";
  return `${VAT_LABEL[o.vat_basis]}${o.vat_basis === "included" ? rate : ""}`;
}

/**
 * «Выпал из графика» — объекта нет в графике последнего месяца, хотя другие объекты того же договора
 * в этом городе в графике есть (как бутик Капри в ТРЦ «Арал Молл», Q-03).
 * «Не назначен» — у объекта нет субподрядчика.
 */
function classify(objects: FacilityObject[], schedules: Schedule[]): { rows: Row[]; period: string | null } {
  const period = schedules.reduce<string | null>((p, s) => (p === null || s.period_month > p ? s.period_month : p), null);
  const scheduled = new Set(schedules.filter((s) => s.period_month === period).map((s) => s.facility_object_id));
  const contractCity = new Set(
    objects.filter((o) => hasPricing(o) && scheduled.has(o.id)).map((o) => `${(o as FacilityObjectFull).contract_id}|${o.city}`),
  );
  const rows = objects.map((o): Row => {
    const inSchedule = scheduled.has(o.id);
    const unassigned = o.subcontractor_id === null;
    const dropped = !inSchedule && hasPricing(o) && contractCity.has(`${o.contract_id}|${o.city}`);
    return { object: o, inSchedule, unassigned, status: dropped ? "dropped" : unassigned ? "unassigned" : "ok" };
  });
  return { rows, period };
}

function StatusBadges({ row }: { row: Row }) {
  return (
    <div className="flex flex-col items-start gap-1">
      {row.status === "dropped" && (
        <Badge variant="destructive" title="Другие объекты договора в этом городе в графике есть">
          <CalendarX className="mr-1 h-3 w-3" />
          Нет в графике смен
        </Badge>
      )}
      {row.unassigned && (
        <Badge variant="warning">
          <AlertTriangle className="mr-1 h-3 w-3" />
          Субподрядчик не назначен
        </Badge>
      )}
      {row.status === "ok" && row.inSchedule && (
        <span className="inline-flex items-center text-xs text-muted-foreground">
          <CheckCircle2 className="mr-1 h-3.5 w-3.5" />в графике
        </span>
      )}
    </div>
  );
}

export function ObjectsTable() {
  const objectsQ = useObjects();
  const schedulesQ = useSchedules();
  const clientsQ = useClients();
  const [clientId, setClientId] = useState<string>("");
  const [city, setCity] = useState<string>("");
  const [onlyProblems, setOnlyProblems] = useState(false);

  const objects = useMemo(() => objectsQ.data ?? [], [objectsQ.data]);
  const priced = objects.length > 0 && objects.every(hasPricing);
  const clientName = useMemo(() => new Map((clientsQ.data ?? []).map((c) => [c.id, c.name])), [clientsQ.data]);
  const { rows, period } = useMemo(() => classify(objects, schedulesQ.data ?? []), [objects, schedulesQ.data]);
  const cities = useMemo(() => Array.from(new Set(objects.map((o) => o.city))).sort((a, b) => a.localeCompare(b, "ru")), [objects]);

  const visible = rows.filter(
    (r) =>
      (!clientId || !priced || (hasPricing(r.object) && String(r.object.client_company_id) === clientId)) &&
      (!city || r.object.city === city) &&
      (!onlyProblems || r.status !== "ok"),
  );
  const dropped = rows.filter((r) => r.status === "dropped").length;
  const unassigned = rows.filter((r) => r.unassigned).length;

  if (objectsQ.isPending || schedulesQ.isPending) {
    return <Skeleton className="h-96" />;
  }
  const error = objectsQ.error ?? schedulesQ.error;
  if (error) {
    return <p className="rounded-md border border-destructive/40 p-3 text-sm text-destructive">{error.message}</p>;
  }

  return (
    <section className="space-y-4" aria-labelledby="objects-title">
      <div>
        <h2 id="objects-title" className="text-lg font-semibold">
          Реестр объектов и субподрядчиков
        </h2>
        <p className="text-sm text-muted-foreground">
          {period ? `График смен: ${period.slice(0, 7)}. ` : "Графика смен нет. "}
          Субподрядчик считается назначенным только по графику, справочник по городам — не назначение.
        </p>
      </div>

      <div className="grid gap-2 sm:grid-cols-3">
        <Card>
          <CardContent className="p-3">
            <p className="text-xs text-muted-foreground">Объектов</p>
            <p className="text-xl font-semibold">{rows.length}</p>
          </CardContent>
        </Card>
        <Card className={cn(unassigned > 0 && "border-warning/50")}>
          <CardContent className="p-3">
            <p className="text-xs text-muted-foreground">Без субподрядчика</p>
            <p className="text-xl font-semibold">{unassigned}</p>
          </CardContent>
        </Card>
        <Card className={cn(dropped > 0 && "border-destructive/50")}>
          <CardContent className="p-3">
            <p className="text-xs text-muted-foreground">Выпали из графика смен</p>
            <p className="text-xl font-semibold">{dropped}</p>
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {priced && clientName.size > 1 && (
          <NativeSelect value={clientId} onChange={(e) => setClientId(e.target.value)} aria-label="Клиент">
            <option value="">Все клиенты ({clientName.size})</option>
            {Array.from(clientName).map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </NativeSelect>
        )}
        <NativeSelect value={city} onChange={(e) => setCity(e.target.value)} aria-label="Город">
          <option value="">Все города ({cities.length})</option>
          {cities.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </NativeSelect>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="h-4 w-4 accent-[hsl(var(--primary))]" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} />
          Только проблемные
        </label>
        <span className="ml-auto text-xs text-muted-foreground">Показано: {visible.length}</span>
      </div>

      {!priced && objects.length > 0 && (
        <p className="rounded-md bg-muted p-3 text-xs text-muted-foreground">
          Роль субподрядчика: сервер не отдаёт тариф, НДС, договор и клиента — только адрес, площадь, услуги и график.
        </p>
      )}

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Объект</TableHead>
              {priced && <TableHead>Клиент</TableHead>}
              <TableHead>Город</TableHead>
              <TableHead className="text-right">Площадь</TableHead>
              {priced && <TableHead className="text-right">Тариф в месяц</TableHead>}
              {priced && <TableHead>НДС</TableHead>}
              {priced && <TableHead>Субподрядчик</TableHead>}
              <TableHead>Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible.map((row) => {
              const o = row.object;
              return (
                <TableRow
                  key={o.id}
                  className={cn(
                    row.status === "dropped" && "bg-destructive/[0.06] hover:bg-destructive/10",
                    row.status === "unassigned" && "bg-warning/[0.08] hover:bg-warning/15",
                  )}
                >
                  <TableCell className="min-w-[16rem]">
                    <p className="font-medium">{o.name}</p>
                    {o.services && <p className="line-clamp-2 text-xs text-muted-foreground">{o.services}</p>}
                  </TableCell>
                  {hasPricing(o) && <TableCell className="min-w-[10rem]">{clientName.get(o.client_company_id) ?? "—"}</TableCell>}
                  <TableCell className="whitespace-nowrap">{o.city}</TableCell>
                  <TableCell className="whitespace-nowrap text-right tabular-nums">{formatArea(o.area_m2)}</TableCell>
                  {hasPricing(o) && (
                    <TableCell className="whitespace-nowrap text-right tabular-nums">
                      {o.monthly_tariff ? formatKzt(o.monthly_tariff) : <span className="text-muted-foreground">по заявке</span>}
                    </TableCell>
                  )}
                  {hasPricing(o) && <TableCell className="whitespace-nowrap text-xs">{vatText(o)}</TableCell>}
                  {hasPricing(o) && (
                    <TableCell className="min-w-[11rem]">
                      {o.subcontractor ? (
                        <span className="text-sm">
                          <span className="font-mono text-xs text-muted-foreground">{o.subcontractor.code}</span> {o.subcontractor.name}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  )}
                  <TableCell>
                    <StatusBadges row={row} />
                  </TableCell>
                </TableRow>
              );
            })}
            {visible.length === 0 && (
              <TableRow>
                <TableCell colSpan={priced ? 8 : 5} className="py-8 text-center text-muted-foreground">
                  Нет объектов по фильтру
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </section>
  );
}
