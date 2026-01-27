"""HistoryManagerのユニットテスト"""
import pytest
import tempfile
import shutil
from pathlib import Path
from core.history_mgr import HistoryManager
from core.schemas import Node, Edge, Flowchart


class TestHistoryManager:
    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリを作成"""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        shutil.rmtree(temp_path)

    @pytest.fixture
    def history_mgr(self, temp_dir):
        """HistoryManagerのインスタンスを作成"""
        return HistoryManager(
            storage_dir=str(temp_dir / "sessions"),
            toon_dir=str(temp_dir / "toon_files")
        )

    @pytest.fixture
    def sample_flowchart(self):
        """サンプルのFlowchartを作成"""
        return Flowchart(
            nodes=[
                Node(id="start", label="開始", type="start"),
                Node(id="process1", label="処理", type="process"),
                Node(id="node_end", label="終了", type="end")
            ],
            edges=[
                Edge(source="start", target="process1"),
                Edge(source="process1", target="node_end")
            ]
        )

    def test_save_and_load_session(self, history_mgr, sample_flowchart):
        session_id = "test_session"
        history = [sample_flowchart]
        
        history_mgr.save_session(session_id, history)
        loaded = history_mgr.load_session(session_id)
        
        assert len(loaded) == 1
        assert loaded[0].nodes[0].id == "start"

    def test_save_and_load_toon_file(self, history_mgr, sample_flowchart):
        session_id = "test_toon"
        
        history_mgr.save_toon_file(session_id, sample_flowchart)
        loaded = history_mgr.load_toon_file(session_id)
        
        assert loaded is not None
        assert len(loaded.nodes) == 3
        assert len(loaded.edges) == 2

    def test_load_nonexistent_session(self, history_mgr):
        loaded = history_mgr.load_session("nonexistent")
        assert loaded == []

    def test_load_nonexistent_toon_file(self, history_mgr):
        loaded = history_mgr.load_toon_file("nonexistent")
        assert loaded is None

    def test_list_toon_files(self, history_mgr, sample_flowchart):
        history_mgr.save_toon_file("file1", sample_flowchart)
        history_mgr.save_toon_file("file2", sample_flowchart)
        
        files = history_mgr.list_toon_files()
        assert "file1" in files
        assert "file2" in files

    def test_append_toon_log_new_file(self, history_mgr, sample_flowchart):
        session_id = "new_session"
        result = history_mgr.append_toon_log(session_id, sample_flowchart)
        
        assert result == sample_flowchart
        loaded = history_mgr.load_toon_file(session_id)
        assert loaded is not None

    def test_append_toon_log_update_node(self, history_mgr, sample_flowchart):
        session_id = "update_session"
        history_mgr.save_toon_file(session_id, sample_flowchart)
        
        # 既存ノードを更新
        updated_flowchart = Flowchart(
            nodes=[
                Node(id="start", label="開始（更新）", type="start"),
                Node(id="process1", label="処理", type="process"),
                Node(id="node_end", label="終了", type="end")
            ],
            edges=[
                Edge(source="start", target="process1"),
                Edge(source="process1", target="node_end")
            ]
        )
        
        result = history_mgr.append_toon_log(session_id, updated_flowchart)
        assert result.nodes[0].label == "開始（更新）"

    def test_append_toon_log_add_node(self, history_mgr, sample_flowchart):
        session_id = "add_node_session"
        history_mgr.save_toon_file(session_id, sample_flowchart)
        
        # 新しいノードを追加
        new_flowchart = Flowchart(
            nodes=[
                Node(id="start", label="開始", type="start"),
                Node(id="process1", label="処理", type="process"),
                Node(id="process2", label="処理2", type="process"),  # 新規
                Node(id="node_end", label="終了", type="end")
            ],
            edges=[
                Edge(source="start", target="process1"),
                Edge(source="process1", target="process2"),
                Edge(source="process2", target="node_end")
            ]
        )
        
        result = history_mgr.append_toon_log(session_id, new_flowchart)
        assert len(result.nodes) == 4
        assert any(node.id == "process2" for node in result.nodes)

    def test_append_toon_log_update_edge(self, history_mgr, sample_flowchart):
        session_id = "update_edge_session"
        history_mgr.save_toon_file(session_id, sample_flowchart)
        
        # エッジのラベルを更新
        updated_flowchart = Flowchart(
            nodes=[
                Node(id="start", label="開始", type="start"),
                Node(id="process1", label="処理", type="process"),
                Node(id="node_end", label="終了", type="end")
            ],
            edges=[
                Edge(source="start", target="process1", label="開始処理"),
                Edge(source="process1", target="node_end")
            ]
        )
        
        result = history_mgr.append_toon_log(session_id, updated_flowchart)
        edge_with_label = next(
            (e for e in result.edges if e.source == "start" and e.target == "process1"),
            None
        )
        assert edge_with_label is not None
        assert edge_with_label.label == "開始処理"
