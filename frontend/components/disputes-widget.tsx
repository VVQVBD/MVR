"use client";

import { FileJson, FileSpreadsheet, FileText, FolderOpen, ShieldAlert } from "lucide-react";
import { useState } from "react";

import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useDiscrepancies } from "@/hooks/queries";
import { formatSourceLocation, sourceKind } from "@/lib/api";
import type { Dispute, Severity, Source } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useSession } from "@/store/session";

const SEVERITY: Record<Severity, { label: string; variant: NonNullable<BadgeProps["variant"]> }> = {
  high: { label: "Высокий риск", variant: "destructive" },
  medium: { label: "Средний риск", variant: "warning" },
  low: { label: "Низкий риск", variant: "muted" },
};

const SEVERITY_ORDER: Record<Severity, number> = { high: 0, medium: 1, low: 2 };

const FILTERS: { value: Severity | undefined; label: string }[] = [
  { value: undefined, label: "Все" },
  { value: "high", label: "Высокий" },
  { value: "medium", label: "Средний" },
  { value: "low", label: "Низкий" },
];

function SourceIcon({ file }: { file: string }) {
  const kind = sourceKind(file);
  const cls = "mt-0.5 h-4 w-4 shrink-0 text-muted-foreground";
  if (kind === "xlsx") return <FileSpreadsheet className={cls} aria-label="Excel" />;
  if (kind === "json") return <FileJson className={cls} aria-label="JSON" />;
  return <FileText className={cls} aria-label="PDF" />;
}

function SourceItem({ source }: { source: Source }) {
  const where = formatSourceLocation(source);
  return (
    <li className="flex gap-2.5 rounded-md border p-3">
      <SourceIcon file={source.file} />
      <div className="min-w-0 space-y-0.5">
        <p className="break-words text-sm font-medium">{source.file}</p>
        {where && <p className="text-xs text-muted-foreground">{where}</p>}
        {source.note && <p className="text-xs text-muted-foreground">{source.note}</p>}
        {source.quote && <p className="text-xs italic">«{source.quote}»</p>}
      </div>
    </li>
  );
}

function SourcesDialog({ dispute }: { dispute: Dispute }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <FolderOpen className="h-3.5 w-3.5" />
          Источники ({dispute.sources.length})
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {dispute.id}: {dispute.topic}
          </DialogTitle>
          <DialogDescription>Первоисточники из пакета документов: файл, страница PDF, лист и строка Excel.</DialogDescription>
        </DialogHeader>
        {dispute.sources.length ? (
          <ul className="space-y-2">
            {dispute.sources.map((s) => (
              <SourceItem key={s.id} source={s} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Источники не указаны.</p>
        )}
      </DialogContent>
    </Dialog>
  );
}

function DisputeCard({ dispute }: { dispute: Dispute }) {
  const sev = SEVERITY[dispute.severity];
  return (
    <Card className={cn("flex flex-col", dispute.severity === "high" && "border-destructive/40")}>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs text-muted-foreground">{dispute.id}</span>
          <Badge variant={sev.variant}>{sev.label}</Badge>
          {dispute.status !== "open" && <Badge variant="outline">{dispute.status === "resolved" ? "решён" : "отклонён"}</Badge>}
        </div>
        <CardTitle>{dispute.topic}</CardTitle>
        <p className="text-xs text-muted-foreground">{dispute.client_name ?? "Все клиенты / общий вопрос"}</p>
      </CardHeader>
      <CardContent className="flex-1 space-y-3 text-sm">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Проблема</p>
          <p>{dispute.issue}</p>
        </div>
        {dispute.ask && (
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Что нужно сделать</p>
            <p>{dispute.ask}</p>
          </div>
        )}
      </CardContent>
      <CardFooter>
        <SourcesDialog dispute={dispute} />
      </CardFooter>
    </Card>
  );
}

export function DisputesWidget() {
  const role = useSession((s) => s.role);
  const [severity, setSeverity] = useState<Severity | undefined>(undefined);
  const { data, isPending, isError, error } = useDiscrepancies({ severity });

  // На защите первыми идут карточки высокого риска, внутри уровня — по номеру вопроса
  const sorted = [...(data ?? [])].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] || a.id.localeCompare(b.id),
  );
  const counts = (data ?? []).reduce<Record<Severity, number>>(
    (acc, d) => ({ ...acc, [d.severity]: acc[d.severity] + 1 }),
    { high: 0, medium: 0, low: 0 },
  );

  return (
    <section className="space-y-4" aria-labelledby="disputes-title">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="disputes-title" className="text-lg font-semibold">
            Реестр расхождений и рисков
          </h2>
          <p className="text-sm text-muted-foreground">Спорные условия договоров, которые нужно закрыть с клиентами.</p>
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Фильтр по уровню риска">
          {FILTERS.map((f) => (
            <Button
              key={f.label}
              size="sm"
              variant={severity === f.value ? "default" : "outline"}
              onClick={() => setSeverity(f.value)}
              aria-pressed={severity === f.value}
            >
              {f.label}
            </Button>
          ))}
        </div>
      </div>

      {isPending && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-56" />
          ))}
        </div>
      )}

      {isError && <p className="rounded-md border border-destructive/40 p-3 text-sm text-destructive">{error.message}</p>}

      {data && data.length === 0 && (
        <Card>
          <CardContent className="flex items-start gap-3 p-4 text-sm">
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
            <p className="text-muted-foreground">
              {role === "subcontractor"
                ? "Спорные условия договоров с клиентами субподрядчику не показываются — сервер вернул пустой список."
                : "Нет спорных условий с выбранным уровнем риска."}
            </p>
          </CardContent>
        </Card>
      )}

      {data && data.length > 0 && (
        <>
          {!severity && (
            <p className="text-xs text-muted-foreground">
              Всего {data.length}: высокий — {counts.high}, средний — {counts.medium}, низкий — {counts.low}
            </p>
          )}
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {sorted.map((d) => (
              <DisputeCard key={d.id} dispute={d} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}
