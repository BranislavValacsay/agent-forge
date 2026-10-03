# Work orchestration: audit a implementačný plán

## Rozsah a overený základ

TASK 1 z implementačného zadania Agent Forge, auditovaný 2026-10-03.
Východiskový commit: `9969333a2e96288f367e8eea753278ecf5a47876` na `main`.
Audit zahŕňa modely, API, autentifikáciu/ACL, pipeline orchestration, worker
protokol a executory, frontend, testy, Compose a Helm. Nie je to potvrdenie
produkčnej pripravenosti ani implementácia TASK 2–18.

**Záver:** existujúci pipeline a worker engine je použiteľný. Chýba planning
vrstva a agent identity/governance. Pridávať ich nad existujúce execution
kontrakty; neprepisovať builder, DAG ani worker protocol.

## Čo existuje, čo reuse a čo chýba

| Oblasť | Overené v kóde | Reuse / potrebná zmena |
| --- | --- | --- |
| DB | SQLAlchemy, PostgreSQL v Compose; lokálny default SQLite | PostgreSQL ponechať source of truth. Chýbajú verziované migrácie. |
| Projects | Model ani router neexistuje | Pridať Project ako hranicu ACL a ownership; hierarchia Work Items patrí do projektu. |
| Planning | EPIC/STORY/TASK a lifecycle neexistujú | Jeden WorkItem s `type`, `parent_id`, projektom, vlastníkmi a optimistickou verziou. |
| Agents | Agent, AgentKind, konfigurácia, vstup/výstup, CPU/GPU requirement | Zachovať AI/script/MCP/CrewAI kind; role CHIEF/DRONE/AUDITOR je nezávislá os. Chýbajú permissions, capabilities, active state a governance limits. |
| Versions | AgentVersion a PipelineVersion tabuľky, nullable odkazy z behov | Samotné tabuľky nestačia: create-run ani job config verzie nepripínajú. Pridať snapshot/pinning pri vytvorení behu. |
| Pipelines | Builder, typované porty, validácia DAG, legacy a LangGraph engines | Zachovať graf a existujúce `/api/v1/pipelines/{id}/runs`. Pridať Work API operations cez service layer. |
| Execution | PipelineRun, StepRun, WorkerJob, leases, CPU/GPU a executor matching | Rozšíriť existujúci execution model o task/correlation/parent väzby. Nevytvárať druhú nesúvisiacu queue. |
| Runs | JSON input/output, timestamps, status; run retry/cancel | Work Item status musí byť oddelený od RunStatus. Samostatný agent run/subrun treba explicitne naviazať na existujúce kroky. |
| Results | Výstup je StepRun.output_payload a event payload | Pridať samostatný Result s provenance, review, freshness a artifact references. JSON payload v SQL je vhodný; filtrované metadata majú vlastné stĺpce. |
| ACL | AclEntry, users/groups, owner/root shortcut, view/run/edit/manage | `has_permission` v security.py reálne kontroluje skupiny. Rozšíriť na Actor HUMAN/AGENT/SERVICE a projekt/team/work/result scope. Chýba správa ACL grantov cez API/UI. |
| Teams | Group a GroupMember pre ľudí; tvorca skupiny sa stane členom | ACL Group nie je agent Team. Team musí mať stabilné human/agent členstvo a admin-only tvorbu. |
| Audit | AuditEvent s user_id, resource a payload; POST/GET audit API | Client-side oznámenia nie sú autoritatívny audit. Chýba audit každej mutácie, old/new, actor/run/correlation/parent a DB append-only enforcement. |
| Events | Per-run RunEvent, zápis worker udalostí | Rozšíriť transactional Postgres outbox; chýba spoločný replayable stream pre scheduler, parent continuation a Kanban. |
| Live UI | SSE backend `/api/v1/runs/{id}/stream`; RunsPage polling každé 2 s | Reuse autentifikáciu a krátke DB sessions. Pridať cursor/replay, ACL revalidation a SSE bez proxy bufferingu. Kanban zatiaľ neexistuje. |
| Hierarchia | Run detail a kroky | Chýba Project → Epic → Story → Task → Run → Result → Review drill-down a agregácie. |
| Runtime | ExecutionSpec, worker executory, LangGraph checkpointy, CrewAI node | Zachovať executor boundary. Pridať explicitný invoke/resume/cancel/status interface bez prenosu control plane do runtime. |
| Kubernetes | Helm API/web, optional CrewAI worker, Ingress/Route a bezpečnostný kontext | Základ deploymentu existuje. Chýbajú probes, migračný Job a validácia viacerých replík; Kubernetes Job executor je stále budúca práca. |
| Artifacts | Compose MinIO; výstupy/logy v SQL | Reálny S3 upload/reference lifecycle chýba; nevydávať deklarovaný MinIO za hotové artifact storage. |
| Observability | RunEvent logy a `/health` | Chýbajú control-plane metriky, trace/correlation naprieč delegovaním a readiness závislá od DB. |

