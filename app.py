import streamlit as st
import streamlit.components.v1 as components
import base64
from core.schemas import Node, Edge, Flowchart
from core.llm_client import LLMClient
from core.toon_parser import TOONParser
from core.history_mgr import HistoryManager
from core.exceptions import LLMAPIError, TOONParseError, FlowchartValidationError
from core.flow_extractor import FlowExtractor
from core.flow_merger import FlowMerger
from pathlib import Path

st.set_page_config(layout="wide")
st.title("Flowchart Generator & History Manager")

# 1. マネージャーの初期化
history_mgr = HistoryManager()

# 2. セッション履歴の初期化
if 'history' not in st.session_state:
    # 初期状態：開始と終了のみの構成
    initial_flow = Flowchart(
        nodes=[
            Node(id="start", label="開始", type="start"),
            Node(id="node_end", label="終了", type="end")
        ],
        edges=[Edge(source="start", target="node_end")]
    )
    st.session_state.history = [initial_flow]

# 3. 質問応答のセッション管理の初期化
if 'conversation_context' not in st.session_state:
    st.session_state.conversation_context = None  # 元のプロンプト
if 'pending_questions' not in st.session_state:
    st.session_state.pending_questions = None  # 現在の質問テキスト
if 'question_responses' not in st.session_state:
    st.session_state.question_responses = []  # 回答のリスト
if 'append_mode_for_question' not in st.session_state:
    st.session_state.append_mode_for_question = False  # 質問時の差分追記モード設定
if 'question_count' not in st.session_state:
    st.session_state.question_count = 0  # 質問回数のカウント（無限ループ防止）
if 'selected_node_ids' not in st.session_state:
    st.session_state.selected_node_ids = []  # 選択されたノードIDのリスト
if 'selection_mode' not in st.session_state:
    st.session_state.selection_mode = 'text'  # 'text' or 'ui'
MAX_QUESTION_COUNT = 5  # 質問回数の上限

# --- サイドバー：セッション管理 ---
st.sidebar.header("💾 セッション管理")

# 保存済みセッションの一覧を取得
saved_sessions = history_mgr.list_sessions()

# セッション名の入力（新規作成用）
session_name = st.sidebar.text_input("セッション名（新規作成/保存用）", value="default_session")

col_save, col_load = st.sidebar.columns(2)
with col_save:
    if st.button("保存", use_container_width=True):
        history_mgr.save_session(session_name, st.session_state.history)
        # 最新のFlowchartをTOON形式でも保存
        if st.session_state.history:
            history_mgr.save_toon_file(session_name, st.session_state.history[-1])
        st.sidebar.success(f"'{session_name}' を保存しました")
        st.rerun()

with col_load:
    if st.button("削除", use_container_width=True):
        if session_name in saved_sessions:
            try:
                json_path = history_mgr.storage_dir / f"{session_name}.json"
                toon_path = history_mgr.toon_dir / f"{session_name}.md"
                if json_path.exists():
                    json_path.unlink()
                if toon_path.exists():
                    toon_path.unlink()
                st.sidebar.success(f"'{session_name}' を削除しました")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"削除に失敗しました: {e}")
        else:
            st.sidebar.warning("セッションが見つかりません")

# セッションの読み込み（選択式）
st.sidebar.subheader("📂 セッションを読み込む")
if saved_sessions:
    selected_session = st.sidebar.selectbox(
        "保存済みセッションを選択",
        [""] + saved_sessions,
        key="session_selector"
    )
    if selected_session and st.sidebar.button("選択したセッションを読み込み", use_container_width=True):
        try:
            loaded_history = history_mgr.load_session(selected_session)
            if loaded_history:
                st.session_state.history = loaded_history
                st.sidebar.success(f"'{selected_session}' を読み込みました")
                st.rerun()
            else:
                st.sidebar.error("セッションの読み込みに失敗しました")
        except ValueError as e:
            st.sidebar.error(str(e))
        except Exception as e:
            st.sidebar.error(f"エラーが発生しました: {e}")
