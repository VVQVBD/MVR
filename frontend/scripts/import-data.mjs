import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import XLSX from "xlsx";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(here, "..");
const dataRoot = path.resolve(frontendRoot, "..", "data");
const outputPath = path.join(frontendRoot, "public", "data", "month-close-september-2026.json");
const period = "2026-09";

const source = (file, sheet, row, field) => ({ file, ...(sheet && { sheet }), ...(row && { row }), ...(field && { field }) });
const audited = (value, sources, calculation) => ({ value, sources, ...(calculation && { calculation }) });
const text = (value) => String(value ?? "").trim();
const has = (value, fragment) => text(value).includes(fragment);

function findWorkbook(requiredSheets) {
  for (const name of fs.readdirSync(dataRoot).filter((file) => file.endsWith(".xlsx"))) {
    const workbook = XLSX.readFile(path.join(dataRoot, name), { cellDates: true });
    if (requiredSheets.every((sheet) => workbook.SheetNames.includes(sheet))) {
      return { name: "05_Факт_сентябрь_2026.xlsx", workbook };
    }
  }
  throw new Error(`Не найден Excel-файл с листами: ${requiredSheets.join(", ")}`);
}

function rows(workbook, sheetName) {
  return XLSX.utils.sheet_to_json(workbook.Sheets[sheetName], { defval: null, raw: false });
}

function objectId(value) {
  if (has(value, "Норд")) return "nord";
  if (has(value, "Самал Сити")) return "samal-city";
  return null;
}

const contracts = JSON.parse(fs.readFileSync(path.join(dataRoot, "contracts.json"), "utf8"));
const fact = findWorkbook(["Отметки", "Замечания клиентов"]);
const marks = rows(fact.workbook, "Отметки");
const remarks = rows(fact.workbook, "Замечания клиентов").map((row, index) => ({ ...row, __sourceRow: index + 2 }));
const acts = fact.workbook.SheetNames
  .filter((sheet) => sheet.startsWith("Акт субподрядчика"))
  .flatMap((sheet) => rows(fact.workbook, sheet).map((row, index) => ({ sheet, row, sourceRow: index + 2 })));

const objects = [
  { id: "nord", title: "ТРЦ «Норд»" },
  { id: "samal-city", title: "ТРЦ «Самал Сити»" },
].map((mall) => {
  const clientRemarks = remarks.filter((remark) => objectId(remark["Объект"]) === mall.id).map((remark) => ({
    id: text(remark.ID), description: text(remark["Описание"]), detectedAt: text(remark["Выявлено"]),
    dueAt: text(remark["Срок устранения"]), resolvedAt: text(remark["Устранено"]) || null,
    status: remark["Устранено"] ? "resolved" : "open", sources: [source(fact.name, "Замечания клиентов", remark.__sourceRow)],
  }));
  const reconciliation = contracts.clients.flatMap((client) => (client.objects ?? []).map((object) => ({ client, object })))
    .filter(({ object }) => objectId(object.object) === mall.id)
    .map(({ client, object }) => {
      const payoutRows = acts.filter(({ row }) => text(row["Договор клиента"]) === client.contract && objectId(row["Объект"]) === mall.id);
      const payout = payoutRows.reduce((sum, { row }) => sum + Number(row["Сумма, тг (без НДС)"] ?? 0), 0);
      const revenue = Number(object.monthly_tariff ?? 0);
      const sources = object.sources ?? [];
      const anomalies = [
        ...(payoutRows.length === 0 ? [{ code: "MISSING_SUBCONTRACTOR_ACT", severity: "medium", message: "Для договорного объекта не найдена строка в акте субподрядчика.", sources }] : []),
      ];
      return {
        id: `${mall.id}:${client.contract}`,
        contract: audited(client.contract, sources), client: client.client, zone: object.object, subcontractor: object.subcontractor,
        revenue: audited(revenue, sources, "Договорный месячный тариф"),
        subcontractorPayout: audited(payout, payoutRows.map(({ sheet, sourceRow }) => source(fact.name, sheet, sourceRow, "Сумма, тг (без НДС)")), "Сумма строк акта субподрядчика"),
        operatorPayout: audited(null, [], "Не рассчитывается: отсутствует связь отметок с объектом и планом смен"),
        marginBeforeOperatorPayout: audited(revenue - payout, [...sources, ...payoutRows.map(({ sheet, sourceRow }) => source(fact.name, sheet, sourceRow))], "Выручка − выплата субподрядчику; перед использованием проверить базу НДС"),
        vatBasis: object.vat, anomalies, status: anomalies.length ? "review" : "closed",
      };
    });
  const kpi = reconciliation.reduce((total, row) => ({ revenue: total.revenue + row.revenue.value, subcontractorPayout: total.subcontractorPayout + row.subcontractorPayout.value, marginBeforeOperatorPayout: total.marginBeforeOperatorPayout + row.marginBeforeOperatorPayout.value, discrepancies: total.discrepancies + row.anomalies.length }), { revenue: 0, subcontractorPayout: 0, marginBeforeOperatorPayout: 0, discrepancies: clientRemarks.filter((remark) => remark.status === "open").length });
  return { ...mall, reconciliation, clientRemarks, kpi: { ...kpi, operatorPayout: null, operatorPayoutStatus: "unavailable_without_shift_object_mapping" } };
});

const unlinkedShifts = marks.map((mark, index) => ({
  id: text(mark["ID смены"]), objectId: "unlinked", operatorId: text(mark["Оператор"]),
  actual: audited({ checkIn: text(mark["Отметка прихода"]), checkOut: text(mark["Отметка ухода"]), checklistPhoto: text(mark["Фото чек-листа"]) === "да" }, [source(fact.name, "Отметки", index + 2)]),
  anomalies: [{ code: "UNLINKED_SHIFT", severity: "high", message: "Нет файла графика для связи смены с объектом и планом.", sources: [source(fact.name, "Отметки", index + 2)] }, ...(text(mark["Фото чек-листа"]) !== "да" ? [{ code: "MISSING_CHECKLIST", severity: "medium", message: "Отсутствует фото чек-листа.", sources: [source(fact.name, "Отметки", index + 2, "Фото чек-листа")] }] : [])],
  status: "unlinked",
}));

const output = {
  schemaVersion: "1.0", period, currency: contracts.currency ?? "KZT",
  sourcePolicy: "Финансовые значения хранят ссылку на исходный документ. Смены без объектной связи не распределяются автоматически.",
  objects, unlinkedShifts,
  disputes: contracts.disputed_conditions.map((dispute) => ({ id: dispute.id, severity: dispute.severity, topic: dispute.topic, description: dispute.issue, request: dispute.ask, status: "open", sources: dispute.sources })),
};

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");
console.log(`Создан ${path.relative(frontendRoot, outputPath)}`);
console.log(`Объекты: ${objects.length}; непривязанные отметки: ${unlinkedShifts.length}; споры: ${output.disputes.length}`);
