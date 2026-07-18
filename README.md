# Agent Forge

Univerzálna webová platforma na vytváranie, testovanie, skladanie, spúšťanie a sledovanie AI a script agentov.

## Aktuálne implementované

- lokálna registrácia a login; prvý používateľ je root,
- SQL model pre users, groups, ACL, agentov, verzie, pipeline, triggery a runy,
- AI/script/CrewAI agent registry s výberom reálne pripojeného providera a modelu,
- Ollama a OpenAI-compatible provider discovery; žiadne falošné prednastavené modely,
- IP/hostname, port, voliteľný šifrovaný API kľúč a test spojenia,
- prázdny drag-and-drop pipeline builder s Agent, Trigger, Transform a Output nodes,
- schema builder pre viacero pomenovaných vstupov a výstupov typu string, JSON, number, boolean, file, image alebo any,
- typované porty na pipeline nodes a explicitné mapovanie výstup kroku → vstup ďalšieho kroku,
- LangGraph ako predvolený perzistentný engine pipeline; legacy engine zostáva počas migrácie dostupný na rollback,
- paralelný DAG scheduler: fan-out, fan-in a viacnásobné použitie jedného pomenovaného výstupu vo viacerých vetvách,
- izolované vstupy vetiev, ochrana pred cyklami a zákaz viacerých zdrojov zapisujúcich do rovnakého cieľového portu,
- samostatné FLOW spojenia pre poradie vykonania aj pri agentoch bez dátových portov,
- kontrola povinných vstupov a typovej kompatibility pred uložením,
- mazanie nodes tlačidlom aj klávesom Delete/Backspace,
- Manual, Cron a Called/API trigger nodes,
- vizuálny Run View s krokmi, input/output, activity, logs a artifacts,
- samostatný register Pipelines a OpenShift/Tekton-like PipelineRuns históriu s rozkliknutím každého behu,
- živé obnovovanie stavov, progressu, udalostí a worker logov bez refreshu stránky,
- SSE endpoint pre živé run udalosti,
- Docker Compose pre PostgreSQL, Redis, MinIO, API a web,
- funkčné menu pre používateľov, ACL skupiny, providerov/modely a deployment,
- základný Helm chart a OpenShift Route,
- žiadne ukážkové pipeline ani historické runy v čistej inštalácii.
- GitLab Runner-like worker protokol s jednorazovou registráciou, heartbeatom, job lease a automatickým návratom nedokončenej úlohy do queue,
- stránka Workers s online/offline stavom a copy-paste inštaláciou pre vzdialený Linux,
- reálny `process`, `builtin`, `podman` a `managed-ai` executor v samostatnom worker programe,
- MCP server registry, Streamable HTTP/stdio executor a MCP agent naviazaný na konkrétny tool,
- CrewAI tím ako LangGraph node: editor členov a úloh, sekvenčný/hierarchický proces, štruktúrovaný výstup a task eventy,
- samostatný neprivilegovaný CrewAI worker image pre Podman a voliteľný Kubernetes Helm Deployment,
- OpenRC a systemd service šablóny.

## Deployment agentov

- **AI agent / managed runtime:** platforma spustí spoločný runner, ktorý pošle prompt a vstup do Ollama alebo OpenAI-compatible API. Zmena promptu nevyžaduje nový image.
- **Script agent / managed runtime:** Python, Node alebo Bash script beží v pripravenom runner image s kontraktom `input.json` → `output.json`.
- **Custom OCI image:** agent môže byť vlastný Podman/Docker image a beží izolovane lokálne alebo ako Kubernetes/OpenShift Job.

Budúci build/deploy modul je oddelený od orchestration enginu. Lokálne bude používať Podman/Buildah; v Kubernetes rootless BuildKit alebo Buildah Job, push do konfigurovanej OCI registry a nasadenie cez Helm. Nevyžaduje privilegovaný Docker-in-Docker ani Docker socket. CrewAI tím je vnorený ako jeden runtime node v LangGraph pipeline bez straty pomenovaných vstupov, výstupov a izolovaného stavu. Podrobný návod je v [docs/crewai.md](docs/crewai.md).

## Pipeline engine

Nové pipeline používajú `engine: langgraph`. Agent Forge graf sa preloží na skutočný LangGraph `StateGraph`; každý externý node vytvorí perzistentný interrupt a iba aktuálny frontier dostane WorkerJob. Výsledok workera resumuje konkrétny interrupt, zapíše výstup pod ID nodu a otvorí ďalšie pripravené vetvy. Checkpointy používajú PostgreSQL v kontajnerovom nasadení a samostatnú SQLite databázu pri lokálnom vývoji.

