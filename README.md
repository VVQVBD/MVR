# IC Group: договоры, объекты, спорные условия

```
backend/    FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic; PostgreSQL / Supabase (SQLite — для тестов)
  app/models.py              схема БД (см. ниже)
  app/access.py              видимость строк по ролям в API — те же правила, что RLS
  app/services/importer.py   загрузка contracts.json в БД
  app/services/contracts_v1.py  разбор полей пакета (НДС, пролонгация, ставки за м², график ОПУ)
  app/services/checks.py     автопроверки: арифметика, сроки, НДС 12→16 %, промпт-инъекции
  db/rls.sql                 Row Level Security для Supabase
  db/schema.sql              вся схема + RLS одним скриптом (сгенерирован из миграций)
  migrations/                Alembic: 0001 — таблицы, 0002 — RLS, 0003 — вью субподрядчика без цен (0002–0003 только PostgreSQL)
  scripts/seed_data.py       сидинг из contracts.json
  scripts/create_user.py     пользователи и их привязка к компании / субподрядчику
frontend/   Next.js 14: спорные условия, автопроверки, объекты (вкладки по роли)
data/       contracts.json из пакета организаторов
```

## Схема БД

| таблица | что хранит |
|---|---|
| `users` | роль `executive` / `manager` / `client` / `subcontractor`; `client_company_id` или `subcontractor_id`; `auth_user_id` — связь с Supabase Auth |
| `client_companies` | 8 компаний: код, наименование, БИН |
| `contracts` | номер, даты, срок по тексту, `renewal` (`auto_annual` / `by_agreement` / `none`), `status` на дату `status_as_of`, НДС, условия (`terms`), текст скана и найденные инъекции |
| `contract_addenda` | ДС №24 Модена, ДС №61 Лира, ДС №1 Вента: даты подписания и вступления, итог из документа |
| `facility_objects` | город, объект, площадь, внешняя и фасадная площадь, группа, услуги, тариф KZT (пусто — «по заявке»), ставка за м², базис и ставка НДС, `subcontractor_id` |
| `subcontractors` | P01, P23, P24 |
| `document_source_references` | файл, страница или страницы, лист, строка, пояснение; M2M с договорами, ДС, объектами и спорными условиями |
| `disputed_conditions` | Q-01 … Q-11: severity, topic, issue, ask, статус, кто и когда закрыл |
| `shift_schedules` | месяц, объект, субподрядчик, число ОПУ, часы, режим (ежедневно / 5/2 / пт–вс) |
| `shift_reports` | отметки смен: дата, табельный код оператора (без ФИО), статус, часы |
| `billing_acts`, `billing_act_lines` | АВР клиентам и акты субподрядчиков, суммы без НДС / НДС / с НДС |

Что сидинг берёт из `contracts.json`, а чего там нет:
- Субподрядчик назначается только по графику (`04_Операторы_и_график_сентябрь.xlsx`), справочник по городам назначением не считается. Из этого графика создаются 12 смен на сентябрь 2026: часы и число ОПУ берутся из текста услуг. Если в договоре их нет (например, у Медеу), поля остаются пустыми.
- Клиент спорного условия определяется по файлам-источникам, которые принадлежат ровно одному договору. У Q-07 клиента нет.
- `shift_reports` и `billing_acts` пустые: в `contracts.json` нет ни отметок смен, ни актов.

## Роли и доступ

| роль | видит | пишет |
|---|---|---|
| executive | всё | всё, пользователи, импорт, удаление |
| manager | всё | компании, объекты, графики, акты, статусы спорных условий |
| client | только свою компанию: договоры, ДС, объекты, спорные условия, графики и отметки по своим объектам, свои АВР, назначенных субподрядчиков | ничего |
| subcontractor | только объекты из своего графика смен — адрес, площадь, услуги, график; **без** тарифа, ставки за м², НДС, договора и клиента; свои графики, отметки и акты | отметки смен по своим графикам |

В Supabase доступ задают политики RLS (`db/rls.sql`), в FastAPI — `app/access.py`. Бекенд подключается ролью-владельцем, которую RLS не ограничивает, поэтому правила продублированы в коде.

Цены от субподрядчика скрыты на уровне столбцов. RLS умеет отбирать только строки, а права на столбцы в Supabase общие для всех пользователей `authenticated`. Поэтому прямого доступа к `facility_objects` у субподрядчика нет, и свои объекты он читает через вью `subcontractor_facility_objects` (`db/rls_0003_subcontractor_view.sql`). В API ту же роль играет схема `FacilityObjectForSubcontractor`.

## Запуск

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed_data ../data/contracts.json
.venv/bin/python -m scripts.create_user boss@icgroup.local <пароль> executive
.venv/bin/python -m scripts.create_user modena@icgroup.local <пароль> client --client modena
.venv/bin/python -m scripts.create_user p23@icgroup.local <пароль> subcontractor --subcontractor P23
.venv/bin/uvicorn app.main:app --reload   # http://localhost:8000/docs
```

```bash
cd frontend
cp .env.example .env.local && npm install && npm run dev   # http://localhost:3000
```

### Supabase
1. Задать `DATABASE_URL=postgresql+psycopg://postgres:<pwd>@db.<project>.supabase.co:5432/postgres` и `JWT_SECRET`.
2. `alembic upgrade head` создаст таблицы и RLS. Другой путь — выполнить `db/schema.sql` в SQL Editor.
3. `python -m scripts.seed_data ../data/contracts.json`.
4. Пользователям Supabase Auth заполнить `users.auth_user_id`: `create_user ... --auth-user-id <uuid>`.

`db/local_supabase_stub.sql` (заглушка `auth.uid()` и ролей) нужен только для локального PostgreSQL, на Supabase его не применять.

## Тесты

```bash
cd backend && .venv/bin/python -m pytest -q
```

RLS проверяется на настоящем PostgreSQL. Тест сам создаёт базу `icgroup_rls_test`:

```bash
PG_TEST_ADMIN_URL=postgresql+psycopg://postgres@localhost:5432/postgres .venv/bin/python -m pytest -q tests/test_rls.py
```

## Автопроверки (`GET /checks?as_of=2026-10-16`, только персонал)
| kind | что значит |
|---|---|
| arithmetic | итог документа (договора или ДС) ≠ сумма строк объектов; у Модены ДС №24 даёт +10 000 |
| line_arithmetic | площадь × ставка за м² ≠ тариф; округление до 100 тг с отклонением ≤ 50 ошибкой не считается |
| expired | срок истёк, продлить можно только допсоглашением |
| expiring | срок истекает в ближайшие 90 дней, автопролонгации нет |
| renewal_unconfirmed | исходный срок прошёл, договор действует по автопролонгации — нужно подтверждение |
| vat_rate | ставка ≠ 16 % в периоде после 01.01.2026, с пересчётом базы |
| vat_unspecified | цена указана «с НДС», ставка не названа |
| prompt_injection | в тексте документа посторонняя инструкция; цифры из текста не берутся |
