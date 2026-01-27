import re
from typing import List, Dict, Tuple
from core.schemas import Node, Edge, Flowchart, NodeStatus
from core.exceptions import TOONParseError

class MermaidParser:
    """Mermaid形式のフローチャートをFlowchartオブジェクトに変換するパーサー"""
    
    @staticmethod
    def parse(mermaid_text: str) -> Flowchart:
        """
        Mermaid形式のテキストをFlowchartオブジェクトに変換します。
        
        Args:
            mermaid_text: Mermaid形式のテキスト
            
        Returns:
            Flowchartオブジェクト
        """
        # Markdownのコードブロックを除去
        clean_text = re.sub(r'```mermaid\s*\n?', '', mermaid_text)
        clean_text = clean_text.replace('```', '').strip()
        
        lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
        
        nodes = []
        edges = []
        node_map = {}  # ID -> Node のマッピング
        
        # ノード定義とエッジ定義を抽出
        in_subgraph = False
        for line in lines:
            # コメント行をスキップ
            if line.startswith('%%'):
                continue
            
            # style行をスキップ（後で処理）
            if line.startswith('style '):
                continue
            
            # subgraphの開始/終了を検出
            if line.startswith('subgraph '):
                in_subgraph = True
                continue
            if line.strip() == 'end':
                in_subgraph = False
                continue
            
            # ノード定義: id["label"] または id{"label"} または id[("label")]
            # より柔軟なパターンマッチング
            node_patterns = [
                r'(\w+)\[\(["\']([^"\']+)["\']\)\]',  # id[("label")]
                r'(\w+)\[/["\']([^"\']+)["\']/\]',     # id[/"label"/]
                r'(\w+)\[["\']([^"\']+)["\']\]',       # id["label"]
                r'(\w+)\{["\']([^"\']+)["\']\}',       # id{"label"}
                r'(\w+)\[\(([^)]+)\)\]',                # id[(label)]
                r'(\w+)\[([^\]]+)\]',                   # id[label]
                r'(\w+)\{([^}]+)\}',                    # id{label}
            ]
            
            node_found = False
            for pattern in node_patterns:
                node_match = re.match(pattern, line)
                if node_match:
                    node_id = node_match.group(1)
                    label = node_match.group(2)
                    
                    # 形状からノードタイプを判定
                    if '{' in line and '}' in line:
                        node_type = "decision"
                    elif '(' in line and ')' in line:
                        # スタジアム形または円筒形
                        if node_id == "start" or (not nodes and node_id != "node_end"):
                            node_type = "start"
                        elif node_id == "node_end" or node_id.endswith("_end"):
                            node_type = "end"
                        else:
                            node_type = "process"
                    elif '/' in line:
                        node_type = "io_data"
                    else:
                        node_type = "process"
                    
                    # IDが'end'の場合は'node_end'に変換
                    safe_id = "node_end" if node_id.lower() == "end" else node_id
                    
                    # 既に存在するノードはスキップ（重複を防ぐ）
                    if safe_id not in [n.id for n in nodes]:
                        node = Node(
                            id=safe_id,
                            label=label.strip(),
                            type=node_type,
                            status=NodeStatus.ACTIVE
                        )
                        nodes.append(node)
                        node_map[node_id] = node
                    node_found = True
                    break
            
            if node_found:
                continue
            
            # エッジ定義: source-->target または source-->|"label"|target
            edge_patterns = [
                r'(\w+)\s*-->\s*\|\s*["\']([^"\']+)["\']\s*\|\s*(\w+)',  # source-->|"label"|target
                r'(\w+)\s*-->\s*(\w+)',                                   # source-->target
            ]
            
            for pattern in edge_patterns:
                edge_match = re.match(pattern, line)
                if edge_match:
                    source_id = edge_match.group(1)
                    if len(edge_match.groups()) == 3:
                        label = edge_match.group(2)
                        target_id = edge_match.group(3)
                    else:
                        label = None
                        target_id = edge_match.group(2)
                    
                    # IDが'end'の場合は'node_end'に変換
                    safe_source = "node_end" if source_id.lower() == "end" else source_id
                    safe_target = "node_end" if target_id.lower() == "end" else target_id
                    
                    edges.append(Edge(
                        source=safe_source,
                        target=safe_target,
                        label=label.strip() if label else None
                    ))
                    break
        
        # ノードが存在しない場合はエラー
        if not nodes:
            raise TOONParseError(f"Mermaid形式のノードが検出されませんでした。内容：\n{mermaid_text[:200]}...")
        
        # startノードとendノードの存在確認
        node_types = {node.type for node in nodes}
        if "start" not in node_types:
            # startノードがない場合、最初のノードをstartに設定
            if nodes:
                nodes[0].type = "start"
        
        if "end" not in node_types:
            # endノードがない場合、node_endがあればそれをendに設定
            end_node = next((n for n in nodes if n.id == "node_end"), None)
            if end_node:
                end_node.type = "end"
            else:
                # 終了ノードがない場合、最後のノードをendに設定
                if nodes:
                    nodes[-1].type = "end"
        
        return Flowchart(nodes=nodes, edges=edges, subgraphs=None)
    
    @staticmethod
    def _determine_node_type(shape_start: str, shape_end: str) -> str:
        """
        Mermaidの形状からノードタイプを判定します。
        
        Args:
            shape_start: 形状の開始文字（[, {, (）
            shape_end: 形状の終了文字（], }, )）
            
        Returns:
            ノードタイプ（start, end, process, decision）
        """
        # スタジアム形 ([ ]) -> start/end
        if shape_start == "(" and shape_end == ")":
            return "start"  # 最初に見つかったものはstart、最後はendに設定される
        
        # 菱形 { } -> decision
        if shape_start == "{" and shape_end == "}":
            return "decision"
        
        # 長方形 [ ] -> process
        if shape_start == "[" and shape_end == "]":
            return "process"
        
        # デフォルトはprocess
        return "process"