## Konflikty a riziká, ktoré treba vyriešiť pred autonómiou

1. **Agent nemá vlastnú autentifikovanú identitu.** `current_user` a
   `has_permission` pracujú s User; worker token identifikuje worker, nie
   delegujúceho agenta. Agent nesmie zdediť root oprávnenia vlastníka.
   Všetky Work API actions musia získať Actor z dôveryhodnej autentifikácie;
   `actor_id` z request payloadu nesmie rozhodovať o oprávneniach.
2. **Prístup k pipeline nie je automaticky prístup ku všetkým agentom.**
   `pipelines.create_run` kontroluje pipeline ACL, ale neoveruje run access
   ku každému referencovanému agentovi. `_job_config` načíta agenta a jeho
   provider secret. Pred dispatchom treba overiť aj agent/resource ACL.
3. **Konfigurácia počas behu je mutable.** `create_run` uloží graph snapshot,
   ale `_job_config` a `execution_spec_for_node` čítajú aktuálny Agent.
   AgentVersion/PipelineVersion sa pri create-run nepripínajú. Zmena draftu
   po zaradení jobu môže zmeniť reálne vykonanie. Snapshot musí obsahovať
   nemennú konfiguráciu a version/hash metadata, nikdy plaintext secret.
4. **CrewAI má delegovanie mimo governance.** Worker `run_crewai` prenáša
   `member.allow_delegation` priamo do CrewAgent. To nevytvorí platformový
   child Task/Subrun ani nevynúti platformové budget/depth limity.
   V managed režime interné delegovanie vypnúť, kým adapter nebude používať
   Work API. Neoznačiť CrewAI task callback za úplný delegation audit.
5. **Checkpoint a SQL state nemajú spoločnú transakciu.** LangGraph saver
   používa inú connection; graph advance prebehne pred `db.commit()` worker
   completion. Pri výpadku treba reconciliation podľa durable command/event
   ID a idempotentné resume. Outbox samotný nevyrieši atomicitu checkpointu.
6. **RunEvent/AuditEvent sú doplnkové záznamy.** Audit router prijíma payload
   od človeka a listuje jeho vlastné eventy; CRUD routers automaticky nepíšu
   audit. Append-only nie je chránené triggerom/DB role. Nové service actions
   musia zapisovať doménový audit aj outbox v tej istej transakcii so stavom.
7. **Existujú locky, ale nie všetky execution limity.** Worker claim používa
   Postgres `FOR UPDATE SKIP LOCKED` aj podmienený lease update; completion
   lockuje PipelineRun. Expired lease recovery je osobitná cesta, ktorú treba
   otestovať pri súbehu s completion. Depth, child count, token/cost budget a
   capacity musia byť transakčne vynútené naprieč celým delegation tree.
8. **SSE má obmedzené recovery/security správanie.** Stream načítava celú
   run event históriu každé 2 s; `last_id` existuje len v konkrétnej connection,
   bez SSE `id`/Last-Event-ID replay. Autorizuje na začiatku, nie po revokácii.
   Nginx nemá explicitné vypnutie bufferingu. Nevytvárať rovnaký limit pre Kanban.
