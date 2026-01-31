import pytest

from core.exceptions import TOONParseError
from core.mermaid_parser import MermaidParser


def test_mermaid_parser_parses_nodes_and_edges():
    mermaid = """```mermaid
graph TD
start[(開始)]
decision1{分岐?}
task1[処理]
node_end[(終了)]
start --> decision1
decision1 -->| "はい" | task1
task1 --> node_end
```"""

    flow = MermaidParser.parse(mermaid)
    assert len(flow.nodes) == 4
    assert len(flow.edges) == 3

    node_types = {n.id: n.type for n in flow.nodes}
    assert node_types["start"] == "start"
    assert node_types["decision1"] == "decision"
    assert node_types["task1"] == "process"
    assert node_types["node_end"] == "end"


def test_mermaid_parser_raises_when_no_nodes_defined():
    with pytest.raises(TOONParseError):
        MermaidParser.parse("graph TD\nA-->B")

