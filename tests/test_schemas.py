"""FlowchartとNode/Edgeのユニットテスト"""
import pytest
from core.schemas import Node, Edge, Flowchart, NodeStatus
from core.exceptions import FlowchartValidationError


class TestNode:
    def test_node_creation(self):
        node = Node(id="test1", label="テスト", type="process")
        assert node.id == "test1"
        assert node.label == "テスト"
        assert node.type == "process"
        assert node.status == NodeStatus.ACTIVE

    def test_node_with_status(self):
        node = Node(id="test2", label="テスト", type="process", status=NodeStatus.COMPLETED)
        assert node.status == NodeStatus.COMPLETED


class TestEdge:
    def test_edge_creation(self):
        edge = Edge(source="node1", target="node2")
        assert edge.source == "node1"
        assert edge.target == "node2"
        assert edge.label is None

    def test_edge_with_label(self):
        edge = Edge(source="node1", target="node2", label="Yes")
        assert edge.label == "Yes"


class TestFlowchart:
    def test_valid_flowchart(self):
        nodes = [
            Node(id="start", label="開始", type="start"),
            Node(id="process1", label="処理", type="process"),
            Node(id="node_end", label="終了", type="end")
        ]
        edges = [
            Edge(source="start", target="process1"),
            Edge(source="process1", target="node_end")
        ]
        flowchart = Flowchart(nodes=nodes, edges=edges)
        assert len(flowchart.nodes) == 3
        assert len(flowchart.edges) == 2

    def test_missing_start_node(self):
        nodes = [
            Node(id="process1", label="処理", type="process"),
            Node(id="node_end", label="終了", type="end")
        ]
        edges = [Edge(source="process1", target="node_end")]
        with pytest.raises(FlowchartValidationError, match="開始/終了ノードが必要です"):
            Flowchart(nodes=nodes, edges=edges)

    def test_missing_end_node(self):
        nodes = [
            Node(id="start", label="開始", type="start"),
            Node(id="process1", label="処理", type="process")
        ]
        edges = [Edge(source="start", target="process1")]
        with pytest.raises(FlowchartValidationError, match="開始/終了ノードが必要です"):
            Flowchart(nodes=nodes, edges=edges)

    def test_duplicate_node_ids(self):
        nodes = [
            Node(id="start", label="開始", type="start"),
            Node(id="process1", label="処理1", type="process"),
            Node(id="process1", label="処理2", type="process"),  # 重複
            Node(id="node_end", label="終了", type="end")
        ]
        edges = [Edge(source="start", target="process1")]
        with pytest.raises(FlowchartValidationError, match="ノードIDが重複しています"):
            Flowchart(nodes=nodes, edges=edges)

    def test_invalid_node_type(self):
        nodes = [
            Node(id="start", label="開始", type="start"),
            Node(id="process1", label="処理", type="invalid_type"),
            Node(id="node_end", label="終了", type="end")
        ]
        edges = [Edge(source="start", target="process1")]
        with pytest.raises(FlowchartValidationError, match="無効なノードタイプ"):
            Flowchart(nodes=nodes, edges=edges)

    def test_invalid_edge_source(self):
        # バリデーション緩和により、エッジの無効性は警告のみ（例外は投げない）
        # 論理の穴検知で自動修正される
        nodes = [
            Node(id="start", label="開始", type="start"),
            Node(id="node_end", label="終了", type="end")
        ]
        edges = [Edge(source="nonexistent", target="node_end")]
        flowchart = Flowchart(nodes=nodes, edges=edges)
        # 警告は出るが、Flowchartオブジェクトは作成される
        assert len(flowchart.nodes) == 2
        assert len(flowchart.edges) == 1

    def test_invalid_edge_target(self):
        # バリデーション緩和により、エッジの無効性は警告のみ（例外は投げない）
        # 論理の穴検知で自動修正される
        nodes = [
            Node(id="start", label="開始", type="start"),
            Node(id="node_end", label="終了", type="end")
        ]
        edges = [Edge(source="start", target="nonexistent")]
        flowchart = Flowchart(nodes=nodes, edges=edges)
        # 警告は出るが、Flowchartオブジェクトは作成される
        assert len(flowchart.nodes) == 2
        assert len(flowchart.edges) == 1

    def test_detect_logic_gaps_decision_no_outgoing(self):
        nodes = [
            Node(id="start", label="開始", type="start"),
            Node(id="decision1", label="判定", type="decision"),
            Node(id="node_end", label="終了", type="end")
        ]
        edges = [
            Edge(source="start", target="decision1")
            # decision1から出口がない
        ]
        flowchart = Flowchart(nodes=nodes, edges=edges)
        gaps = flowchart.detect_logic_gaps()
        assert len(gaps) == 1
        assert gaps[0].id == "decision1"

    def test_detect_logic_gaps_missing_target(self):
        nodes = [
            Node(id="start", label="開始", type="start"),
            Node(id="process1", label="処理", type="process"),
            Node(id="node_end", label="終了", type="end")
        ]
        edges = [
            Edge(source="start", target="process1"),
            Edge(source="process1", target="missing_node")  # 存在しないノード
        ]
        flowchart = Flowchart(nodes=nodes, edges=edges)
        gaps = flowchart.detect_logic_gaps()
        assert len(gaps) == 1
        assert gaps[0].id == "missing_missing_node"
        assert gaps[0].type == "missing"

    def test_to_mermaid(self):
        nodes = [
            Node(id="start", label="開始", type="start"),
            Node(id="process1", label="処理", type="process"),
            Node(id="node_end", label="終了", type="end")
        ]
        edges = [
            Edge(source="start", target="process1"),
            Edge(source="process1", target="node_end")
        ]
        flowchart = Flowchart(nodes=nodes, edges=edges)
        mermaid = flowchart.to_mermaid()
        assert "graph TD" in mermaid
        assert 'start["開始"]' in mermaid
        assert 'process1["処理"]' in mermaid
        assert 'start-->process1' in mermaid

    def test_to_toon_format(self):
        nodes = [
            Node(id="start", label="開始", type="start"),
            Node(id="node_end", label="終了", type="end")
        ]
        edges = [Edge(source="start", target="node_end")]
        flowchart = Flowchart(nodes=nodes, edges=edges)
        toon = flowchart.to_toon_format()
        assert "[Node]" in toon
        assert "id: start" in toon
        assert "[Edge]" in toon
        assert "source: start" in toon
