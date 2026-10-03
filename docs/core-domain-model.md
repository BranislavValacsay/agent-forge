# TASK 2 – Core domain model

## Implementované

Databázový základ pre governed work orchestration, vytvorený z vetvy `DEV`.
Existujúce pipeline API a worker queue zostávajú použiteľné; nové entity ešte
nie sú sprístupnené cez mutujúce API bez ACL/service layer.

| Entita | Tabuľka | Úloha |
| --- | --- | --- |
| Project | projects | Hranica plánovania, human ownership a visibility. |
| WorkItem | work_items | EPIC/STORY/TASK, parent, status, priority, actor/owner, correlation a version. |
| ExecutionRun | execution_runs | Beh agenta pre Task, parent run, provenance a optional pipeline/step bridge. |
| Result | results | Štruktúrovaný SQL/JSON výsledok, artifact references, oddelený validation/review/freshness stav. |
| AuditEvent | audit_events | Rozšírená existujúca história o actor, old/new/reason, parent event a typed references. |

`PipelineRun` zostáva behom celej pipeline. `StepRun` zostáva vykonaním nodu a
zachováva WorkerJob kontrakt. `ExecutionRun` môže existovať bez pipeline alebo
referencovať konkrétny pipeline krok. Táto fáza **nevytvára druhú worker queue**
a ešte automaticky neprevádza pipeline kroky na Work Items/ExecutionRuns.

ExecutionRun referencuje Task a agenta; version/model/provider/input metadata
sú pripravené na pripnutie snapshotu v ďalšej fáze. Result vlastní `run_id`
a `task_id`; composite FK zaručuje, že patria k tomu istému behu a práci.
Agent a pipeline verzie sú dostupné cez Result → ExecutionRun.

DB vynucuje existenciu referencií, rovnaký project parent/child, zákaz self-parent,
Epic ako root, platné hodnoty type/status/priority a párové owner_type/owner_id.
Pipeline/Step bridge nemôže spojiť krok s cudzím PipelineRun.
WorkItem má optimistic versioning cez SQLAlchemy `version_id_col`.
Úplné pravidlá typov rodičov, viacúrovňových cyklov, transitions a agregácie
Epic/Story stavov patria do TASK 3/service layer.

## Audit a kompatibilita

Pôvodné polia `kind`, `resource_type`, `resource_id`, `payload`, `message`
a `created_at` zostávajú zachované. Predstavujú action/object referencia
kontrakt; nezavádzame paralelnú audit tabuľku. `user_id` je nullable, aby audit
mohol patriť AGENT alebo SERVICE. HUMAN audit vyžaduje user_id = actor_id;
ostatní aktéri nesmú obsahovať human user_id.

Historické audit rows dostanú `actor_type=HUMAN`, `actor_id=user_id`; payloady
a pôvodné timestamps sa nemenia. Existujúci audit POST odvodzuje actor z
prihláseného človeka, nie z request payloadu. Nové doménové referencie sú
nullable kvôli zachovaniu starej histórie.

SQLite a PostgreSQL migrations inštalujú append-only triggers proti UPDATE
a DELETE. PostgreSQL blokuje aj TRUNCATE. Toto chráni bežnú application DB
session; vlastník schémy/superuser môže trigger odstrániť. Produkcia musí oddeliť
migration owner a runtime DB role. Audit list API si zatiaľ zachováva pôvodný
human scope; hierarchický audit a automatický audit všetkých actions sú TASK 4.

Result default: validation PENDING, review NOT_REQUESTED, freshness UNKNOWN.
Existencia výsledku sama neznamená validitu ani splnenie Tasku. Automatické
review/freshness pravidlá a publikovanie patria do TASK 9.

## Migrácie a spustenie

Nové Alembic revisions:

1. `0001` – frozen baseline existujúcej control-plane schémy.
2. `0002` – nové core entity, integrity constraints, backfill a append-only audit.