9. **Bootstrap schema nie je migračný systém.** `create_schema` robí create_all
   a ad hoc ALTER pri API startup; pri viacerých replikách môžu pretekať.
   Baseline + migračný Job musia predchádzať rolloutom nového modelu.
10. **Declarácia triggera nie je cron scheduler.** PipelineTrigger a API
    existujú, ale v auditovaných súboroch nie je pravidelný cron dispatch loop.
    Work scheduler a cron triggers majú odlišnú zodpovednosť.

Ďalšie existujúce limity: `max(sequence)+1` nie je bezpečné globálne číslovanie
pri súbehu; Helm API/web selectors nemajú release-instance label; produkčné
config defaults vyžadujú nastavenie secret/cookies/registrácie. Nie sú riešené
týmto dokumentačným commitom.

## Navrhované hranice implementácie

- **Planning:** Project/Team/WorkItem je SQL source of truth. Backend kontroluje
  prípustné typy rodičov, rovnaký project scope, cykly, transitions a ownership.
- **Execution:** PipelineRun zostane kontajnerom pipeline; StepRun zachová
  node/job väzby. Pred TASK 2 explicitne rozhodnúť, či je agent Run rozšírený
  StepRun alebo samostatný ExecutionRun s odkazom na StepRun. Samostatný run
  musí podporovať agent invocation bez pipeline. Nevytvárať druhý WorkerJob systém.
- **Governance:** Result/Review/Audit + transactional outbox sú oddelené od
  execution status. Task DONE vyžaduje podľa policy schválený aktuálny Result;
  worker success sám osebe neznamená DONE.
- **Security:** zachovať user/group ACL správanie pre existujúce entity;
  nové actor/resource scope kontroly deny-by-default. Role udeľuje zodpovednosť,
  explicitná permission povoľuje action. Public pipeline nesmie obísť agent ACL.
- **Idempotency/concurrency:** scope idempotency key na actor + action + resource,
  porovnávať request hash, konflikt pri inom payloadu. Version pre update/transition;
  DB locks pre scheduler, aggregate budget a parent resume.
- **Delegation:** významná práca vytvára child Task; inline helper vytvára
  Subrun s rovnakými ACL, correlation a limit checks. Parent completion čaká na
  požadované child Results/Reviews. Review/reject, failure, cancel a timeout majú
  explicitný recovery path; žiadne skryté spawnovanie.

## Backlog a poradie podľa závislostí

Čísla odkazujú na pôvodné zadanie. Reuse neznamená hotový acceptance test.

| TASK | Stav po audite | Ďalší konkrétny výstup / závislosť |
| --- | --- | --- |
| 1 Audit | Hotové týmto dokumentom | Overený základ, gap analysis, test baseline. |
| 2 Core domain | Chýba planning/result; execution/audit reuse | Alembic baseline, Project a core WorkItem/Run/Result väzby; audit actor fields; DB constraints. |
| 3 Lifecycle | Chýba | State machine, recovery transitions a hierarchické pravidlá, optimistic concurrency. |
| 4 Work API | Chýba | Jedna service transaction pre state + audit + outbox; ACL a idempotency od prvého mutujúceho endpointu. |
| 5 Permissions | Chýba | Agent role, explicitné permissions a validované execution limits; runtime snapshot. |
| 6 Delegation | Chýba | Vyžaduje 5, 7, 10, agent identity a immutable config; child/parent task/run/correlation, resume po review. |
| 7 Scheduler | Worker dispatch existuje | Pridať capability-based task → agent výber, priority, access a capacity; reuse job lease protokol. |
| 8 Inline | Chýba | Managed Subrun bez Task; rovnaké authority/limit checks, cancel a audit. |
| 9 Validation | Chýba | Result + Review, approve/reject, publish policy, freshness metadata a manuálna invalidácia. |
| 10 Events | Per-run eventy existujú | Outbox založiť už pri 2–4; consumer checkpoint/retry a dedup pred 6–7. Bez Kafky. |
| 11 Live backend | SSE pattern existuje | Project-scoped SSE stream, cursor/replay/revalidation, krátke DB sessions a proxy config. |
| 12 Kanban | Chýba | Board z Work API, required filtre; updates výhradne cez backend transitions. |
| 13 Detail | Run detail reuse | Hierarchy, children, runs, results/reviews, audit a delegation drill-down. |
| 14 Overview | Chýba | SQL agregácie podľa autorizovaného project/team scope; stale/review/blocked počty. |
| 15 Teams | Human ACL Group reuse | Minimálne Team a členstvo pridať pred team-scoped scheduling; ľudská/admin tvorba. |
| 16 Pipeline integration | Graph/worker boundary reuse | Work operations používajú service API, child pipeline provenance a completion events. |
| 17 Runtime boundary | ExecutionSpec/worker reuse | Definovať invoke/resume/cancel/status ešte pred 6–8; existujúci runtime ako prvý adapter. |
| 18 E2E | Chýba | Human → Chief → child Drone → Result → Auditor → approved → parent resume, viditeľné na Kanbane. |

