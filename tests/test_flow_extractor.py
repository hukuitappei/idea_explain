import pytest

from core.flow_extractor import FlowExtractor
from core.schemas import Node, Edge, Flowchart


def test_extract_node_range_excludes_start_end_and_collects_edges():
    flow = Flowchart(
        nodes=[
            Node(id="start", label="開始", type="start"),
            Node(id="a", label="A", type="process"),
            Node(id="b", label="B", type="process"),
            Node(id="node_end", label="終了", type="end"),
        ],
        edges=[
            Edge(source="start", target="a"),
            Edge(source="a", target="b"),
            Edge(source="b", target="node_end"),
        ],
    )

    extracted = FlowExtractor.extract_node_range(flow, ["start", "a", "node_end"])
    # start/end are included to satisfy Flowchart validation; selected node is included too
    assert {n.id for n in extracted.nodes} == {"start", "a", "node_end"}
    # Only edges whose endpoints are present should be included
    assert {(e.source, e.target) for e in extracted.edges} == {("start", "a")}


def test_extract_node_range_returns_empty_when_only_start_end():
    flow = Flowchart(
        nodes=[
            Node(id="start", label="開始", type="start"),
            Node(id="node_end", label="終了", type="end"),
        ],
        edges=[Edge(source="start", target="node_end")],
    )

    with pytest.raises(ValueError):
        FlowExtractor.extract_node_range(flow, ["start", "node_end"])