Pipeline možno dočasne prepnúť na `engine: legacy`. Existujúce databázy dostanú pri migrácii pre staré pipeline hodnotu `legacy`; nové a upravené pipeline možno v editore vedome prepnúť na LangGraph. Legacy odstránime až po produkčnom overení behov.

## Input/output kontrakty

Agent môže deklarovať viacero pomenovaných hodnôt, napríklad:

```text
inputs:
  document: string (required)
  metadata: json

outputs:
  summary: string
  score: number
```

Pipeline neodovzdáva celý anonymný blob. Hrana grafu obsahuje konkrétne mapovanie, napríklad `extract.summary → review.document`. Trigger output porty definujú vstupy celej pipeline a vstupné porty Output node definujú výsledky celej pipeline.

Graf je DAG. Po dokončení spoločného predchodcu scheduler uvoľní všetky pripravené vetvy naraz. Jeden výstup, napríklad `translate.slovak`, môže smerovať do ľubovoľného počtu nodes. Join čaká iba na svojich priamych predchodcov. Každý cieľový vstup má najviac jeden zdroj, takže paralelné vetvy sa navzájom neprepisujú.

Agent sa dá spustiť cez **Agenti → Testovať v pipeline**. Platforma pripraví `Manual trigger → Agent → Pipeline output`; tlačidlo **Uložiť a spustiť** vytvorí run a výsledok je v **Spustenia → posledný run → Output**. Spodný/horný bod node je FLOW poradie, bočné body sú dátové mapovania.

## MCP servery a agenti

1. Ako root otvor **MCP servery → Pridať MCP server**.
2. Pre vzdialenú službu zadaj celý Streamable HTTP endpoint, napríklad `http://host.containers.internal:3000/mcp`, a voliteľný Bearer token. **Connect & sync** vykoná MCP handshake a načíta skutočné tools.
3. Pre lokálny MCP proces zadaj bezpečné JSON pole argumentov pre stdio. Proces sa spustí až na workerovi.
4. V **Agenti → Nový agent → MCP agent** vyber server a konkrétny tool. Objavená input/output schéma sa prenesie do pomenovaných portov agenta.
5. MCP agenta vlož do pipeline rovnako ako AI alebo script agenta. `structuredContent` zostáva štruktúrovaným výstupom pre ďalšie nodes.

Worker musí mať executor `mcp`. Po aktualizácii existujúceho workera na verziu 0.5 ho znovu zaregistruj s `--executors process,builtin,podman,managed-ai,mcp`. Nedostupný endpoint, protocol error alebo timeout zmení MCP server na `error` a pipeline krok na `failed`; tool-level `isError` zlyhá krok, ale služba zostane `online`. Detailný návrh je v [docs/mcp-architecture.md](docs/mcp-architecture.md).

## Pripojenie Ollama

V `Providery a modely` vyber Ollama, zadaj IP/hostname a port (štandardne `11434`) a klikni na **Overiť spojenie**. Platforma zavolá Ollama `/api/tags` a zobrazí iba reálne nainštalované modely.

Pri kontajnerovom spustení a Ollame na tom istom Linux hoste použi `host.containers.internal:11434`. Ollama musí počúvať aj mimo loopbacku, napríklad cez `OLLAMA_HOST=0.0.0.0:11434`.

## Lokálne spustenie

```bash
cp .env.example .env
podman compose up --build
```

Web: `http://localhost:8080`
OpenAPI: `http://localhost:8000/docs`

Prvý zaregistrovaný používateľ sa stane root administrátorom. Pred reálnym nasadením zmeň všetky hodnoty v `.env`.

## Pripojenie workera

Po prihlásení otvor **Workers → Pridať worker**. Platforma vygeneruje jednorazový token a príkazy pripravené na skopírovanie do ľubovoľného Linux stroja. Worker nepotrebuje Uvicorn ani otvorený port; cez HTTPS posiela heartbeat, preberá úlohy a vracia logy a výsledky. Kompletný návod je v [docs/workers.md](docs/workers.md).

## Vývoj frontendu

```bash
cd frontend
npm install
npm run dev
```

## Vývoj API

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

## Ďalšia etapa

- Alembic migrácie namiesto bootstrap `create_all`,
- úprava existujúceho providera a rotácia API kľúča,
- group ACL enforcement,
- scheduler s databázovým leader lockom,
- Kubernetes/OpenShift Job executor (lokálny process, Podman a managed AI worker už sú implementované),
- artifact upload do MinIO/S3,
- editor konkrétnych user/group ACL oprávnení vo frontende.
