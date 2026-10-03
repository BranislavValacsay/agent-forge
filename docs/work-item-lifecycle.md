# TASK 3 — Work Item lifecycle a hierarchia

TASK 3 pridáva aplikačnú doménovú vrstvu v `backend/app/work_lifecycle.py`.
Nadväzuje na [TASK 2 databázový základ](core-domain-model.md). Schéma databázy
sa nemení. Existujúce pipeline, LangGraph, worker protokol a ich endpointy
naďalej používajú pôvodný runtime.

## Človek, Chief a ďalší agenti

Operácie prijímajú dôveryhodnú identitu `Actor(HUMAN | AGENT | SERVICE, id)`.
Človek potrebuje aktívny účet a existujúce oprávnenie `edit` na projekt.
Agent musí existovať v registri a mať vlastný explicitný projektový ACL grant
`edit`, `manage` alebo `owner`; nepreberá oprávnenia človeka, ktorý ho vytvoril.
Service identita tiež potrebuje explicitný projektový grant.

Chief môže byť takýmto agentom. Názov alebo rola Chief mu automaticky nedáva
vyššie oprávnenia. Vytváranie taskov človekom aj oprávneným Chiefom bude
prechádzať spoločným Work API. TASK 3 zatiaľ poskytuje prechody stavov a zmenu
rodiča, nie verejný create endpoint ani autentifikáciu agentov.

`Actor` je interný kontrakt, nie pole dôveryhodné z REST request body.
TASK 4 musí zostaviť identitu z autentifikácie a volať túto vrstvu; TASK 5
doplní agent capabilities a delegovanie. Samotný projektový ACL grant dnes
neznamená, že agent už má dostupný tool na vytvorenie alebo zmenu práce.

## Povolené prechody Task

| Zo stavu | Do stavu |
| --- | --- |
| BACKLOG | READY, CANCELLED |
| READY | BACKLOG, ASSIGNED, BLOCKED, NEEDS_INPUT, CANCELLED |
| ASSIGNED | RUNNING, READY, BLOCKED, NEEDS_INPUT, FAILED, CANCELLED |
| RUNNING | VALIDATING, WAITING_FOR_CHILDREN, BLOCKED, NEEDS_INPUT, FAILED, CANCELLED |
| VALIDATING | REVIEW, WAITING_FOR_CHILDREN, NEEDS_INPUT, FAILED, CANCELLED |
| REVIEW | DONE, READY, BLOCKED, STALE, FAILED, CANCELLED |
| DONE | STALE |
| BLOCKED | READY, FAILED, CANCELLED |
| FAILED | READY, CANCELLED |
| CANCELLED | Žiadny; terminálny stav |
| WAITING_FOR_CHILDREN | RUNNING, VALIDATING, BLOCKED, FAILED, CANCELLED |
| NEEDS_INPUT | READY, FAILED, CANCELLED |
| STALE | READY, CANCELLED |

Nepovolený prechod ani zápis rovnakého stavu nevytvorí auditnú udalosť.
BLOCKED, FAILED, CANCELLED, NEEDS_INPUT a STALE vyžadujú dôvod. Návrat do READY
z REVIEW, FAILED, BLOCKED, NEEDS_INPUT alebo STALE tiež vyžaduje dôvod.

ASSIGNED a RUNNING vyžadujú existujúceho owner agenta alebo aktívneho owner
človeka. WAITING_FOR_CHILDREN vyžaduje nedokončené podúlohy; pokračovanie do
RUNNING alebo VALIDATING vyžaduje všetky podúlohy DONE. Rodičovský Task si
ponecháva vlastný lifecycle a vlastný výsledok, preto sa automaticky neukončí
po dokončení podúloh.

DONE vyžaduje všetky podúlohy DONE a posledný ExecutionRun `succeeded`
s posledným Result v kombinácii `VALID / APPROVED / CURRENT`. Po retry alebo
rework do READY treba nový run; starší schválený výsledok nestačí. Výber runu
a výsledku je podľa `created_at`, pri zhode podľa ID. Uzavretie do DONE,
FAILED alebo CANCELLED odmietne queued/running run v celom podstrome.
CANCELLED navyše vyžaduje podúlohy DONE alebo CANCELLED. Táto vrstva runy
nezastavuje a nevykonáva validáciu či schvaľovanie výsledkov.

## Epic, Story a zmena rodiča

