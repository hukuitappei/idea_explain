"""TOONParserのユニットテスト"""
import pytest
from core.toon_parser import TOONParser
from core.schemas import NodeStatus
from core.exceptions import TOONParseError


class TestTOONParser:
    def test_parse_simple_flow(self):
        toon_text = """
[Node]
id: start
label: 開始
type: start
[Node]
id: task1
label: 処理
type: process
[Node]
id: node_end
label: 終了
type: end
[Edge]
source: start
target: task1
[Edge]
source: task1
target: node_end
"""
        flowchart = TOONParser.parse(toon_text)
        assert len(flowchart.nodes) == 3
        assert len(flowchart.edges) == 2

    def test_parse_with_status(self):
        toon_text = """
[Node]
id: start
label: 開始
type: start
status: completed
[Node]
id: node_end
label: 終了
type: end
[Edge]
source: start
target: node_end
"""
        flowchart = TOONParser.parse(toon_text)
        assert flowchart.nodes[0].status == NodeStatus.COMPLETED

    def test_parse_invalid_status(self):
        toon_text = """
[Node]
id: start
label: 開始
type: start
status: invalid_status
[Node]
id: node_end
label: 終了
type: end
[Edge]
source: start
target: node_end
"""
        flowchart = TOONParser.parse(toon_text)
        # 無効なstatusはデフォルト値（ACTIVE）になる
        assert flowchart.nodes[0].status == NodeStatus.ACTIVE

    def test_parse_with_markdown_code_block(self):
        toon_text = """
```toon
[Node]
id: start
label: 開始
type: start
[Node]
id: node_end
label: 終了
type: end
[Edge]
source: start
target: node_end
```
"""
        flowchart = TOONParser.parse(toon_text)
        assert len(flowchart.nodes) == 2
        assert len(flowchart.edges) == 1

    def test_parse_empty_nodes(self):
        toon_text = "[Edge]\nsource: start\ntarget: end"
        with pytest.raises(TOONParseError, match="有効なTOON形式のノードが検出されませんでした"):
            TOONParser.parse(toon_text)

    def test_parse_end_node_id_protection(self):
        toon_text = """
[Node]
id: end
label: 終了
type: end
[Node]
id: start
label: 開始
type: start
[Edge]
source: start
target: end
"""
        flowchart = TOONParser.parse(toon_text)
        # 'end'は'node_end'に変換される
        assert any(node.id == "node_end" for node in flowchart.nodes)
