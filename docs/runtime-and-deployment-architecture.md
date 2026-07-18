# Runtime and deployment architecture

## Stable boundary

LangGraph is the pipeline orchestration and state engine. It owns graph order,
parallel frontiers, joins, durable checkpoints and named state transfer. It does
not build images and it does not execute arbitrary user code inside the API.

Every executable node crosses one stable contract:

```text
Node interrupt
  -> node_id + named JSON input + runtime reference
WorkerJob
  -> executor + CPU/GPU requirement + immutable configuration
Node resume
  -> named JSON output or structured error
```

This boundary allows these runtimes to coexist:

- managed AI, script, MCP, Podman and Kubernetes jobs,
- CrewAI team embedded as one LangGraph node,
- a future nested LangGraph subgraph,
- a deployed immutable OCI agent reached through a service endpoint.

CrewAI internal task state stays inside its node namespace. Memory, cache and
CrewAI checkpointing are disabled; LangGraph is the only durable state owner.
Only declared output ports are merged into the parent LangGraph state. This
prevents parallel teams and branches from overwriting each other.

## OCI build pipeline

Image building is a separate executor, not part of LangGraph itself:

1. resolve an immutable agent version and source bundle,
2. generate or validate Containerfile and runtime contract,
3. build with local Podman/Buildah or a Kubernetes rootless BuildKit/Buildah Job,
4. push the digest to a configured OCI registry,
5. sign and record image digest, SBOM and provenance,
6. deploy the immutable digest through Helm.

Classic privileged Docker-in-Docker and host Docker socket mounts are excluded.
Registry credentials are encrypted control-plane secrets and are exposed only to
the short-lived build Job.

## Kubernetes and Podman targets

The deployment adapter accepts the same desired state for both targets:

```yaml
runtime: service | job
image: registry.example/agents/name@sha256:...
resources:
  workerClass: cpu | gpu
  cpu: "1"
  memory: 1Gi
ports: []
health: {}
environmentSecretRefs: []
```

- Podman applies it as a rootless container or pod.
- Kubernetes applies it as a Job or Deployment through Helm.
- OpenShift may add Route/SCC integration, but is not required by the contract.

The existing Agent Forge Helm chart deploys the control plane on standard
Kubernetes with Ingress. OpenShift Route remains an optional switch.