Migrácie nepoužívajú aktuálne `Base.metadata.create_all()` ako historický
snapshot. Baseline má zmrazené definície a overuje existujúce tabuľky, typy,
nullable/length, primary keys, foreign keys a PostgreSQL enum hodnoty pred
prevzatím inštalácie bez alembic_version. Neúplnú/nekompatibilnú legacy DB
odmietne bez automatického stampovania. Podporovaný pre-Alembic základ je
schéma commitu `9969333`; staršiu inštaláciu najprv aktualizovať na tento základ.

Príkazy z `backend`:

```bash
uv sync --extra dev --frozen
uv run python -m app.migrations
uv run alembic current
uv run alembic check
uv run python -m pytest -q
```

URL načítava rovnaké `AF_DATABASE_URL` ako API. Docker image obsahuje Alembic
konfiguráciu a migration scripts. Ad hoc startup ALTER/create_all sú nahradené
riadeným upgrade. `AF_AUTO_MIGRATE=true` zachováva jednoduchý development
bootstrap; PostgreSQL používa transaction advisory lock, SQLite BEGIN IMMEDIATE.
SQLite batch migrations dočasne vypnú FK enforcement a pred commitom overia
foreign_key_check; bežné API connections majú FK enforcement zapnutý.

Pre produkciu aplikovať migráciu samostatným deployment krokom/Jobom a spustiť
API s `AF_AUTO_MIGRATE=false`: startup potom iba kontroluje aktuálnu revision.
Samostatný Helm migration Job nie je súčasťou TASK 2. Offline `--sql` nie je
podporované, pretože baseline adoption vyžaduje live schema inspection.

Downgrade je zámerne odmietnutý: odstraňovanie planning tabuliek a audit identity
by mohlo stratiť dáta. Použiť overený backup alebo forward migration. Toto je
aditívna DB zmena; rollback starého API kódu možný iba po overení kompatibility
jeho audit insertov s novou povinnou actor identitou.

## Testy a hranice overenia

`test_core_domain.py` používa izolovanú SQLite DB a skutočné migrations:

- uloženie Epic → Story → Task → delegated Task → Run → Result → Audit,
- odmietnutie cross-project parent, cross-task Result a nesprávneho StepRun bridge,
- neplatné type/status/priority/actor/owner hodnoty a append-only audit,
- optimistic concurrency konflikt,
- zachovanie historického PipelineRun/StepRun/AuditEvent pri legacy adoption,
- idempotentný upgrade, odmietnutie čiastočnej schémy a destructive downgrade.

`test_postgres_migrations.py` je voliteľný integračný test. Vytvorí izolovanú
schému, aplikuje baseline, vloží históriu, overí adoption/core upgrade a blokovanie
UPDATE/DELETE/TRUNCATE, potom odstráni testovaciu schému:

```bash
AF_TEST_POSTGRES_URL='postgresql+psycopg://user:password@localhost/testdb' \
  uv run python -m pytest tests/test_postgres_migrations.py -q
```

Nepoužiť produkčnú DB. Test vyžaduje CREATE SCHEMA oprávnenie.
V tejto pracovnej session bol PostgreSQL test preskočený: testovacia PostgreSQL
DB nie je k dispozícii. Nebol vykonaný Kubernetes rollout ani live provider call.
Overenie: **40 passed, 1 skipped**, Ruff prešiel a `alembic check` nehlási
rozdiel medzi migrations a ORM modelom. Pôvodných 27 testov zostalo úspešných.

## Ďalší krok a otvorený dlh

TASK 3: lifecycle a úplné hierarchy rules; TASK 4: Work services/API s ACL,
idempotency a atomic state/audit/event zápisom. TASK 5: agent identity, role,
permissions a limits. TASK 15 pridá Team model/členstvo a team_id väzby.

Polymorfné owner/creator/actor IDs zatiaľ nemajú spoločný identity registry.
Version ownership, correlation inheritance a immutable runtime snapshot musí
vynútiť Work service pred dispatchom. Transactional outbox je TASK 10; tento
commit nevydáva AuditEvent za event bus. Review/Approval, live Kanban, managed
delegation a runtime integration zatiaľ implementované nie sú.
