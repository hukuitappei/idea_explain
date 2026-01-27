from typing import List
from core.schemas import Flowchart, Node, Edge

class FlowMerger:
    """部分変更を全体フローにマージする機能"""
    
    @staticmethod
    def merge_partial_change(
        original_flowchart: Flowchart,
        changed_partial: Flowchart,
        selected_node_ids: List[str]
    ) -> Flowchart:
        """
        部分変更を全体フローにマージします。
        
        Args:
            original_flowchart: 元の全体フロー
            changed_partial: 変更された部分フロー
            selected_node_ids: 変更対象だったノードIDのリスト
        
        Returns:
            マージされた全体フロー
        """
        # startとendノードを保護（変更対象外）
        protected_node_ids = {"start", "node_end"}
        
        # 元のノードをコピー
        merged_nodes = [Node(**n.model_dump()) for n in original_flowchart.nodes]
        merged_edges = [Edge(**e.model_dump()) for e in original_flowchart.edges]
        
        # 変更されたノードで更新
        for changed_node in changed_partial.nodes:
            # startとendは更新しない
            if changed_node.id in protected_node_ids:
                continue
                
            if changed_node.id in selected_node_ids:
                # 既存ノードを更新
                for i, node in enumerate(merged_nodes):
                    if node.id == changed_node.id:
                        merged_nodes[i] = changed_node
                        break
        
        # 新しいノードを追加（存在しない場合）
        existing_node_ids = {n.id for n in merged_nodes}
        for changed_node in changed_partial.nodes:
            # startとendは追加しない
            if changed_node.id in protected_node_ids:
                continue
                
            if changed_node.id not in existing_node_ids:
                merged_nodes.append(changed_node)
        
        # 変更されたエッジで更新
        # 選択範囲に関連するエッジを更新
        for changed_edge in changed_partial.edges:
            # startとendに関連するエッジは保護（ただし、選択範囲内のノードへの接続は許可）
            # start/endから選択範囲外へのエッジは変更しない
            if (changed_edge.source in protected_node_ids and 
                changed_edge.target not in selected_node_ids):
                continue
            if (changed_edge.target in protected_node_ids and 
                changed_edge.source not in selected_node_ids):
                continue
            
            # 既存エッジを更新または追加
            edge_key = (changed_edge.source, changed_edge.target)
            existing_edge = next(
                (e for e in merged_edges 
                 if (e.source, e.target) == edge_key),
                None
            )
            if existing_edge:
                # 更新
                idx = merged_edges.index(existing_edge)
                merged_edges[idx] = changed_edge
            else:
                # 追加
                merged_edges.append(changed_edge)
        
        return Flowchart(
            nodes=merged_nodes,
            edges=merged_edges,
            subgraphs=original_flowchart.subgraphs
        )