else:
    st.sidebar.info("保存されたセッションはありません")

# TOONファイルの読み込み
st.sidebar.subheader("📄 TOONファイル管理")
toon_files = history_mgr.list_toon_files()
if toon_files:
    selected_toon = st.sidebar.selectbox("TOONファイルを選択", [""] + toon_files)
    if selected_toon and st.sidebar.button("TOONファイルを読み込み"):
        try:
            loaded_flow = history_mgr.load_toon_file(selected_toon)
            if loaded_flow:
                st.session_state.history = [loaded_flow]
                st.sidebar.success(f"'{selected_toon}' を読み込みました")
                st.rerun()
            else:
                st.sidebar.error("TOONファイルが見つかりません")
        except ValueError as e:
            st.sidebar.error(str(e))
else:
    st.sidebar.info("保存されたTOONファイルはありません")

# --- デバッグ情報：Ollama設定 ---
st.sidebar.divider()
st.sidebar.subheader("⚙️ Ollama設定")
try:
    ollama_config = st.secrets.get("ollama", {})
    base_url = ollama_config.get("base_url", "http://localhost:11434")
    model = ollama_config.get("model", "llama3.2")
    config_source = "secrets.toml"
except (AttributeError, FileNotFoundError, ImportError, RuntimeError):
    import os
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.2")
    config_source = "環境変数"

st.sidebar.text(f"設定元: {config_source}")
# セキュリティのため、ベースURLは表示しない
st.sidebar.text(f"モデル: {model}")

# --- 描画と履歴管理ロジック ---
st.divider()

# 履歴を遡るスライダー
if len(st.session_state.history) > 1:
    history_index = st.sidebar.slider(
        "履歴を遡る", 
        min_value=0, 
        max_value=len(st.session_state.history) - 1, 
        value=len(st.session_state.history) - 1
    )
else:
    history_index = 0
    st.sidebar.info("現在は初期状態です。")

current_flow = st.session_state.history[history_index]

# 3ペイン構成: 左（Chat/Input）、中央（Flowchart）、右（Source）
col_chat, col_flow, col_source = st.columns([1, 2, 1])