Odporúčané reviewable inkrementy:

1. **Domain + migrations:** TASK 2, najmenšie Project/Team identity základy,
   audit/outbox schéma. Acceptance: migrate prázdnu aj existujúcu DB; pôvodné
   runy sú čitateľné; FK a constraints zabránia neplatným referenciám.
2. **Governed Work API:** TASK 3–5 a zápisová časť 10. Acceptance: EPIC/STORY/TASK
   CRUD a transitions, agent vs human ACL, neprípustný cross-project parent,
   rollback bez eventu, retry bez duplicity, konfliktný update.
3. **Execution:** TASK 7, základ 17 a Team permissions; version pinning a
   checkpoint reconciliation. Acceptance: PostgreSQL concurrent claim bez
   duplicitného behu, agent access a capacity checks, crash/recovery.
4. **Delegation + validation:** TASK 6, 8, 9 a event consumers 10. Acceptance:
   parent resume presne raz po schválení children; odmietnuté delegovanie bez
   práva, depth/budget breach, timeout/cancel, stale a invalid Result.
5. **Live visibility:** TASK 11–14. Acceptance: SSE reconnect a revokácia,
   board/detail/summary sú backend projections, všetky požadované filtre.
6. **Integration demo:** TASK 16 + 18. Acceptance: celý scenár s audit trail,
   test runtime bez plateného providera, restart uprostred execution; potom
   optional reálny provider smoke test.

Kafka, operator, billing, marketplace, autonómna tvorba teams, AI scheduler
a redesign buildera zostávajú mimo tejto fázy.

## Overenie TASK 1

Na nezmenenom runtime kóde s dependencies z `backend/uv.lock`:

| Kontrola | Výsledok |
| --- | --- |
| `cd backend && uv sync --extra dev --frozen` | Úspešné. |
| `cd backend && uv run python -m pytest -q` | **27 passed**, 11 warnings. |
| `cd backend && uv run ruff check app tests --output-format concise` | All checks passed. |
| `cd frontend && npm ci --no-audit --no-fund && npm run build` | Úspešné TypeScript a Vite production build. |

`uv run pytest -q` bez editable installation zlyhal pri importe `app`;
`uv run python -m pytest -q` funguje z backend directory. Test suite používa
SQLite: výsledok **neoveruje PostgreSQL locks, migrácie ani multi-replica
recovery**. Nie sú spustené reálne Kubernetes/OpenShift deploymenty ani live
LLM/CrewAI provider calls. Build hlási chunk nad 500 kB; backend hlási
deprecation warnings a krátky development JWT secret. Nové testy, endpointy
ani migrácie v TASK 1 nepribudli; runtime správanie sa nemení.

Existujúci architektonický dlh je explicitne zaznamenaný vyššie. Tento audit
nepridáva nové runtime abstrakcie a nedokazuje uzavretie žiadneho TASK 2–18.
