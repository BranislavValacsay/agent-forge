# MCP integration architecture

## Scope and execution model

Agent Forge treats an MCP server as infrastructure and an MCP agent as a deterministic adapter for one selected MCP tool. A pipeline node never calls an arbitrary server or tool name supplied at run time. The server and tool are selected when the agent is created, while the tool arguments arrive through the node's named input ports.

Version 1 supports the MCP 2025-11-25 lifecycle and both standard transports:

- `streamable-http`: remote MCP endpoint reachable from a worker;
- `stdio`: a command launched by the worker as an argument array, never through a shell.

Dynamic LLM tool selection is deliberately separate from this deterministic MCP agent. It can later be added as an AI agent with an allow-list of MCP tools without changing the pipeline data contract.

## Components

1. **MCP Server Registry** stores identity, transport configuration, ACL ownership, health, negotiated protocol metadata and the last discovered tool catalog.
2. **Encrypted MCP Secret** stores HTTP authorization headers or stdio environment variables separately from public server metadata.
3. **MCP Agent** references one registry server and one case-sensitive tool name. Its input and output schemas are copied into the agent version, so a later `tools/list` change cannot silently alter an existing pipeline.
4. **MCP Worker Executor** owns the full MCP session: `initialize`, `notifications/initialized`, `tools/call`, result normalization and shutdown.
5. **Run/Event layer** records the server, tool, transport, timing, protocol error or tool execution error without recording secrets.

## Data model

`mcp_servers` contains:

- `name`, `slug`, `description`, `owner_id`, `visibility`;
- `transport`: `streamable-http` or `stdio`;
- HTTP `endpoint`, or stdio `command` as a JSON argument array;
- `status`: `unknown`, `online`, `error`, `disabled`;
- `status_message`, `protocol_version`, `server_info`, `capabilities`;
- `tools_snapshot`, `last_checked_at`, timestamps.

`mcp_server_secrets` contains one encrypted JSON document per server. API responses expose only `has_secret`, never the secret value.

`agents` gains `kind=mcp`, `mcp_server_id` and `mcp_tool_name`. The agent's existing `input_schema` and `output_schema` remain the canonical pipeline contract.

## Lifecycle

### Registration and discovery

For Streamable HTTP, **Connect and synchronize** performs initialization, sends the initialized notification, follows all `tools/list` pages and stores the discovered catalog. Success changes health to `online`; timeout, authentication, protocol or network failure changes it to `error` with a safe diagnostic.

For stdio, discovery happens on the execution worker because the command and its dependencies belong to that machine. A tool may be configured manually before the first run; the first execution establishes real health.

### Pipeline execution

1. DAG scheduler leases the node only to a worker advertising the `mcp` executor.
2. Server and encrypted connection configuration are placed only into that leased job.
3. Worker initializes a fresh MCP session and invokes the fixed tool with the node's named input object.
4. `structuredContent` is preferred. If it matches named agent outputs, keys remain unchanged. Otherwise a single output port receives the structured result or the complete MCP content envelope.
5. JSON-RPC errors, timeout, unavailable service and `isError: true` fail the step and therefore the run. They never leave it queued indefinitely.
6. Completion updates registry health and emits auditable `mcp.call.*` run events.

Parallel calls use independent MCP sessions and independent result objects. They cannot overwrite one another; ordinary DAG named-port rules still apply.

## Failure and state semantics

| Condition | Server state | Pipeline step |
| --- | --- | --- |
| Discovery/call succeeds | `online` | `succeeded` |
| DNS/connect/HTTP timeout | `error` | `failed` |
| Authentication rejected | `error` | `failed` |
| Protocol/version/JSON-RPC error | `error` | `failed` |
| Tool returns `isError: true` | `online` | `failed` |
| Server disabled | `disabled` | rejected/failed before execution |
| No compatible MCP worker | unchanged | `queued`, with explicit required executor |

Tool errors do not mark the service offline because the transport and server remain healthy. Transport/protocol failures do.

## Security boundaries

- Only root manages MCP infrastructure in the first implementation; authenticated users can use servers through agent/pipeline ACL.
- HTTP URLs allow only `http`/`https`, reject embedded credentials and apply explicit timeouts. Private addresses remain allowed because on-premise MCP is a core use case.
- HTTP secrets and stdio environment variables are encrypted at rest and redacted from API, logs and events.
- Stdio commands are argument arrays and use `shell=False`; the worker process account remains the OS security boundary.
- Tool names are fixed by the agent, inputs are schema-bound, calls are audited and results are size-limited by the existing job/event channel.
- Sensitive or destructive tools should later gain per-call approval policy; tool annotations are treated as untrusted metadata.

## Compatibility and future work

- Current transport is Streamable HTTP; deprecated HTTP+SSE is not auto-detected.
- MCP tasks, sampling, elicitation, roots, prompts and resources are outside the first executor scope.
- Future additions: OAuth discovery/refresh, worker-label affinity for stdio commands, health scheduler, list-changed subscriptions, artifact offload and human approval policies.
