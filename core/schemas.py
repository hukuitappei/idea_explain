from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Dict
from enum import Enum
from collections import defaultdict
import warnings
from core.exceptions import FlowchartValidationError

class NodeStatus(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    MISSING = "missing"

class Node(BaseModel):
    id: str
    label: str
    type: str = "process"
    status: NodeStatus = NodeStatus.ACTIVE
    subgraph_id: Optional[str] = None  # ノードが属するsubgraphのID

class Edge(BaseModel):
    source: str
    target: str
    label: Optional[str] = None

class Flowchart(BaseModel):
    nodes: List[Node]
    edges: List[Edge]
    subgraphs: Optional[Dict[str, str]] = None  # {subgraph_id: subgraph_label} のマッピング

    @field_validator('nodes')
    @classmethod
    def validate_flow_structure(cls, v: List[Node]) -> List[Node]:
        if not v:
            raise FlowchartValidationError("ノードが1つも存在しません")
        
        # 開始/終了ノードの存在チェック
        types = {node.type for node in v}
        if "start" not in types or "end" not in types:
            raise FlowchartValidationError("開始/終了ノードが必要です")
        
        # ノードIDの重複チェック
        node_ids = [node.id for node in v]
        duplicates = [node_id for node_id in node_ids if node_ids.count(node_id) > 1]
        if duplicates:
            raise FlowchartValidationError(f"ノードIDが重複しています: {set(duplicates)}")
        
        # ノードタイプの有効性チェック
        valid_types = {"start", "end", "process", "decision", "io_data", "storage", "missing"}
        invalid_types = [node.type for node in v if node.type not in valid_types]
        if invalid_types:
            raise FlowchartValidationError(f"無効なノードタイプが使用されています: {set(invalid_types)}")
        
        return v

    @model_validator(mode='after')
    def validate_edges_reference_nodes(self):
        """エッジが有効なノードIDを参照しているかチェック（警告のみ、論理の穴検知で自動修正）"""
        node_ids = {node.id for node in self.nodes}
        
        # エッジの有効性チェック（警告のみ、例外は投げない）
        invalid_edges = []
        for edge in self.edges:
            if edge.source not in node_ids:
                invalid_edges.append(f"source '{edge.source}' が存在しません")
            if edge.target not in node_ids:
                invalid_edges.append(f"target '{edge.target}' が存在しません")
        
        if invalid_edges:
            # 警告のみを出力（論理の穴検知で自動修正される）
            warnings.warn(
                f"無効なエッジが検出されました（論理の穴検知で自動修正されます）: {', '.join(invalid_edges)}",
                UserWarning
            )
        
        return self

    def detect_logic_gaps(self) -> List[Node]:
        """論理の穴（出口のない分岐、接続先/接続元未定義ノード、孤立ノード）を検出"""
        node_ids = {node.id for node in self.nodes}
        gaps = []
        
        # 各ノードの接続状況を確認（defaultdictを使用してKeyErrorを防ぐ）
        outgoing_edges = defaultdict(list)
        incoming_edges = defaultdict(list)
        
        # 既存ノードを初期化
        for node in self.nodes:
            outgoing_edges[node.id] = []
            incoming_edges[node.id] = []
        
        # エッジを処理（存在しないノードIDでもKeyErrorが発生しない）
        for edge in self.edges:
            outgoing_edges[edge.source].append(edge)
            incoming_edges[edge.target].append(edge)
        
        # 1. 出口のない分岐（DECISIONノードで出口が1つ以下）
        for node in self.nodes:
            if node.type == "decision":
                outgoing_count = len(outgoing_edges[node.id])
                if outgoing_count == 0:
                    # DECISIONノードに出口がない場合（重大な問題）
                    gaps.append(node)
                elif outgoing_count == 1:
                    # DECISIONノードに出口が1つしかない場合（通常は2つ以上必要）
                    gaps.append(node)
        
        # 2. 接続先/接続元未定義ノード（エッジのtarget/sourceが存在しない）
        # 重複を防ぐために既に処理済みのIDを記録
        processed_missing_ids = set()
        
        for edge in self.edges:
            # 接続先未定義ノードのチェック
            if edge.target not in node_ids:
                missing_id = f"missing_{edge.target}"
                if missing_id not in processed_missing_ids:
                    missing_node = Node(
                        id=missing_id,
                        label=f"未定義: {edge.target}",
                        type="missing",
                        status=NodeStatus.MISSING
                    )
                    gaps.append(missing_node)
                    processed_missing_ids.add(missing_id)
            
            # 接続元未定義ノードのチェック
            if edge.source not in node_ids:
                missing_id = f"missing_{edge.source}"
                if missing_id not in processed_missing_ids:
                    missing_node = Node(
                        id=missing_id,
                        label=f"未定義: {edge.source}",
                        type="missing",
                        status=NodeStatus.MISSING
                    )
                    gaps.append(missing_node)
                    processed_missing_ids.add(missing_id)
        
        # 3. 孤立ノード（START/END以外で接続がない）
        for node in self.nodes:
            if node.type not in ["start", "end"]:
                if len(outgoing_edges[node.id]) == 0 and len(incoming_edges[node.id]) == 0:
                    # 孤立しているノードをMISSINGとしてマーク
                    gaps.append(node)
        
        return gaps

    def apply_logic_gap_detection(self) -> 'Flowchart':
        """論理の穴を検出し、MISSINGノードとして追加。

        注意:
        - 未定義ノード参照（edge.source/edge.targetが存在しない）は、MISSINGノードを追加するだけでなく、
          Mermaid上で確実に可視化されるように edge の参照先を missing_* に付け替える。
        """
        gaps = self.detect_logic_gaps()
        
        if not gaps:
            return self
        
        # 既存のノードをコピー
        new_nodes = [Node(**node.model_dump()) for node in self.nodes]
        new_edges = [Edge(**edge.model_dump()) for edge in self.edges]
        
        # ギャップノードを追加または更新
        existing_ids = {node.id for node in new_nodes}
        for gap in gaps:
            if gap.id not in existing_ids:
                new_nodes.append(gap)
                existing_ids.add(gap.id)
            else:
                # 既存ノードをMISSINGとして更新
                for i, node in enumerate(new_nodes):
                    if node.id == gap.id:
                        new_nodes[i] = Node(
                            id=node.id,
                            label=node.label,
                            type="missing",
                            status=NodeStatus.MISSING,
                            subgraph_id=node.subgraph_id
                        )
                        break

        # 未定義ノード参照のエッジを missing_* に付け替える（Mermaidで確実に表示するため）
        # ここで new_nodes に missing_* を追加する可能性があるので、existing_ids を使い回す
        for i, edge in enumerate(new_edges):
            src = edge.source
            tgt = edge.target
            changed = False

            if src not in existing_ids:
                missing_id = f"missing_{src}"
                if missing_id not in existing_ids:
                    new_nodes.append(
                        Node(
                            id=missing_id,
                            label=f"未定義: {src}",
                            type="missing",
                            status=NodeStatus.MISSING,
                        )
                    )
                    existing_ids.add(missing_id)
                src = missing_id
                changed = True

            if tgt not in existing_ids:
                missing_id = f"missing_{tgt}"
                if missing_id not in existing_ids:
                    new_nodes.append(
                        Node(
                            id=missing_id,
                            label=f"未定義: {tgt}",
                            type="missing",
                            status=NodeStatus.MISSING,
                        )
                    )
                    existing_ids.add(missing_id)
                tgt = missing_id
                changed = True

            if changed:
                new_edges[i] = Edge(source=src, target=tgt, label=edge.label)
        
        return Flowchart(nodes=new_nodes, edges=new_edges, subgraphs=self.subgraphs)

    @staticmethod
    def _get_node_shape(node_type: str) -> str:
        """ノードタイプに応じたMermaid形状を返す"""
        shape_map = {
            "start": "([ ])",
            "end": "([ ])",
            "process": "[ ]",
            "decision": "{ }",
            "io_data": "[/ /]",
            "storage": "[( )]",
            "missing": "{{ }}"
        }
        return shape_map.get(node_type.lower(), "{{ }}")  # デフォルトはMISSING

    @staticmethod
    def _get_status_color(status: NodeStatus) -> str:
        """ノード状態に応じた色を返す"""
        color_map = {
            NodeStatus.ACTIVE: "#90EE90",      # ライトグリーン
            NodeStatus.COMPLETED: "#87CEEB",   # スカイブルー
            NodeStatus.MISSING: "#FF6B6B"       # 赤
        }
        return color_map.get(status, "#D3D3D3")  # デフォルトはグレー

    def to_mermaid(self) -> str:
        """FlowchartをMermaid構文に変換"""
        lines = ["graph TD"]
        style_lines = []
        
        # subgraphがある場合の処理
        if self.subgraphs:
            # subgraphに属さないノードを先に定義
            nodes_outside_subgraph = [n for n in self.nodes if not n.subgraph_id]
            nodes_by_subgraph = defaultdict(list)
            
            # subgraphごとにノードをグループ化
            for n in self.nodes:
                if n.subgraph_id:
                    nodes_by_subgraph[n.subgraph_id].append(n)
            
            # subgraphに属さないノードを定義
            for n in nodes_outside_subgraph:
                safe_id = f"n_{n.id}" if n.id == "end" else n.id
                shape = self._get_node_shape(n.type)
                
                if shape == "([ ])":  # START/END
                    lines.append(f'{safe_id}["{n.label}"]')
                elif shape == "[ ]":  # PROCESS
                    lines.append(f'{safe_id}["{n.label}"]')
                elif shape == "{ }":  # DECISION
                    lines.append(f'{safe_id}{{"{n.label}"}}')
                elif shape == "[/ /]":  # IO_DATA (平行四辺形)
                    lines.append(f'{safe_id}[/"{n.label}"/]')
                elif shape == "[( )]":  # STORAGE (円筒形)
                    lines.append(f'{safe_id}[("{n.label}")]')
                elif shape == "{{ }}":  # MISSING
                    lines.append(f'{safe_id}{{"{n.label}"}}')
                
                color = self._get_status_color(n.status)
                style_lines.append(f'    style {safe_id} fill:{color}')
            
            # subgraphを定義
            for sg_id, sg_label in self.subgraphs.items():
                lines.append(f'    subgraph {sg_id} ["{sg_label}"]')
                
                # このsubgraphに属するノードを定義
                for n in nodes_by_subgraph[sg_id]:
                    safe_id = f"n_{n.id}" if n.id == "end" else n.id
                    shape = self._get_node_shape(n.type)
                    
                    if shape == "([ ])":  # START/END
                        lines.append(f'        {safe_id}["{n.label}"]')
                    elif shape == "[ ]":  # PROCESS
                        lines.append(f'        {safe_id}["{n.label}"]')
                    elif shape == "{ }":  # DECISION
                        lines.append(f'        {safe_id}{{"{n.label}"}}')
                    elif shape == "[/ /]":  # IO_DATA (平行四辺形)
                        lines.append(f'        {safe_id}[/"{n.label}"/]')
                    elif shape == "[( )]":  # STORAGE (円筒形)
                        lines.append(f'        {safe_id}[("{n.label}")]')
                    elif shape == "{{ }}":  # MISSING
                        lines.append(f'        {safe_id}{{"{n.label}"}}')
                    
                    color = self._get_status_color(n.status)
                    style_lines.append(f'    style {safe_id} fill:{color}')
                
                lines.append('    end')
        else:
            # subgraphがない場合は従来通り
            for n in self.nodes:
                safe_id = f"n_{n.id}" if n.id == "end" else n.id
                shape = self._get_node_shape(n.type)
                
                if shape == "([ ])":  # START/END
                    lines.append(f'{safe_id}["{n.label}"]')
                elif shape == "[ ]":  # PROCESS
                    lines.append(f'{safe_id}["{n.label}"]')
                elif shape == "{ }":  # DECISION
                    lines.append(f'{safe_id}{{"{n.label}"}}')
                elif shape == "[/ /]":  # IO_DATA (平行四辺形)
                    lines.append(f'{safe_id}[/"{n.label}"/]')
                elif shape == "[( )]":  # STORAGE (円筒形)
                    lines.append(f'{safe_id}[("{n.label}")]')
                elif shape == "{{ }}":  # MISSING
                    lines.append(f'{safe_id}{{"{n.label}"}}')
                
                color = self._get_status_color(n.status)
                style_lines.append(f'    style {safe_id} fill:{color}')
        
        # エッジ定義
        for e in self.edges:
            src = f"n_{e.source}" if e.source == "end" else e.source
            tgt = f"n_{e.target}" if e.target == "end" else e.target
            
            if e.label:
                lines.append(f'{src}-->|"{e.label}"|{tgt}')
            else:
                lines.append(f'{src}-->{tgt}')
        
        # スタイル定義を追加
        if style_lines:
            lines.append("")
            lines.extend(style_lines)
            
        return "\n".join(lines)

    def to_toon_format(self) -> str:
        """FlowchartをTOON形式（Markdown）に変換"""
        lines = []
        
        # Subgraph定義（存在する場合）
        if self.subgraphs:
            for sg_id, sg_label in self.subgraphs.items():
                lines.append("[Subgraph]")
                lines.append(f"id: {sg_id}")
                lines.append(f"label: {sg_label}")
                lines.append("")
        
        # ノード定義
        for node in self.nodes:
            lines.append("[Node]")
            lines.append(f"id: {node.id}")
            lines.append(f"label: {node.label}")
            lines.append(f"type: {node.type}")
            if node.status != NodeStatus.ACTIVE:
                lines.append(f"status: {node.status.value}")
            if node.subgraph_id:
                lines.append(f"subgraph: {node.subgraph_id}")
            lines.append("")
        
        # エッジ定義
        for edge in self.edges:
            lines.append("[Edge]")
            lines.append(f"source: {edge.source}")
            lines.append(f"target: {edge.target}")
            if edge.label:
                lines.append(f"label: {edge.label}")
            lines.append("")
        
        return "\n".join(lines)