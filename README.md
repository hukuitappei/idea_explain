# TOON-Flow Visualizer

AIとの対話を通じて自然言語をTOON形式で構造化し、リアルタイムでフローチャート化するシステム。

## セットアップ

```bash
# 依存関係のインストール
pip install -r requirements.txt

# 環境変数の設定（オプション）
# .envファイルに以下を追加（デフォルト値で動作します）:
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL=llama3.2
```

## 起動方法

```bash
streamlit run app.py
```

## 主要機能

- 自然言語入力からフローチャート自動生成
- TOON形式での保存・読み込み
- 論理の穴検知と自動修正
- 差分追記機能

## テスト実行

```bash
# テスト実行
pytest tests/

# カバレッジ測定（60%目標）
pytest tests/ --cov=core --cov-report=term-missing --cov-fail-under=60
```
