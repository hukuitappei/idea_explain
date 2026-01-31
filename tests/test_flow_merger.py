from core.flow_merger import FlowMerger
from core.schemas import Node, Edge, Flowchart


def test_merge_partial_change_updates_selected_nodes_and_protects_start_end():
    original = Flowchart(
        nodes=[
            Node(id="start", label="開始", type="start"),
            Node(id="a", label="旧A", type="process"),
            Node(id="node_end", label="終了", type="end"),
        ],
        edges=[
            Edge(source="start", target="a"),
            Edge(source="a", target="node_end"),
        ],
        subgraphs=None,
    )

    changed_partial = Flowchart(
        nodes=[
            Node(id="start", label="改竄", type="start"),  # should be ignored
            Node(id="a", label="新A", type="process"),
            Node(id="b", label="B", type="process"),
            Node(id="node_end", label="改竄", type="end"),  # should be ignored
        ],
        edges=[
            Edge(source="start", target="a", label="更新ラベル"),  # allowed (target selected)
            Edge(source="a", target="b"),
            Edge(source="b", target="node_end"),
        ],
        subgraphs=None,
    )

    merged = FlowMerger.merge_partial_change(original, changed_partial, selected_node_ids=["a", "b"])

    # start/end protected
    start = next(n for n in merged.nodes if n.id == "start")
    end = next(n for n in merged.nodes if n.id == "node_end")
    assert start.label == "開始"
    assert end.label == "終了"

    # selected updated / added
    a = next(n for n in merged.nodes if n.id == "a")
    b = next(n for n in merged.nodes if n.id == "b")
    assert a.label == "新A"
    assert b.label == "B"

    # edge update / additions
    assert {(e.source, e.target) for e in merged.edges} == {
        ("start", "a"),
        ("a", "node_end"),
        ("a", "b"),
        ("b", "node_end"),
    }
    updated = next(e for e in merged.edges if (e.source, e.target) == ("start", "a"))
    assert updated.label == "更新ラベル"