with col_chat:
    st.subheader("💬 チャット")
    
    # 質問が保留中の場合は質問を表示し、回答入力欄を表示
    if st.session_state.pending_questions:
        # 質問と回答の履歴を表示
        if st.session_state.conversation_context:
            with st.expander("📝 会話履歴", expanded=False):
                st.markdown("**元のプロンプト:**")
                st.text(st.session_state.conversation_context)
                
                if st.session_state.question_responses:
                    st.markdown("**これまでの回答:**")
                    for i, response in enumerate(st.session_state.question_responses, 1):
                        st.markdown(f"{i}. {response}")
        
        st.info("📋 LLMからの質問:")
        st.markdown(st.session_state.pending_questions)
        
        st.divider()
        st.subheader("💭 回答を入力")
        
        # 回答入力欄
        user_answer = st.text_area(
            "質問に対する回答を入力してください",
            placeholder="回答を入力...",
            height=100,
            key="answer_input"
        )
        
        col_answer, col_cancel = st.columns([2, 1])
        with col_answer:
            if st.button("回答を送信", type="primary", use_container_width=True):
                if user_answer:
                    # 回答を収集
                    st.session_state.question_responses.append(user_answer)
                    
                    # 元のプロンプト、質問、回答を組み合わせて再送信
                    combined_prompt = st.session_state.conversation_context
                    if st.session_state.pending_questions:
                        combined_prompt += f"\n\n質問:\n{st.session_state.pending_questions}\n"
                    if st.session_state.question_responses:
                        combined_prompt += "\n\n回答:\n"
                        for i, response in enumerate(st.session_state.question_responses, 1):
                            combined_prompt += f"{i}. {response}\n"
                    
                    # 質問時の差分追記モード設定を保存
                    append_mode_flag = st.session_state.append_mode_for_question
                    
                    # セッション状態を一時的に保存（エラー時に復元するため）
                    temp_context = st.session_state.conversation_context
                    temp_questions = st.session_state.pending_questions
                    temp_responses = st.session_state.question_responses.copy()
                    
                    # 再送信処理
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    status_text.info("LLMがフローを設計中...（最大2分かかる場合があります）")
                    progress_bar.progress(10)
                    
                    try:
                        client = LLMClient()
                        raw_toon_text = client.generate_flow(combined_prompt, current_flow if append_mode_flag else None)
                        progress_bar.progress(100)
                        status_text.empty()
                        
                        # 質問形式の応答かチェック
                        if client.is_question_response(raw_toon_text):
                            # 質問回数の上限チェック
                            st.session_state.question_count += 1
                            if st.session_state.question_count >= MAX_QUESTION_COUNT:
                                st.error(f"質問回数が上限（{MAX_QUESTION_COUNT}回）に達しました。セッションをリセットしてください。")
                                st.session_state.conversation_context = None
                                st.session_state.pending_questions = None
                                st.session_state.question_responses = []
                                st.session_state.question_count = 0
                            else:
                                # 再度質問が来た場合、セッション状態を更新
                                st.session_state.conversation_context = combined_prompt
                                st.session_state.pending_questions = raw_toon_text
                                st.session_state.question_responses = []  # 新しい質問なので回答をリセット
                                st.info(f"LLMから追加の質問がありました。回答を入力してください。（質問回数: {st.session_state.question_count}/{MAX_QUESTION_COUNT}）")
                                st.rerun()
                        else:
                            # 出力サイズの検証
                            is_valid, validation_message = client.validate_output_size(raw_toon_text)
                            if not is_valid:
                                st.warning(validation_message)
                                st.info("主要なルートのみを生成するか、フローを分割することを検討してください。")
                            
                            # TOON形式のパース成功時のみセッション状態をリセット
                            st.session_state.conversation_context = None
                            st.session_state.pending_questions = None
                            st.session_state.question_responses = []
                            st.session_state.question_count = 0  # 質問回数もリセット
                            
                            # TOON形式のパース
                            new_flow = TOONParser.parse(raw_toon_text)
                            
                            # 論理の穴検知を適用
                            new_flow = new_flow.apply_logic_gap_detection()
                            
                            # 差分追記モードの場合
                            if append_mode_flag:
                                merged_flow = history_mgr.append_toon_log(session_name, new_flow)
                                st.session_state.history.append(merged_flow)
                                st.success(f"'{session_name}' のTOONファイルに差分を追記しました")
                            else:
                                # 通常モード：履歴に追加
                                st.session_state.history.append(new_flow)
                        
                        st.rerun()
                    except LLMAPIError as e:
                        # エラー時はセッション状態を復元
                        st.session_state.conversation_context = temp_context
                        st.session_state.pending_questions = temp_questions
                        st.session_state.question_responses = temp_responses
                        st.error(f"LLM APIエラー: {e}")
                        st.info("Ollamaが起動しているか、モデルがインストールされているか確認してください。")
                        # エラー時はst.rerun()を呼ばない（無限ループ防止）
                    except TOONParseError as e:
                        # エラー時はセッション状態を復元
                        st.session_state.conversation_context = temp_context
                        st.session_state.pending_questions = temp_questions
                        st.session_state.question_responses = temp_responses
                        
                        # 質問形式の応答の可能性をチェック
                        if 'raw_toon_text' in locals() and raw_toon_text:
                            if client.is_question_response(raw_toon_text):
                                # 質問回数の上限チェック
                                st.session_state.question_count += 1
                                if st.session_state.question_count >= MAX_QUESTION_COUNT:
                                    st.error(f"質問回数が上限（{MAX_QUESTION_COUNT}回）に達しました。セッションをリセットしてください。")
                                    st.session_state.conversation_context = None
                                    st.session_state.pending_questions = None
                                    st.session_state.question_responses = []
                                    st.session_state.question_count = 0
                                else:
                                    # 質問形式の応答だった場合
                                    st.session_state.conversation_context = combined_prompt
                                    st.session_state.pending_questions = raw_toon_text
                                    st.session_state.question_responses = []
                                    st.info(f"LLMから追加の質問がありました。回答を入力してください。（質問回数: {st.session_state.question_count}/{MAX_QUESTION_COUNT}）")
                                    st.rerun()
                            else:
                                st.error(f"TOON形式の解析に失敗しました: {e}")
                                with st.expander("🔍 LLMの生出力（デバッグ用）", expanded=True):
                                    st.info("以下のテキストをTOON形式として解釈しようとしましたが、失敗しました。")
                                    st.code(raw_toon_text)
                        else:
                            st.error(f"TOON形式の解析に失敗しました: {e}")
                        # エラー時はst.rerun()を呼ばない（無限ループ防止）
                    except Exception as e:
                        # エラー時はセッション状態を復元
                        st.session_state.conversation_context = temp_context
                        st.session_state.pending_questions = temp_questions
                        st.session_state.question_responses = temp_responses
                        
                        # 質問形式の応答の可能性をチェック
                        if 'raw_toon_text' in locals() and raw_toon_text:
                            try:
                                client = LLMClient()
                                if client.is_question_response(raw_toon_text):
                                    # 質問回数の上限チェック
                                    st.session_state.question_count += 1
                                    if st.session_state.question_count >= MAX_QUESTION_COUNT:
                                        st.error(f"質問回数が上限（{MAX_QUESTION_COUNT}回）に達しました。セッションをリセットしてください。")
                                        st.session_state.conversation_context = None
                                        st.session_state.pending_questions = None
                                        st.session_state.question_responses = []
                                        st.session_state.question_count = 0
                                    else:
                                        st.session_state.conversation_context = combined_prompt
                                        st.session_state.pending_questions = raw_toon_text
                                        st.session_state.question_responses = []
                                        st.info(f"LLMから質問がありました。回答を入力してください。（質問回数: {st.session_state.question_count}/{MAX_QUESTION_COUNT}）")
                                        st.rerun()
                            except:
                                pass
                        
                        st.error(f"エラーが発生しました: {e}")
                        # エラー時はst.rerun()を呼ばない（無限ループ防止）
                else:
                    st.warning("回答を入力してください。")
        
        with col_cancel:
            if st.button("キャンセル", use_container_width=True):
                # セッション状態をリセット
                st.session_state.conversation_context = None
                st.session_state.pending_questions = None
                st.session_state.question_responses = []
                st.session_state.question_count = 0  # 質問回数もリセット
                st.rerun()
        
        st.divider()
    
    # 差分追記モードの選択
    append_mode = st.checkbox(
        "既存TOONファイルに差分追記（LOG）",
        help="チェックすると、既存のTOONファイルに新しいノードとエッジを追加します。"
    )
    
    # 部分フロー生成モードの選択
    partial_mode = st.checkbox(
        "部分フロー生成モード（推奨）",
        value=True,
        help="チェックすると、主要なルートのみを生成します。全ルートを含む複雑なフローは避けます。"
    )
    
    user_prompt = st.text_area(
        "どのようなプロセスを可視化したいですか？", 
        placeholder="例：ハードウェアの故障診断手順をフローにして",
        help="自然言語で入力するとLLMがTOON形式を生成し、フローチャートを更新します。",
        height=150
    )
    
    if st.button("フローを生成", type="primary", use_container_width=True):
        if user_prompt:
            progress_bar = st.progress(0)
            status_text = st.empty()
            status_text.info("LLMがフローを設計中...（最大2分かかる場合があります）")
            progress_bar.progress(10)
            
            raw_toon_text = ""
            try:
                # LLMとの通信
                client = LLMClient()
                # 差分追記モードの場合は既存のFlowchartをコンテキストとして渡す
                context_flowchart = current_flow if append_mode else None
                
                # 部分フロー生成モードの場合、プロンプトに追加指示を付与
                enhanced_prompt = user_prompt
                if partial_mode:
                    enhanced_prompt = user_prompt + "\n\n【重要】主要なルートのみを生成してください。全ルートを含む必要はありません。ノード数は30個以下、エッジ数は50個以下にしてください。"
                
                raw_toon_text = client.generate_flow(enhanced_prompt, context_flowchart)
                progress_bar.progress(100)
                status_text.empty()
                
                # 質問形式の応答かチェック
                if client.is_question_response(raw_toon_text):
                    # 質問回数の上限チェック
                    st.session_state.question_count += 1
                    if st.session_state.question_count >= MAX_QUESTION_COUNT:
                        st.error(f"質問回数が上限（{MAX_QUESTION_COUNT}回）に達しました。セッションをリセットしてください。")
                        st.session_state.conversation_context = None
                        st.session_state.pending_questions = None
                        st.session_state.question_responses = []
                        st.session_state.question_count = 0
                    else:
                        # 質問形式の応答の場合、セッション状態に保存
                        st.session_state.conversation_context = user_prompt
                        st.session_state.pending_questions = raw_toon_text
                        st.session_state.question_responses = []
                        st.session_state.append_mode_for_question = append_mode  # 差分追記モード設定を保存
                        st.info(f"LLMから質問がありました。回答を入力してください。（質問回数: {st.session_state.question_count}/{MAX_QUESTION_COUNT}）")
                        st.rerun()
                else:
                    # 出力サイズの検証
                    is_valid, validation_message = client.validate_output_size(raw_toon_text)
                    if not is_valid:
                        st.warning(validation_message)
                        st.info("主要なルートのみを生成するか、フローを分割することを検討してください。")
                    
                    # TOON形式のパース
                    new_flow = TOONParser.parse(raw_toon_text)
                    
                    # 論理の穴検知を適用
                    new_flow = new_flow.apply_logic_gap_detection()
                    
                    # 差分追記モードの場合
                    if append_mode:
                        merged_flow = history_mgr.append_toon_log(session_name, new_flow)
                        st.session_state.history.append(merged_flow)
                        st.success(f"'{session_name}' のTOONファイルに差分を追記しました")
                    else:
                        # 通常モード：履歴に追加
                        st.session_state.history.append(new_flow)
                    
                    # 成功時のみ質問回数をリセット
                    st.session_state.question_count = 0
                    st.rerun()
            except LLMAPIError as e:
                # LLM APIエラー
                st.error(f"LLM APIエラー: {e}")
                st.info("Ollamaが起動しているか、モデルがインストールされているか確認してください。")
                # エラー時はst.rerun()を呼ばない（無限ループ防止）
            except TOONParseError as e:
                # TOON形式のパースエラー
                # 質問形式の応答の可能性をチェック
                if 'raw_toon_text' in locals() and raw_toon_text:
                    client = LLMClient()
                    if client.is_question_response(raw_toon_text):
                        # 質問回数の上限チェック
                        st.session_state.question_count += 1
                        if st.session_state.question_count >= MAX_QUESTION_COUNT:
                            st.error(f"質問回数が上限（{MAX_QUESTION_COUNT}回）に達しました。セッションをリセットしてください。")
                            st.session_state.conversation_context = None
                            st.session_state.pending_questions = None
                            st.session_state.question_responses = []
                            st.session_state.question_count = 0
                        else:
                            # 質問形式の応答だった場合、セッション状態に保存
                            st.session_state.conversation_context = user_prompt
                            st.session_state.pending_questions = raw_toon_text
                            st.session_state.question_responses = []
                            st.info(f"LLMから質問がありました。回答を入力してください。（質問回数: {st.session_state.question_count}/{MAX_QUESTION_COUNT}）")
                            st.rerun()
                    else:
                        # 本当にパースエラーの場合
                        st.error(f"TOON形式の解析に失敗しました: {e}")
                        with st.expander("🔍 LLMの生出力（デバッグ用）", expanded=True):
                            st.info("以下のテキストをTOON形式として解釈しようとしましたが、失敗しました。")
                            st.code(raw_toon_text)
                else:
                    st.error(f"TOON形式の解析に失敗しました: {e}")
                # エラー時はst.rerun()を呼ばない（無限ループ防止）
            except FlowchartValidationError as e:
                # Flowchartバリデーションエラー（警告として表示、自動修正を試行）
                st.warning(f"フローチャートの検証で問題を検出しました: {e}")
                st.info("論理の穴検知で自動修正を試行します。")
                # 自動修正を試行（既にapply_logic_gap_detectionが適用されているが、再度試行）
                try:
                    if 'new_flow' in locals():
                        corrected_flow = new_flow.apply_logic_gap_detection()
                        st.session_state.history.append(corrected_flow)
                        st.session_state.question_count = 0  # 成功時は質問回数をリセット
                        st.success("自動修正が完了しました。")
                        st.rerun()
                except Exception as correction_error:
                    st.error(f"自動修正に失敗しました: {correction_error}")
                    # エラー時はst.rerun()を呼ばない（無限ループ防止）
            except ValueError as e:
                # その他のValueError（モデル応答エラーなど）
                st.error(f"エラーが発生しました: {e}")
                # エラー時はst.rerun()を呼ばない（無限ループ防止）
            except Exception as e:
                # 予期しないエラー
                st.error(f"予期しないエラーが発生しました: {e}")
                # デバッグ用：エラー時に生出力を確認できるエクスパンダーを表示
                if 'raw_toon_text' in locals() and raw_toon_text:
                    # 質問形式の応答の可能性をチェック
                    try:
                        client = LLMClient()
                        if client.is_question_response(raw_toon_text):
                            # 質問回数の上限チェック
                            st.session_state.question_count += 1
                            if st.session_state.question_count >= MAX_QUESTION_COUNT:
                                st.error(f"質問回数が上限（{MAX_QUESTION_COUNT}回）に達しました。セッションをリセットしてください。")
                                st.session_state.conversation_context = None
                                st.session_state.pending_questions = None
                                st.session_state.question_responses = []
                                st.session_state.question_count = 0
                            else:
                                # 質問形式の応答だった場合、セッション状態に保存
                                st.session_state.conversation_context = user_prompt
                                st.session_state.pending_questions = raw_toon_text
                                st.session_state.question_responses = []
                                st.info(f"LLMから質問がありました。回答を入力してください。（質問回数: {st.session_state.question_count}/{MAX_QUESTION_COUNT}）")
                                st.rerun()
                    except:
                        pass
                    
                    with st.expander("🔍 LLMの生出力（デバッグ用）", expanded=True):
                        st.info("以下のテキストをTOON形式として解釈しようとしましたが、失敗しました。")
                        st.code(raw_toon_text)
                # エラー時はst.rerun()を呼ばない（無限ループ防止）
        else:
            st.warning("指示を入力してください。")

