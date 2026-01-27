import re
from typing import Dict, Optional
from core.schemas import Node, Edge, Flowchart, NodeStatus
from core.exceptions import TOONParseError

class TOONParser:
    @staticmethod
    def parse(text: str) -> Flowchart:
        # Markdownの装飾（```toon...```）があれば除去
        clean_text = re.sub(r'```[a-zA-Z]*\n?', '', text)
        clean_text = clean_text.replace('```', '').strip()

        nodes = []
        edges = []
        subgraphs: Optional[Dict[str, str]] = None

        # [Subgraph]タグで分割して抽出
        subgraph_matches = re.split(r'\[Subgraph\]', clean_text, flags=re.IGNORECASE)[1:]
        if subgraph_matches:
            subgraphs = {}
            for block in subgraph_matches:
                data = TOONParser._parse_block(re.split(r'\[', block)[0])
                if 'id' in data and 'label' in data:
                    sg_id = data['id'].strip()
                    sg_label = data['label'].strip()
                    subgraphs[sg_id] = sg_label

        # [Node]タグで分割して抽出
        node_matches = re.split(r'\[Node\]', clean_text, flags=re.IGNORECASE)[1:]
        for block in node_matches:
            # 次のタグの手前までをパース
            data = TOONParser._parse_block(re.split(r'\[', block)[0])
            if 'id' in data and 'label' in data:
                raw_id = data['id'].strip()
                safe_id = "node_end" if raw_id.lower() == "end" else raw_id
                
                # statusフィールドの読み込み
                status = NodeStatus.ACTIVE  # デフォルト値
                if 'status' in data:
                    try:
                        status = NodeStatus(data['status'].strip().lower())
                    except ValueError:
                        # 無効なstatus値の場合はデフォルト値を使用
                        pass
                
                # subgraphフィールドの読み込み
                subgraph_id = None
                if 'subgraph' in data:
                    subgraph_id = data['subgraph'].strip()
                
                nodes.append(Node(
                    id=safe_id,
                    label=data['label'].strip(),
                    type=data.get('type', 'process').strip().lower(),
                    status=status,
                    subgraph_id=subgraph_id
                ))

        # [Edge]タグで分割して抽出
        edge_matches = re.split(r'\[Edge\]', clean_text, flags=re.IGNORECASE)[1:]
        for block in edge_matches:
            data = TOONParser._parse_block(re.split(r'\[', block)[0])
            if 'source' in data and 'target' in data:
                src = "node_end" if data['source'].strip().lower() == "end" else data['source'].strip()
                tgt = "node_end" if data['target'].strip().lower() == "end" else data['target'].strip()
                edges.append(Edge(source=src, target=tgt, label=data.get('label', '').strip() or None))

        # 最終チェック：ノードが空ならここで例外を投げて app.py でキャッチ
        if not nodes:
            raise TOONParseError(f"有効なTOON形式のノードが検出されませんでした。内容：\n{text[:100]}...")

        return Flowchart(nodes=nodes, edges=edges, subgraphs=subgraphs)

    @staticmethod
    def _parse_block(block: str) -> dict:
        data = {}
        for line in block.strip().split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                data[key.strip().lower()] = val.strip()
        return data