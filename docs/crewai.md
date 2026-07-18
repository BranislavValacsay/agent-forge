# CrewAI v LangGraph pipeline

LangGraph zostáva jediným vlastníkom pipeline grafu, pomenovaného stavu,
checkpointov, paralelných vetiev, retry a histórie behov. CrewAI tím je jeden
vykonateľný LangGraph node. Jeho interní členovia a úlohy dostanú vstup node a
posledná úloha vytvorí presne pomenovaný výstup node.

CrewAI `Flow` ani CrewAI checkpointing sa nepoužívajú. Pamäť a cache sú vypnuté,
aby nevznikli dva zdroje pravdy. Retry CrewAI node preto bezpečne zopakuje celý
tím. Na jednom worker procese sa CrewAI joby vykonávajú sériovo; nezávislé nodes
môžu súčasne bežať na ďalších workeroch.

## Vytvorenie CrewAI agenta

1. V **Providery a modely** pripoj Ollama alebo OpenAI-compatible API.
2. V **Agenti → Nový agent → CrewAI tím** vyber provider a model.
3. Pridaj členov s rolou, cieľom a backstory.
4. Pridaj zoradené úlohy a každej priraď člena. V texte možno použiť pomenované
   vstupy, napríklad `{tema}`.
5. Definuj vstupné a výstupné porty. Posledná úloha je automaticky viazaná na
   dynamický Pydantic model výstupných portov.
6. Vlož tím do LangGraph pipeline ako bežný node.

Každé dokončenie internej CrewAI úlohy sa zapíše ako worker event. Celý prompt,
credential ani neobmedzený interný stav sa do parent pipeline nemergujú.

## CrewAI worker cez Podman

```bash
podman build -f backend/Dockerfile.crewai-worker \
  -t localhost/agent-forge-crewai-worker:0.6.0 backend

# Worker skript možno stiahnuť cez GUI návod. Registrácia CrewAI knižnicu nepotrebuje.
agent-forge-worker --config ./crewai-worker-config.json register \
  --url https://forge.example.sk \
  --token TOKEN_Z_GUI \
  --name crewai-worker \
  --class universal \
  --executors crewai

podman volume create agent-forge-crewai-config
podman run --rm --user 0 --entrypoint sh \
  -v agent-forge-crewai-config:/config:Z \
  -v "$PWD/crewai-worker-config.json:/source/config.json:ro,Z" \
  localhost/agent-forge-crewai-worker:0.6.0 \
  -c 'cp /source/config.json /config/config.json && chown 10001:0 /config/config.json && chmod 600 /config/config.json'

podman run -d --name agent-forge-crewai-worker --restart=always \
  -v agent-forge-crewai-config:/config:Z \
  localhost/agent-forge-crewai-worker:0.6.0 run --concurrency 1
```

Ak API beží na tom istom hoste v inom kontajneri, registračná URL musí byť z
workera dostupná, napríklad `http://host.containers.internal:8080`.

## CrewAI worker v Kubernetes

Najprv vytvor konfiguráciu registráciou proti URL dostupnej z clusteru a ulož ju
ako Secret:

```bash
kubectl create secret generic agent-forge-crewai-worker \
  --from-file=config.json=./crewai-worker-config.json

helm upgrade --install forge deploy/helm/agent-forge \
  --set crewaiWorker.enabled=true \
  --set crewaiWorker.image=registry.example/agent-forge-crewai-worker:0.6.0 \
  --set crewaiWorker.configSecretName=agent-forge-crewai-worker
```

Deployment je neprivilegovaný, používa read-only root filesystem a zapisovateľné
`emptyDir` iba pre HOME a `/tmp`. Nepotrebuje Docker socket ani Kubernetes RBAC.
