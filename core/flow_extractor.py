from typing import List
from core.schemas import Flowchart

class FlowExtractor:
    """フローチャートから選択範囲を抽出する機能"""
    
    @staticmethod
    def extract_node_range(flowchart: Flowchart, node_ids: List[str]) -> Flowchart:
        """
        指定されたノードIDの範囲を抽出します。
        startとendノードは除外されます。
        
        Args:
            flowchart: 元のフローチャート
            node_ids: 抽出するノードIDのリスト
            
        Returns:
            抽出されたフローチャート（部分フロー）
        """
        # startとendノードを除外（選択対象外）
        valid_node_ids = [nid for nid in node_ids 
                         if nid not in ["start", "node_end"]]
        
        # 選択されたノードのうち、実際に存在するものだけを対象にする
        selected_nodes = [n for n in flowchart.nodes if n.id in valid_node_ids]
        if not selected_nodes:
            raise ValueError("選択されたノードが見つかりませんでした。")

        # Flowchartモデルのバリデーション要件（start/end必須）を満たすため、
        # 部分フローにも start/node_end を含める（ただし変更対象ではない）
        included_ids = {n.id for n in selected_nodes}
        if any(n.id == "start" for n in flowchart.nodes):
            included_ids.add("start")
        if any(n.id == "node_end" for n in flowchart.nodes):
            included_ids.add("node_end")

        extracted_nodes = [n for n in flowchart.nodes if n.id in included_ids]

        # エッジは「両端が含まれているものだけ」採用（参照先が欠けるのを防ぐ）
        extracted_edges = [
            e for e in flowchart.edges if e.source in included_ids and e.target in included_ids
        ]
        
        # 部分フローチャートを作成
        return Flowchart(
            nodes=extracted_nodes,
            edges=extracted_edges,
            subgraphs=None  # 部分抽出時はsubgraph情報は含めない
        )
