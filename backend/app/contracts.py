from copy import deepcopy
from typing import Any


SCALAR_TYPES = {"string", "number", "boolean", "json", "file", "image", "any"}


def value_at(payload: dict[str, Any], path: str) -> Any:
    """Resolve a dotted result path, e.g. `article.title`."""
    value: Any = payload
    for segment in path.split("."):
        if not isinstance(value, dict) or segment not in value:
            raise KeyError(f"Value path '{path}' does not exist")
        value = value[segment]
    return value


def assign_at(payload: dict[str, Any], path: str, value: Any) -> None:
    """Assign a value to a dotted input path, creating intermediate objects."""
    target = payload
    segments = path.split(".")
    for segment in segments[:-1]:
        child = target.get(segment)
        if not isinstance(child, dict):
            child = {}
            target[segment] = child
        target = child
    target[segments[-1]] = value


def apply_mappings(
    source_output: dict[str, Any],
    current_input: dict[str, Any],
    mappings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Map named upstream results into named downstream inputs."""
    result = deepcopy(current_input)
    for mapping in mappings:
        assign_at(result, mapping["target"], value_at(source_output, mapping["source"]))
    return result


def types_compatible(source: str, target: str) -> bool:
    return source == target or source == "any" or target == "any"


def edge_mapping(edge: dict[str, Any]) -> dict[str, Any]:
    """Return canonical named mapping; connected handles override stale UI metadata."""
    mapping = dict(((edge.get("data") or {}).get("mapping") or {}))
    source_handle = edge.get("sourceHandle")
    target_handle = edge.get("targetHandle")
    if isinstance(source_handle, str) and source_handle.startswith("out:"):
        mapping["source"] = source_handle[4:]
    if isinstance(target_handle, str) and target_handle.startswith("in:"):
        mapping["target"] = target_handle[3:]
    return mapping


def graph_predecessors(graph: dict[str, Any], node_id: str) -> set[str]:
    """Return direct DAG dependencies from both control and value edges."""
    return {
        edge["source"]
        for edge in graph.get("edges", [])
        if edge.get("target") == node_id
        and isinstance(edge.get("source"), str)
        and edge.get("source") != node_id
    }


def validate_graph(graph: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    nodes = {node.get("id"): node for node in graph.get("nodes", [])}
    edges = graph.get("edges", [])
    if not nodes:
        errors.append("Pipeline has no nodes")
        return errors, warnings
    dependencies: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    mapped_targets: dict[tuple[str, str], str] = {}
    for edge in edges:
        source = nodes.get(edge.get("source"))
        target = nodes.get(edge.get("target"))
        if not source or not target:
            errors.append(f"Edge {edge.get('id', '?')} references a missing node")
            continue
        if edge.get("source") == edge.get("target"):
            errors.append(f"Edge {edge.get('id', '?')} creates a self-cycle")
            continue
        dependencies[edge["target"]].add(edge["source"])
        edge_data = edge.get("data") or {}
        if edge_data.get("kind") == "control":
            continue
        mapping = edge_mapping(edge)
        if not mapping:
            errors.append(f"Edge {edge.get('id', '?')} has no value mapping")
            continue
        source_ports = {port.get("name"): port for port in (source.get("data") or {}).get("outputs", [])}
        target_ports = {port.get("name"): port for port in (target.get("data") or {}).get("inputs", [])}
        if mapping.get("source") not in source_ports:
            errors.append(f"Mapping source '{mapping.get('source')}' does not exist on {(source.get('data') or {}).get('label', edge.get('source'))}")
            continue
        if mapping.get("target") not in target_ports:
            errors.append(f"Mapping target '{mapping.get('target')}' does not exist on {(target.get('data') or {}).get('label', edge.get('target'))}")
            continue
        target_key = (edge["target"], mapping["target"])
        previous_source = mapped_targets.get(target_key)
        if previous_source is not None:
            errors.append(
                f"Input '{mapping['target']}' on {(target.get('data') or {}).get('label', edge['target'])} "
                f"has multiple sources ({previous_source}, {mapping['source']})"
            )
            continue
        mapped_targets[target_key] = mapping["source"]
        mapping["sourceType"] = source_ports[mapping["source"]].get("type", mapping.get("sourceType", "any"))
        mapping["targetType"] = target_ports[mapping["target"]].get("type", mapping.get("targetType", "any"))
        if not types_compatible(mapping.get("sourceType", "any"), mapping.get("targetType", "any")):
            errors.append(
                f"Incompatible mapping {mapping.get('source')} ({mapping.get('sourceType')}) "
                f"→ {mapping.get('target')} ({mapping.get('targetType')})"
            )
    # Kahn's algorithm: branches are valid, but every dependency graph must be acyclic.
    indegree = {node_id: len(predecessors) for node_id, predecessors in dependencies.items()}
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    for target_id, predecessors in dependencies.items():
        for source_id in predecessors:
            outgoing[source_id].add(target_id)
    ready = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited = 0
    while ready:
        source_id = ready.pop()
        visited += 1
        for target_id in outgoing[source_id]:
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                ready.append(target_id)
    if visited != len(nodes):
        errors.append("Pipeline graph contains a cycle; only directed acyclic branches are supported")
    for node_id, node in nodes.items():
        data = node.get("data") or {}
        for port in data.get("inputs", []):
            if port.get("required") and not any(
                edge.get("target") == node_id
                and ((edge.get("data") or {}).get("kind") != "control")
                and edge_mapping(edge).get("target") == port.get("name")
                for edge in edges
            ):
                errors.append(f"{data.get('label', node_id)} is missing required input '{port.get('name')}'")
        if data.get("nodeKind") == "agent" and not data.get("agentId"):
            errors.append(f"{data.get('label', node_id)} has no agent assigned")
    if not any((node.get("data") or {}).get("nodeKind") == "trigger" for node in nodes.values()):
        warnings.append("Pipeline has no trigger node")
    if not any((node.get("data") or {}).get("nodeKind") == "output" for node in nodes.values()):
        warnings.append("Pipeline has no output node")
    return errors, warnings
