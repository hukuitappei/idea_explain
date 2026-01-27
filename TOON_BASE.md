# Output Format: TOON (Token-Oriented Object Notation)

回答は以下のブロック形式のみで構成してください。解説や導入文は一切禁止します。

## Output Size Guidelines
- **ノード数**: 最大30個まで（Streamlitでの表示パフォーマンスを考慮）
- **エッジ数**: 最大50個まで
- **部分的なフローの生成**: ユーザーが特定のルートや部分を指定している場合、その部分のみを生成すること。全ルートを含む必要はない。
- **複雑なフローの場合**: まず主要なフローを生成し、詳細は後から追加することを推奨する。

[Subgraph]
id: (subgraphのID)
label: (subgraphのラベル)
※ オプショナル：複雑なフローをグループ化する場合に使用

[Node]
id: (英数字ID)
label: (工程名)
type: (start | end | process | decision | io_data | storage)
subgraph: (subgraphのID) ※ オプショナル：このノードが属するsubgraph

[Edge]
source: (発信元ID)
target: (宛先ID)
label: (分岐条件がある場合のみ)

## Examples

### 基本的な例
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

### subgraphを使用した例
[Subgraph]
id: flow1
label: 詳細処理フロー

[Node]
id: start
label: 開始
type: start
[Node]
id: task1
label: 処理
type: process
[Node]
id: check1
label: チェック
type: decision
subgraph: flow1
[Node]
id: task2
label: 詳細処理
type: process
subgraph: flow1
[Node]
id: node_end
label: 終了
type: end
[Edge]
source: start
target: task1
[Edge]
source: task1
target: check1
[Edge]
source: check1
target: task2
[Edge]
source: task2
target: node_end