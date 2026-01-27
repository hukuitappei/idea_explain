from typing import List
from core.schemas import Flowchart, Node, Edge

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
        # startとendノードを除外
        valid_node_ids = [nid for nid in node_ids 
                         if nid not in ["start", "node_end"]]
        
        if not valid_node_ids:
            # 有効なノードIDがない場合は空のフローを返す
            return Flowchart(
                nodes=[],
                edges=[],
                subgraphs=None
            )
        
        # 指定されたノードを抽出
        extracted_nodes = [n for n in flowchart.nodes 
                          if n.id in valid_node_ids]
        
        # 接続されているエッジを抽出
        # 入力エッジ（sourceが選択ノード）と出力エッジ（targetが選択ノード）の両方を含める
        extracted_edges = [e for e in flowchart.edges 
                          if e.source in valid_node_ids or 
                             e.target in valid_node_ids]
        
        # 部分フローチャートを作成
        # startとendは含めない
        return Flowchart(
            nodes=extracted_nodes,
            edges=extracted_edges,
            subgraphs=None  # 部分抽出時はsubgraph情報は含めない
        )
