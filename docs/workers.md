# Agent Forge Worker

Worker je samostatný Linux proces. Komunikuje iba odchádzajúcim HTTPS spojením s Agent Forge API, takže nepotrebuje otvorený port ani verejnú IP adresu.

## Najjednoduchšia inštalácia

V Agent Forge otvor **Workers → Pridať worker**. GUI vytvorí jednorazový token a zobrazí kompletné príkazy. Na cieľovom stroji stačí Python 3.10+ a `curl`.

```bash
curl -fsSL https://forge.example.sk/api/v1/worker/install.sh \
  | AGENT_FORGE_URL=https://forge.example.sk sh

~/.local/bin/agent-forge-worker register \
  --url https://forge.example.sk \
  --token TOKEN_Z_GUI \
  --name gentoo-worker \
  --executors process,builtin,podman,managed-ai,mcp

~/.local/bin/agent-forge-worker run --concurrency 2
```

Konfigurácia s worker credentialom sa uloží do `~/.config/agent-forge-worker/config.json` s právami `0600`. Registračný token je jednorazový a štandardne platí 30 minút.

## Executory

| Executor | Použitie | Požiadavky |
| --- | --- | --- |
| `builtin` | Trigger, transform a pipeline output | Python 3 |
| `process` | Python, Bash alebo Node script priamo na OS | Príslušný interpreter |
| `podman` | Vlastný OCI image | Podman |
| `managed-ai` | AI agent volajúci Ollama/OpenAI-compatible API | Sieťový prístup k provideru |
| `mcp` | MCP tool cez Streamable HTTP alebo stdio | Sieťový prístup alebo lokálny MCP príkaz |
| `crewai` | Izolovaný CrewAI tím v jednom LangGraph node | CrewAI worker image a prístup k provideru |

Process agent dostane cesty cez `AF_INPUT_PATH` a `AF_OUTPUT_PATH`. JSON objekt môže zapísať do výstupného súboru, ale jednoduchý text alebo JSON zo `stdout` worker automaticky zabalí podľa deklarovaného výstupného portu. Process executor nie je kontajnerový sandbox; v produkcii ho spúšťaj pod samostatným systémovým používateľom.

## Paralelné vetvy

Worker 0.4+ štandardne vykonáva dve úlohy súbežne. Limit nastavíš cez `run --concurrency N`; pre GPU worker zvoľ hodnotu podľa VRAM, pokojne `1`. Viac workerov môže paralelne spracovať ďalšie pripravené vetvy. Control aj dátové hrany sú závislosti DAG: node sa sprístupní až po úspechu všetkých svojich priamych predchodcov.

## OpenRC

Uprav používateľa a cestu v `deploy/worker/openrc/agent-forge-worker`, potom:

```bash
sudo cp deploy/worker/openrc/agent-forge-worker /etc/init.d/
sudo chmod +x /etc/init.d/agent-forge-worker
sudo rc-update add agent-forge-worker default
sudo rc-service agent-forge-worker start
```

## systemd user service

```bash
mkdir -p ~/.config/systemd/user
cp deploy/worker/systemd/agent-forge-worker.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now agent-forge-worker
```

## Protokol

Worker posiela heartbeat každých 15 sekúnd, preberá iba úlohy kompatibilné so svojimi executormi a dostáva časovo obmedzený lease. Logovanie zároveň obnovuje lease. Po prerušení workera sa úloha po exspirácii lease vráti do queue.

CrewAI executor nie je súčasťou ľahkého stdlib workera. Použi pripravený
`backend/Dockerfile.crewai-worker` a registruj ho iba s executorom `crewai`.
Podman a Kubernetes návod je v [crewai.md](crewai.md).