with col_flow:
    st.subheader("📊 フローチャート")
    # Mermaid描画処理
    mermaid_code = current_flow.to_mermaid()
    b64_mermaid = base64.b64encode(mermaid_code.encode('utf-8')).decode('utf-8')

    html_path = Path("frontend/index.html")
    if html_path.exists():
        html_content = html_path.read_text(encoding='utf-8')
        # ノード選択用のコンポーネント（メッセージ受信用）
        components.html(
            f"""
            {html_content}
            <script>
                window.onload = () => {{
                    window.postMessage({{ 
                        type: "render", 
                        base64Code: "{b64_mermaid}" 
                    }}, "*");
                }};
                
                // Streamlitへのメッセージ送信を設定
                window.addEventListener('message', function(event) {{
                    // ノード選択メッセージをStreamlitに送信
                    if (event.data && event.data.type === 'node_selected') {{
                        // Streamlitのコンポーネント通信プロトコルに従って送信
                        window.parent.postMessage({{
                            type: 'streamlit:setComponentValue',
                            value: event.data.nodeId
                        }}, '*');
                    }}
                }});
            </script>
            """,
            height=800,
            scrolling=True
        )
        
        # コンポーネントからメッセージを受信（Streamlitの仕様に従う）
        # 注意: components.htmlは直接メッセージを受信できないため、
        # JavaScriptから送信されたメッセージを処理する別の方法を使用
    else:
        st.error("frontend/index.html が見つかりません")

