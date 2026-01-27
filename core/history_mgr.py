import json
from pathlib import Path
from typing import List, Optional
from core.schemas import Flowchart
from core.toon_parser import TOONParser

class HistoryManager:
    def __init__(self, storage_dir: str = "storage/sessions", toon_dir: str = "storage/toon_files"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.toon_dir = Path(toon_dir)
        self.toon_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session_id: str, history: List[Flowchart]):
        """現在の履歴スタックをJSONファイルとして保存します。"""
        file_path = self.storage_dir / f"{session_id}.json"
        # Pydanticモデルを辞書形式にして保存（EnumをJSONシリアライズ可能な形式に変換）
        data = [flow.model_dump(mode='json') for flow in history]
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def load_session(self, session_id: str) -> List[Flowchart]:
        """保存されたJSONファイルから履歴スタックを復元します。"""
        file_path = self.storage_dir / f"{session_id}.json"
        if not file_path.exists():
            return []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                if not content.strip():
                    # 空のファイルの場合
                    return []
                data = json.loads(content)
            
            # 辞書からPydanticモデルへ変換
            flowcharts = []
            for item in data:
                try:
                    # statusがEnumオブジェクトの場合は文字列に変換
                    if 'nodes' in item:
                        for node in item['nodes']:
                            if 'status' in node:
                                if isinstance(node['status'], dict):
                                    # Enumがdict形式で保存されている場合
                                    if 'value' in node['status']:
                                        node['status'] = node['status']['value']
                                elif not isinstance(node['status'], str):
                                    # Enumオブジェクトの場合は文字列に変換を試みる
                                    node['status'] = str(node['status'])
                                # statusが空の場合はデフォルト値を設定
                                if not node['status']:
                                    node['status'] = 'active'
                    
                    flowcharts.append(Flowchart(**item))
                except Exception as e:
                    # 個別のFlowchartの読み込みに失敗した場合はスキップ
                    import warnings
                    warnings.warn(f"Flowchartの読み込みに失敗しました: {e}")
                    continue
            
            return flowcharts
        except json.JSONDecodeError as e:
            # JSONファイルが破損している場合
            error_msg = f"JSONファイルの読み込みに失敗しました。ファイルが破損している可能性があります: {e}"
            # 破損したファイルをバックアップして削除
            try:
                backup_path = file_path.with_suffix('.json.broken')
                file_path.rename(backup_path)
                error_msg += f"\n破損したファイルは '{backup_path}' にバックアップされました。"
            except Exception:
                pass
            raise ValueError(error_msg) from e
        except Exception as e:
            raise ValueError(f"セッションの読み込みに失敗しました: {e}") from e

    def save_toon_file(self, session_id: str, flowchart: Flowchart):
        """現在のFlowchartをTOON形式（Markdown）で保存します。"""
        file_path = self.toon_dir / f"{session_id}.md"
        toon_text = flowchart.to_toon_format()
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(toon_text)

    def load_toon_file(self, session_id: str) -> Optional[Flowchart]:
        """保存されたTOON形式（Markdown）ファイルからFlowchartを復元します。"""
        file_path = self.toon_dir / f"{session_id}.md"
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                toon_text = f.read()
            return TOONParser.parse(toon_text)
        except Exception as e:
            raise ValueError(f"TOONファイルの読み込みに失敗しました: {e}") from e

    def list_toon_files(self) -> List[str]:
        """保存されているTOONファイルのリストを返します。"""
        return [f.stem for f in self.toon_dir.glob("*.md")]
    
    def list_sessions(self) -> List[str]:
        """保存されているセッション（JSONファイル）のリストを返します。"""
        return [f.stem for f in self.storage_dir.glob("*.json") if not f.name.endswith('.broken')]

    def append_toon_log(self, session_id: str, new_flowchart: Flowchart) -> Flowchart:
        """既存のTOONファイルに新しいノードとエッジを追加（マージ）します。"""
        existing_flow = self.load_toon_file(session_id)
        
        if existing_flow is None:
            # 既存ファイルがない場合は新規作成
            return new_flowchart
        
        # 既存のノードをIDでマッピング
        existing_nodes_map = {node.id: node for node in existing_flow.nodes}
        
        # 新しいノードを追加または更新
        merged_nodes = []
        processed_ids = set()
        
        # まず既存ノードを処理（新しいノードで更新される可能性がある）
        for existing_node in existing_flow.nodes:
            # 新しいノードに同じIDがあるかチェック
            new_node = next((n for n in new_flowchart.nodes if n.id == existing_node.id), None)
            if new_node:
                # 新しいノードで更新
                merged_nodes.append(new_node)
                processed_ids.add(new_node.id)
            else:
                # 既存ノードをそのまま保持
                merged_nodes.append(existing_node)
                processed_ids.add(existing_node.id)
        
        # 新しいノードを追加（まだ処理されていないもののみ）
        for new_node in new_flowchart.nodes:
            if new_node.id not in processed_ids:
                merged_nodes.append(new_node)
        
        # 新しいエッジを追加または更新
        # 既存エッジを(source, target)をキーとしてマッピング
        existing_edges_map = {(edge.source, edge.target): edge for edge in existing_flow.edges}
        merged_edges = []
        processed_edge_keys = set()
        
        # まず既存エッジを処理（新しいエッジで更新される可能性がある）
        for existing_edge in existing_flow.edges:
            edge_key = (existing_edge.source, existing_edge.target)
            # 新しいエッジに同じキーがあるかチェック
            new_edge = next(
                (e for e in new_flowchart.edges if (e.source, e.target) == edge_key),
                None
            )
            if new_edge:
                # 新しいエッジで更新（ラベルが変更された場合など）
                merged_edges.append(new_edge)
                processed_edge_keys.add(edge_key)
            else:
                # 既存エッジをそのまま保持
                merged_edges.append(existing_edge)
                processed_edge_keys.add(edge_key)
        
        # 新しいエッジを追加（まだ処理されていないもののみ）
        for new_edge in new_flowchart.edges:
            edge_key = (new_edge.source, new_edge.target)
            if edge_key not in processed_edge_keys:
                merged_edges.append(new_edge)
        
        # subgraph情報をマージ（新しいsubgraph情報で上書き）
        merged_subgraphs = None
        if existing_flowchart.subgraphs or new_flowchart.subgraphs:
            merged_subgraphs = {}
            if existing_flowchart.subgraphs:
                merged_subgraphs.update(existing_flowchart.subgraphs)
            if new_flowchart.subgraphs:
                merged_subgraphs.update(new_flowchart.subgraphs)
        
        # マージされたFlowchartを作成
        merged_flow = Flowchart(nodes=merged_nodes, edges=merged_edges, subgraphs=merged_subgraphs)
        
        # 論理の穴検知を適用
        merged_flow = merged_flow.apply_logic_gap_detection()
        
        # 保存
        self.save_toon_file(session_id, merged_flow)
        
        return merged_flow