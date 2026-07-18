from app.contracts import apply_mappings, edge_mapping, graph_predecessors, types_compatible, validate_graph


def test_named_value_mapping() -> None:
    output = {"summary": "hello", "stats": {"score": 0.9}}
    mapped = apply_mappings(
        output,
        {"existing": True},
        [
            {"source": "summary", "target": "document"},
            {"source": "stats.score", "target": "metadata.score"},
        ],
    )
    assert mapped == {"existing": True, "document": "hello", "metadata": {"score": 0.9}}


def test_type_compatibility() -> None:
    assert types_compatible("string", "string")
    assert types_compatible("json", "any")
    assert not types_compatible("string", "number")


def test_required_input_validation() -> None:
    graph = {
        "nodes": [{"id": "agent", "data": {"nodeKind": "agent", "label": "Agent", "agentId": "1", "inputs": [{"name": "text", "type": "string", "required": True}]}}],
        "edges": [],
    }
    errors, _ = validate_graph(graph)
    assert "Agent is missing required input 'text'" in errors


def test_control_flow_edge_does_not_require_value_mapping() -> None:
    graph = {
        "nodes": [
            {"id": "a", "data": {"nodeKind": "trigger", "label": "Start", "inputs": []}},
            {"id": "b", "data": {"nodeKind": "agent", "label": "Agent", "agentId": "1", "inputs": []}},
        ],
        "edges": [{"id": "flow", "source": "a", "target": "b", "data": {"kind": "control"}}],
    }
    errors, _ = validate_graph(graph)
    assert errors == []


def test_connected_handles_override_stale_mapping_metadata() -> None:
    edge = {
        "source": "first",
        "target": "second",
        "sourceHandle": "out:tema",
        "targetHandle": "in:tema",
        "data": {"kind": "value", "mapping": {"source": "result", "target": "old_input", "sourceType": "json", "targetType": "string"}},
    }
    assert edge_mapping(edge)["source"] == "tema"
    assert edge_mapping(edge)["target"] == "tema"
    graph = {
        "nodes": [
            {"id": "first", "data": {"nodeKind": "agent", "label": "First", "agentId": "1", "inputs": [], "outputs": [{"name": "result", "type": "json"}, {"name": "tema", "type": "string"}]}},
            {"id": "second", "data": {"nodeKind": "agent", "label": "Second", "agentId": "2", "inputs": [{"name": "tema", "type": "string", "required": True}], "outputs": []}},
        ],
        "edges": [edge],
    }
    errors, _ = validate_graph(graph)
    assert errors == []


def test_fan_out_is_valid_and_dependencies_are_deduplicated() -> None:
    graph = {
        "nodes": [
            {"id": "source", "data": {"nodeKind": "agent", "label": "Translator", "agentId": "1", "inputs": [], "outputs": [{"name": "sk", "type": "string"}]}},
            {"id": "left", "data": {"nodeKind": "agent", "label": "Left", "agentId": "2", "inputs": [{"name": "text", "type": "string", "required": True}], "outputs": []}},
            {"id": "right", "data": {"nodeKind": "agent", "label": "Right", "agentId": "3", "inputs": [{"name": "article", "type": "string", "required": True}], "outputs": []}},
        ],
        "edges": [
            {"source": "source", "target": "left", "sourceHandle": "out:sk", "targetHandle": "in:text", "data": {"kind": "value"}},
            {"source": "source", "target": "right", "sourceHandle": "out:sk", "targetHandle": "in:article", "data": {"kind": "value"}},
            {"source": "source", "target": "right", "data": {"kind": "control"}},
        ],
    }
    errors, _ = validate_graph(graph)
    assert errors == []
    assert graph_predecessors(graph, "right") == {"source"}


def test_multiple_named_outputs_can_route_independently() -> None:
    graph = {
        "nodes": [
            {"id": "source", "data": {"nodeKind": "agent", "label": "Source", "agentId": "1", "inputs": [], "outputs": [{"name": "third", "type": "string"}, {"name": "fourth", "type": "string"}]}},
            {"id": "a", "data": {"nodeKind": "agent", "label": "A", "agentId": "2", "inputs": [{"name": "value", "type": "string", "required": True}], "outputs": []}},
            {"id": "b", "data": {"nodeKind": "agent", "label": "B", "agentId": "3", "inputs": [{"name": "value", "type": "string", "required": True}], "outputs": []}},
        ],
        "edges": [
            {"source": "source", "target": "a", "sourceHandle": "out:third", "targetHandle": "in:value", "data": {"kind": "value"}},
            {"source": "source", "target": "b", "sourceHandle": "out:fourth", "targetHandle": "in:value", "data": {"kind": "value"}},
        ],
    }
    assert validate_graph(graph)[0] == []


def test_cycle_and_multiple_writers_are_rejected() -> None:
    graph = {
        "nodes": [
            {"id": "a", "data": {"nodeKind": "agent", "label": "A", "agentId": "1", "inputs": [{"name": "in", "type": "string"}], "outputs": [{"name": "out", "type": "string"}]}},
            {"id": "b", "data": {"nodeKind": "agent", "label": "B", "agentId": "2", "inputs": [{"name": "in", "type": "string"}], "outputs": [{"name": "out", "type": "string"}]}},
            {"id": "c", "data": {"nodeKind": "agent", "label": "C", "agentId": "3", "inputs": [{"name": "in", "type": "string"}], "outputs": [{"name": "out", "type": "string"}]}},
        ],
        "edges": [
            {"source": "a", "target": "b", "sourceHandle": "out:out", "targetHandle": "in:in", "data": {"kind": "value"}},
            {"source": "b", "target": "a", "data": {"kind": "control"}},
            {"source": "c", "target": "b", "sourceHandle": "out:out", "targetHandle": "in:in", "data": {"kind": "value"}},
        ],
    }
    errors, _ = validate_graph(graph)
    assert any("cycle" in error for error in errors)
    assert any("multiple sources" in error for error in errors)