Epic nemá rodiča. Story môže patriť pod Epic; Task pod Story alebo Task.
Samostatné položky bez rodiča sú povolené. Rodič musí patriť do rovnakého
projektu a hierarchia nesmie obsahovať cyklus.

Epic a Story nemajú ručný status transition. Po zmene potomka sa stav
dotknutých kontajnerov odvodí zo všetkých descendant Tasks, vrátane
rodičovských Tasks. Prázdna Story prispieva do Epic ako BACKLOG.

Pravidlá agregácie sa vyhodnocujú v tomto poradí:

1. Prázdny scope je BACKLOG; všetko DONE je DONE; všetko CANCELLED je CANCELLED.
2. Výnimky majú prioritu FAILED, BLOCKED, STALE, NEEDS_INPUT, WAITING_FOR_CHILDREN.
3. CANCELLED zmiešaný s inými stavmi znamená BLOCKED a vyžaduje rozhodnutie.
4. Iba DONE/REVIEW znamená REVIEW; iba DONE/REVIEW/VALIDATING znamená VALIDATING.
5. Iná kombinácia obsahujúca RUNNING, VALIDATING, REVIEW alebo DONE znamená RUNNING.
6. Nasleduje ASSIGNED, READY a nakoniec BACKLOG.

Presun pod iného rodiča vyžaduje dôvod a celý presúvaný scope musí byť
BACKLOG, READY, BLOCKED, NEEDS_INPUT alebo STALE, bez aktívnych runov.
Nie je povolená zmena scope uzavretého rodičovského Tasku. Prepočítajú sa
stavy starých aj nových predkov a invalidujú sa načítané ORM vzťahy.
Create/update Work API musí znovu použiť validáciu hierarchie a zabezpečiť
audit a prepočet pri vytvorení novej práce; priame ORM zápisy tieto pravidlá
nepresadzujú.

## Audit a súbežné zápisy

Každá operácia vyžaduje aktuálny `expected_version`; zastaraná verzia vyvolá
`LifecycleConflict`. PostgreSQL zamyká projekt pomocou `SELECT FOR UPDATE`,
SQLite získa writer lock pred savepointom. Projektový zámok zatiaľ serializuje
všetky lifecycle operácie daného projektu. Budúce create/update/run operácie
musia dodržať ten istý kontrakt zamykania.

Zmena a audit sa zapisujú v jednom savepointe. Volajúci rozhoduje o commit
alebo rollback celej transakcie. Rozpracované ORM zmeny WorkItem treba
pred vstupom explicitne flushnúť; služba ich potichu neprepíše.

Audit obsahuje `STATUS_CHANGED`, `PARENT_CHANGED` a `STATUS_DERIVED`,
identitu aktéra, predchádzajúcu a novú hodnotu aj verziu, dôvod, projekt,
Work Item a correlation ID. Odvodené udalosti odkazujú na príčinnú udalosť
cez `parent_event_id`. Append-only ochranu poskytujú existujúce DB triggery.
Pri chybe sa stav aj audit vrátia späť; nevznikne čiastočný úspech.

Kanban bude čítať tento doménový stav a jeho ovládacie prvky budú volať
rovnaké Work API ako človek alebo Chief. Live event transport/outbox zatiaľ
nie je implementovaný; samotný audit nevysiela UI udalosti.

## Overenie a nasledujúci krok

`backend/tests/test_work_lifecycle.py` overuje normálny flow, zakázané prechody,
dôvody, explicitné agent ACL, owner a completion podmienky, retry, waiting,
odvodené stavy, cykly, reparent, rollback aj dvoch súbežných SQLite writerov.
Existujúce testy naďalej pokrývajú pipeline runtime, worker protokol a migrácie.
Pri overení TASK 3 prešlo 83 backend testov, z toho 43 lifecycle testov;
Ruff kontrola `app`, `tests` a `migrations` prešla.
PostgreSQL integračný test je voliteľný cez `AF_TEST_POSTGRES_URL`; bez
dostupného PostgreSQL sa preskočí. PostgreSQL lifecycle concurrency ešte
nebola integračne overená.

TASK 4: Projects/Work Items API vrátane vytvorenia tasku oprávneným človekom
aj agentom, assignment, transition, reparent a audit lookup. API bude používať
doménovú vrstvu a bezpečne mapovať identitu, version conflict a validation
errors. Potom nasledujú capabilities/delegovanie a runtime bridge; až tie
spoja task s reálnym behom agenta a live Kanbanom.