with col_source:
    st.subheader("📄 TOON形式（Source）")
    
    # TOON形式の生データを生成
    toon_text = current_flow.to_toon_format()
    
    with st.expander("TOON形式を表示", expanded=True):
        st.code(toon_text, language="markdown")
    
    # ダウンロードボタン
    st.download_button(
        label="📥 TOONファイルをダウンロード",
        data=toon_text,
        file_name=f"{session_name}_toon.md",
        mime="text/markdown"
    )
    
    # ノード選択セクション
    st.divider()
    st.subheader("🎯 ノード選択（部分変更用）")
    
    # 選択モード
    selection_mode = st.radio(
        "選択方法",
        ["UI選択", "テキスト入力", "両方"],
        horizontal=True,
        key="selection_mode_radio"
    )
    
    # テキスト入力
    if selection_mode in ["テキスト入力", "両方"]:
        node_ids_input = st.text_input(
            "ノードID（カンマ区切り）",
            placeholder="例: task1, task2, decision1",
            help="変更したいノードのIDを入力してください。startとendは選択できません。",
            key="node_ids_input"
        )
        
        if node_ids_input:
            selected_ids = [id.strip() for id in node_ids_input.split(",")]
            # startとendを除外
            selected_ids = [id for id in selected_ids 
                          if id not in ["start", "node_end"]]
            # 存在チェック
            valid_ids = [id for id in selected_ids 
                        if id in [n.id for n in current_flow.nodes]]
            invalid_ids = [id for id in selected_ids if id not in valid_ids]
            
            if invalid_ids:
                st.warning(f"存在しないノードID: {invalid_ids}")
            
            # セッション状態を更新（既存の選択に追加）
            if 'selected_node_ids' not in st.session_state:
                st.session_state.selected_node_ids = []
            # テキスト入力で指定されたIDを追加（重複を避ける）
            for node_id in valid_ids:
                if node_id not in st.session_state.selected_node_ids:
                    st.session_state.selected_node_ids.append(node_id)
    
    # UI選択からのメッセージ処理
    # Streamlitのcomponents.htmlは直接メッセージを受信できないため、
    # クエリパラメータを使用してノード選択を処理
    query_params = st.query_params
    if 'selected_node' in query_params:
        selected_node_id = query_params['selected_node']
        if selected_node_id and selected_node_id not in ["start", "node_end"]:
            if selected_node_id in [n.id for n in current_flow.nodes]:
                if 'selected_node_ids' not in st.session_state:
                    st.session_state.selected_node_ids = []
                if selected_node_id not in st.session_state.selected_node_ids:
                    st.session_state.selected_node_ids.append(selected_node_id)
        # クエリパラメータをクリアして再読み込みを防ぐ
        st.query_params.clear()
        if 'selected_node' in query_params:
            st.rerun()
    
    # ノード一覧から選択（UI選択の代替方法）
    if selection_mode in ["UI選択", "両方"]:
        st.markdown("**ノード一覧から選択:**")
        # 現在のフローのノード一覧を表示（startとendを除く）
        available_nodes = [n for n in current_flow.nodes 
                          if n.id not in ["start", "node_end"]]
        
        if available_nodes:
            # ノードをチェックボックスで選択可能にする
            node_dict = {f"{n.id} ({n.label})": n.id for n in available_nodes}
            selected_node_labels = st.multiselect(
                "ノードを選択（複数選択可能）",
                options=list(node_dict.keys()),
                default=[label for label, node_id in node_dict.items() 
                        if node_id in st.session_state.get('selected_node_ids', [])],
                key="node_multiselect"
            )
            
            # 選択されたノードIDをセッション状態に反映
            if 'selected_node_ids' not in st.session_state:
                st.session_state.selected_node_ids = []
            
            # 選択されたノードIDを更新
            selected_node_ids_from_ui = [node_dict[label] for label in selected_node_labels]
            # 既存の選択とマージ（重複を避ける）
            current_selected = set(st.session_state.selected_node_ids)
            new_selected = set(selected_node_ids_from_ui)
            st.session_state.selected_node_ids = list(current_selected | new_selected)
        else:
            st.info("選択可能なノードがありません。")
    
    # 選択されたノードの表示
    if 'selected_node_ids' in st.session_state and st.session_state.selected_node_ids:
        st.info(f"選択されたノード: {', '.join(st.session_state.selected_node_ids)}")
        
        # 選択解除ボタン
        col_clear1, col_clear2 = st.columns(2)
        with col_clear1:
            if st.button("選択をクリア", key="clear_selection"):
                st.session_state.selected_node_ids = []
                st.rerun()
        with col_clear2:
            if st.button("最後の選択を削除", key="remove_last_selection"):
                if st.session_state.selected_node_ids:
                    st.session_state.selected_node_ids.pop()
                st.rerun()
        
        # 部分変更の入力
        change_instruction = st.text_area(
            "変更指示",
            placeholder="例: このノードのラベルを「確認処理」に変更してください",
            height=100,
            key="change_instruction"
        )
        
        if st.button("選択範囲を変更", type="primary", key="apply_partial_change"):
            if not change_instruction.strip():
                st.error("変更指示を入力してください。")
            else:
                try:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    status_text.info("選択範囲を変更中...（最大2分かかる場合があります）")
                    progress_bar.progress(10)
                    
                    # 1. 選択範囲を抽出
                    selected_node_ids = st.session_state.selected_node_ids
                    partial_flowchart = FlowExtractor.extract_node_range(
                        current_flow, 
                        selected_node_ids
                    )
                    progress_bar.progress(30)
                    
                    if not partial_flowchart.nodes:
                        st.error("選択されたノードが見つかりませんでした。")
                        progress_bar.empty()
                        status_text.empty()
                    else:
                        # 2. LLMに部分変更を依頼
                        client = LLMClient()
                        status_text.info("LLMが変更を生成中...")
                        progress_bar.progress(50)
                        changed_toon = client.generate_partial_change(
                            change_instruction,
                            partial_flowchart,
                            current_flow
                        )
                        progress_bar.progress(70)
                        
                        # 3. 変更結果をパース
                        status_text.info("変更結果を解析中...")
                        parser = TOONParser()
                        changed_partial = parser.parse(changed_toon)
                        progress_bar.progress(85)
                        
                        # 4. 全体フローにマージ
                        status_text.info("フローをマージ中...")
                        merged_flowchart = FlowMerger.merge_partial_change(
                            current_flow,
                            changed_partial,
                            selected_node_ids
                        )
                        progress_bar.progress(95)
                        
                        # 5. 履歴に追加
                        history_mgr.append_toon_log(
                            session_name,
                            merged_flowchart
                        )
                        
                        # 6. セッション状態を更新
                        st.session_state.history = history_mgr.load_history(session_name)
                        st.session_state.selected_node_ids = []  # 選択をクリア
                        
                        progress_bar.progress(100)
                        status_text.empty()
                        progress_bar.empty()
                        st.success("選択範囲の変更が完了しました！")
                        st.rerun()
                            
                except LLMAPIError as e:
                    st.error(f"LLM APIエラー: {str(e)}")
                except TOONParseError as e:
                    st.error(f"TOON解析エラー: {str(e)}")
                except FlowchartValidationError as e:
                    st.error(f"フローチャート検証エラー: {str(e)}")
                except Exception as e:
                    st.error(f"予期しないエラーが発生しました: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())

with st.sidebar.expander("現在のMermaidコードを表示"):
    st.code(mermaid_code)