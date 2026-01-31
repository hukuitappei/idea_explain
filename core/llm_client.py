import os
import requests
import re
from pathlib import Path
from typing import Optional
from core.exceptions import LLMAPIError
from core.schemas import Flowchart
from core import config
from core.logging_config import logger

class LLMClient:
    def __init__(self):
        # 情報漏洩防止のため、DEBUG_MODE が明示されていない限り詳細は出さない
        self.is_production = not config.DEBUG_MODE

        backend_env = os.getenv("LLM_BACKEND", "").strip().lower()
        if backend_env in {"openai", "ollama"}:
            preferred_backend = backend_env
        else:
            preferred_backend = "auto"

        # Streamlitのsecretsから設定を読み込む（フォールバック処理付き）
        try:
            import streamlit as st
            secrets_openai = st.secrets.get("openai", {}) or {}
            secrets_ollama = st.secrets.get("ollama", {}) or {}
        except (AttributeError, FileNotFoundError, ImportError, RuntimeError):
            secrets_openai = {}
            secrets_ollama = {}

        # Collect OpenAI-compatible settings
        openai_api_key = secrets_openai.get("api_key") or os.getenv("OPENAI_API_KEY", "")
        openai_base_url = secrets_openai.get("base_url") or os.getenv("OPENAI_BASE_URL", config.OPENAI_DEFAULT_BASE_URL)
        openai_model = secrets_openai.get("model") or os.getenv("OPENAI_MODEL", config.OPENAI_DEFAULT_MODEL)

        # Collect Ollama settings
        ollama_base_url = secrets_ollama.get("base_url") or os.getenv("OLLAMA_BASE_URL", config.OLLAMA_DEFAULT_BASE_URL)
        ollama_model = secrets_ollama.get("model") or os.getenv("OLLAMA_MODEL", config.OLLAMA_DEFAULT_MODEL)

        # Decide backend (auto prefers OpenAI if key exists)
        if preferred_backend == "openai":
            self.backend = "openai"
        elif preferred_backend == "ollama":
            self.backend = "ollama"
        else:
            self.backend = "openai" if openai_api_key else "ollama"

        if self.backend == "openai":
            self.openai_api_key = openai_api_key
            self.base_url = openai_base_url
            self.model = openai_model
        else:
            self.base_url = ollama_base_url
            self.model = ollama_model
        
        # APIエンドポイント
        if self.backend == "openai":
            self.api_url = f"{self.base_url.rstrip('/')}/chat/completions"
        else:
            self.api_url = f"{self.base_url}/api/chat"

        # rules.md (Skills) と TOON_BASE.md (Format) を読み込む
        # プロジェクトルートを明示的に指定（Streamlitの実行ディレクトリに依存しない）
        base_dir = Path(__file__).parent.parent
        rules_path = base_dir / "rules.md"
        base_path = base_dir / "TOON_BASE.md"
        
        rules_text = self._load_file(rules_path, "Skills: Standard Flow Logic")
        base_text = self._load_file(base_path, "Format: TOON Output")
        
        # 情報収集の指示を追加
        information_gathering_instruction = """
## 重要: 情報不足時の動作

ユーザーの入力が不十分で、以下の情報が不足している場合：
- 具体的なハードウェア/ソフトウェアの仕様
- 故障の具体的な症状やエラーメッセージ
- 環境設定や前提条件
- 実行すべき具体的な手順

**推測でフローチャートを生成せず、必要な情報を質問する形式で返してください。**

質問の形式例：
「以下の情報を教えてください：
1. jarvisの具体的な故障症状は何ですか？（例：電源が入らない、LEDが点灯しないなど）
2. jarvisの機種や型番は何ですか？
3. 故障が発生した際のエラーメッセージはありますか？」

ユーザーが「わからないところは問いかけてください」と明示している場合、特に注意して情報不足を確認してください。
"""
        
        # システム指示（System Instruction）の構築
        self.system_instruction = f"{rules_text}\n\n{base_text}\n\n{information_gathering_instruction}"

    def _load_file(self, path: Path, default_title: str) -> str:
        """ファイルを安全に読み込み、存在しない場合はデフォルトの見出しを返す"""
        if path.exists():
            return path.read_text(encoding="utf-8")
        return f"# {default_title}\n(No specific instructions found.)"

    @staticmethod
    def is_question_response(response_text: str) -> bool:
        """
        LLMの応答が質問形式かTOON形式かを判定します。
        
        Args:
            response_text: LLMからの応答テキスト
            
        Returns:
            True: 質問形式の場合
            False: TOON形式の場合
        """
        # TOON形式の特徴をチェック
        # [Node]タグが存在する場合はTOON形式と判断
        if re.search(r'\[Node\]', response_text, re.IGNORECASE):
            return False
        
        # [Edge]タグが存在する場合もTOON形式と判断
        if re.search(r'\[Edge\]', response_text, re.IGNORECASE):
            return False
        
        # 質問パターンをチェック
        question_patterns = [
            r'教えてください',
            r'何ですか[？?]',
            r'どのよう[なに]',
            r'どれ[がを]',
            r'いつ[がを]',
            r'どこ[がを]',
            r'なぜ',
            r'どうして',
            r'[？?]\s*$',  # 文末が?で終わる
            r'以下の情報',
            r'質問',
            r'確認',
        ]
        
        # 質問パターンが含まれているかチェック
        for pattern in question_patterns:
            if re.search(pattern, response_text, re.IGNORECASE):
                return True
        
        # 数字付きの質問リスト形式（例：「1. ...ですか？」）
        numbered_question_pattern = r'\d+[\.．]\s*[^。\n]*[？?]'
        if re.search(numbered_question_pattern, response_text):
            return True
        
        # デフォルトはTOON形式と判断（質問形式ではない）
        return False

    def validate_output_size(self, toon_text: str) -> tuple[bool, str]:
        """
        生成されたTOON形式のテキストのサイズを検証します。
        
        Args:
            toon_text: TOON形式のテキスト
        
        Returns:
            (is_valid, message): 検証結果とメッセージ
        """
        # ノード数とエッジ数をカウント
        node_count = len(re.findall(r'\[Node\]', toon_text))
        edge_count = len(re.findall(r'\[Edge\]', toon_text))
        
        MAX_NODES = config.MAX_TOON_NODES
        MAX_EDGES = config.MAX_TOON_EDGES
        
        issues = []
        if node_count > MAX_NODES:
            issues.append(f"ノード数が{node_count}個で上限({MAX_NODES}個)を超えています。")
        if edge_count > MAX_EDGES:
            issues.append(f"エッジ数が{edge_count}個で上限({MAX_EDGES}個)を超えています。")
        
        if issues:
            message = "警告: " + " ".join(issues) + f"Streamlitでの表示に問題が発生する可能性があります。主要なルートのみを生成することを推奨します。"
            return False, message
        
        return True, f"ノード数: {node_count}, エッジ数: {edge_count}"

    def generate_partial_change(
        self, 
        user_input: str, 
        target_flowchart: Flowchart,
        full_flowchart: Flowchart
    ) -> str:
        """
        選択された範囲に対してのみ変更指示を出します。
        
        Args:
            user_input: ユーザーの変更指示
            target_flowchart: 変更対象の部分フロー
            full_flowchart: 全体フロー（参照用、start/endを含む）
        
        Returns:
            TOON形式の変更結果
        """
        try:
            if config.DEBUG_MODE:
                logger.debug("LLM partial change request started (backend=%s model=%s)", self.backend, self.model)
            # 選択範囲のTOON形式を生成
            target_toon = target_flowchart.to_toon_format()
            
            # 全体フローの構造説明（start/endの位置を参照）
            full_context = f"""全体フローチャートの構造（参照用）:
- 開始ノード: start
- 終了ノード: node_end
- 選択範囲外のノードは変更しないでください

変更対象の範囲:
{target_toon}

変更指示: {user_input}

重要:
- startとendノードは変更対象外です。これらのノードを含めないでください。
- 選択された範囲のノードとエッジのみを変更してください。
- 選択範囲外のノードやエッジは変更しないでください。
- 新しいノードを追加する場合は、既存のノードIDと重複しないようにしてください。
- 変更結果はTOON形式で返してください。
"""
            
            if self.backend == "openai":
                if not getattr(self, "openai_api_key", ""):
                    raise LLMAPIError("OPENAI_API_KEY が設定されていません。")
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.system_instruction},
                        {"role": "user", "content": full_context},
                    ],
                    "temperature": 0.7,
                }
                headers = {"Authorization": f"Bearer {self.openai_api_key}"}
            else:
                # Ollama HTTP APIを直接呼び出し
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.system_instruction},
                        {"role": "user", "content": full_context}
                    ],
                    "options": {
                        "temperature": 0.7
                    },
                    "stream": False
                }
                headers = None
            
            # localhostへの接続ではプロキシを使用しない
            proxies = {"http": None, "https": None} if "localhost" in self.base_url or "127.0.0.1" in self.base_url else None
            
            response = requests.post(
                self.api_url,
                json=payload,
                timeout=config.LLM_REQUEST_TIMEOUT_SEC,
                proxies=proxies,
                headers=headers,
            )
            
            response.raise_for_status()
            result = response.json()
            
            toon_text = ""
            if self.backend == "openai":
                # OpenAI-compatible response
                toon_text = (
                    (result.get("choices") or [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
            else:
                if result and 'message' in result and 'content' in result['message']:
                    toon_text = result['message']['content']
                
            if toon_text:
                # 出力サイズの検証（質問形式の応答の場合はスキップ）
                if not self.is_question_response(toon_text):
                    is_valid, validation_message = self.validate_output_size(toon_text)
                    if not is_valid:
                        warning_comment = f"<!-- {validation_message} -->\n"
                        toon_text = warning_comment + toon_text
                
                return toon_text
            else:
                raise ValueError("モデルから有効な応答が得られませんでした。")
                
        except ValueError:
            logger.exception("LLMClient.generate_partial_change: ValueError")
            raise
        except requests.exceptions.ConnectionError as e:
            logger.exception("LLMClient.generate_partial_change: ConnectionError")
            if self.is_production:
                # 本番環境では詳細情報を非表示
                raise LLMAPIError(
                    "Ollamaへの接続に失敗しました。\n"
                    "システム管理者に連絡してください。"
                ) from e
            else:
                # 開発環境では詳細情報を表示
                raise LLMAPIError(
                    f"Ollamaへの接続に失敗しました。\n"
                    f"確認事項:\n"
                    f"1. Ollamaが起動しているか確認してください（`ollama serve`またはOllamaアプリが起動しているか）\n"
                    f"2. ベースURL: {self.base_url}\n"
                    f"3. モデル名: {self.model}（`ollama pull {self.model}`でインストールされているか確認）\n"
                    f"4. エラー詳細: {str(e)}"
                ) from e
        except requests.exceptions.Timeout as e:
            logger.exception("LLMClient.generate_partial_change: Timeout")
            raise LLMAPIError(
                f"Ollama APIへのリクエストがタイムアウトしました。\n"
                f"モデル名: {self.model}\n"
                f"エラー詳細: {str(e)}"
            ) from e
        except requests.exceptions.HTTPError as e:
            logger.exception("LLMClient.generate_partial_change: HTTPError")
            if self.is_production:
                # 本番環境では詳細情報を非表示
                raise LLMAPIError(
                    f"Ollama APIでエラーが発生しました。\n"
                    f"システム管理者に連絡してください。"
                ) from e
            else:
                # 開発環境では詳細情報を表示
                error_detail = ""
                try:
                    error_response = response.json()
                    if 'error' in error_response:
                        error_detail = f"\nエラー内容: {error_response['error']}"
                except:
                    pass
                
                raise LLMAPIError(
                    f"Ollama APIでHTTPエラーが発生しました。\n"
                    f"ステータスコード: {response.status_code}\n"
                    f"ベースURL: {self.base_url}\n"
                    f"モデル名: {self.model}\n"
                    f"{error_detail}\n"
                    f"エラー詳細: {str(e)}"
                ) from e
        except Exception as e:
            logger.exception("LLMClient.generate_partial_change: Unexpected error")
            error_msg = str(e)
            if "Connection" in error_msg or "connect" in error_msg.lower():
                if self.is_production:
                    raise LLMAPIError(
                        "Ollamaへの接続に失敗しました。\n"
                        "システム管理者に連絡してください。"
                    ) from e
                else:
                    raise LLMAPIError(
                        f"Ollamaへの接続に失敗しました。\n"
                        f"確認事項:\n"
                        f"1. Ollamaが起動しているか確認してください（`ollama serve`またはOllamaアプリが起動しているか）\n"
                        f"2. ベースURL: {self.base_url}\n"
                        f"3. モデル名: {self.model}（`ollama pull {self.model}`でインストールされているか確認）\n"
                        f"4. エラー詳細: {error_msg}"
                    ) from e
            if self.is_production:
                raise LLMAPIError("Ollama APIとの通信に失敗しました。システム管理者に連絡してください。") from e
            raise LLMAPIError(f"Ollama APIとの通信に失敗しました: {error_msg}") from e

    def generate_flow(self, user_input: str, current_flowchart: Optional[Flowchart] = None) -> str:
        """
        ユーザーの入力を受け取り、OllamaからTOON形式のテキストを取得します。
        
        Args:
            user_input: ユーザーの入力テキスト
            current_flowchart: 既存のFlowchart（文脈として渡す）
        
        Raises:
            ValueError: モデルから有効な応答が得られない場合
            LLMAPIError: Ollama APIとの通信に失敗した場合
        """
        try:
            if config.DEBUG_MODE:
                logger.debug("LLM generate_flow request started (backend=%s model=%s)", self.backend, self.model)
            # 既存のFlowchartがある場合、TOON形式に変換してコンテキストとして追加
            if current_flowchart:
                context = f"既存のフローチャート:\n{current_flowchart.to_toon_format()}\n\n"
                enhanced_input = context + f"上記のフローチャートを参考に、以下の指示に従ってフローチャートを生成または更新してください:\n{user_input}"
            else:
                enhanced_input = user_input
            
            # ユーザー入力に質問を促すキーワードが含まれるかチェック
            question_keywords = ["問いかけて", "質問して", "聞いて", "確認して"]
            requires_questions = any(keyword in user_input for keyword in question_keywords)
            
            # システムプロンプトに追加の強調を加える
            if requires_questions:
                additional_instruction = "\n\n【重要】ユーザーは情報不足時に質問することを明示的に要求しています。推測せず、必要な情報を質問してください。"
                system_prompt = self.system_instruction + additional_instruction
            else:
                system_prompt = self.system_instruction
            
            if self.backend == "openai":
                if not getattr(self, "openai_api_key", ""):
                    raise LLMAPIError("OPENAI_API_KEY が設定されていません。")
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": enhanced_input},
                    ],
                    "temperature": 0.7,
                }
                headers = {"Authorization": f"Bearer {self.openai_api_key}"}
            else:
                # Ollama HTTP APIを直接呼び出し
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": enhanced_input}
                    ],
                    "options": {
                        "temperature": 0.7
                    },
                    "stream": False
                }
                headers = None
            
            # localhostへの接続ではプロキシを使用しない
            proxies = {"http": None, "https": None} if "localhost" in self.base_url or "127.0.0.1" in self.base_url else None
            
            response = requests.post(
                self.api_url,
                json=payload,
                timeout=config.LLM_REQUEST_TIMEOUT_SEC,
                proxies=proxies,
                headers=headers,
            )
            
            # HTTPステータスコードのチェック
            response.raise_for_status()
            
            # JSONレスポンスの解析
            result = response.json()
            
            toon_text = ""
            if self.backend == "openai":
                toon_text = (
                    (result.get("choices") or [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
            else:
                if result and 'message' in result and 'content' in result['message']:
                    toon_text = result['message']['content']
                
            if toon_text:
                # 出力サイズの検証（質問形式の応答の場合はスキップ）
                if not self.is_question_response(toon_text):
                    is_valid, validation_message = self.validate_output_size(toon_text)
                    if not is_valid:
                        # 警告メッセージをTOON形式の前に追加（コメント形式）
                        warning_comment = f"<!-- {validation_message} -->\n"
                        toon_text = warning_comment + toon_text
                
                return toon_text
            else:
                raise ValueError("モデルから有効な応答が得られませんでした。")
                
        except ValueError:
            # 再発生させる
            logger.exception("LLMClient.generate_flow: ValueError")
            raise
        except requests.exceptions.ConnectionError as e:
            # 接続エラーの場合
            logger.exception("LLMClient.generate_flow: ConnectionError")
            if self.is_production:
                raise LLMAPIError(
                    "Ollamaへの接続に失敗しました。\n"
                    "システム管理者に連絡してください。"
                ) from e
            else:
                raise LLMAPIError(
                    f"Ollamaへの接続に失敗しました。\n"
                    f"確認事項:\n"
                    f"1. Ollamaが起動しているか確認してください（`ollama serve`またはOllamaアプリが起動しているか）\n"
                    f"2. ベースURL: {self.base_url}\n"
                    f"3. モデル名: {self.model}（`ollama pull {self.model}`でインストールされているか確認）\n"
                    f"4. エラー詳細: {str(e)}"
                ) from e
        except requests.exceptions.Timeout as e:
            logger.exception("LLMClient.generate_flow: Timeout")
            raise LLMAPIError(
                f"Ollama APIへのリクエストがタイムアウトしました。\n"
                f"モデル名: {self.model}\n"
                f"エラー詳細: {str(e)}"
            ) from e
        except requests.exceptions.HTTPError as e:
            # HTTPエラーの場合（404, 500など）
            logger.exception("LLMClient.generate_flow: HTTPError")
            if self.is_production:
                raise LLMAPIError(
                    f"Ollama APIでエラーが発生しました。\n"
                    f"システム管理者に連絡してください。"
                ) from e
            else:
                error_detail = ""
                try:
                    error_response = response.json()
                    if 'error' in error_response:
                        error_detail = f"\nエラー内容: {error_response['error']}"
                except:
                    pass
                
                raise LLMAPIError(
                    f"Ollama APIでHTTPエラーが発生しました。\n"
                    f"ステータスコード: {response.status_code}\n"
                    f"ベースURL: {self.base_url}\n"
                    f"モデル名: {self.model}\n"
                    f"{error_detail}\n"
                    f"エラー詳細: {str(e)}"
                ) from e
        except Exception as e:
            # その他のエラー
            logger.exception("LLMClient.generate_flow: Unexpected error")
            error_msg = str(e)
            if "Connection" in error_msg or "connect" in error_msg.lower():
                if self.is_production:
                    raise LLMAPIError(
                        "Ollamaへの接続に失敗しました。\n"
                        "システム管理者に連絡してください。"
                    ) from e
                else:
                    raise LLMAPIError(
                        f"Ollamaへの接続に失敗しました。\n"
                        f"確認事項:\n"
                        f"1. Ollamaが起動しているか確認してください（`ollama serve`またはOllamaアプリが起動しているか）\n"
                        f"2. ベースURL: {self.base_url}\n"
                        f"3. モデル名: {self.model}（`ollama pull {self.model}`でインストールされているか確認）\n"
                        f"4. エラー詳細: {error_msg}"
                    ) from e
            if self.is_production:
                raise LLMAPIError("Ollama APIとの通信に失敗しました。システム管理者に連絡してください。") from e
            raise LLMAPIError(f"Ollama APIとの通信に失敗しました: {error_msg}") from e