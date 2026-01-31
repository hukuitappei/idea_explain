# 公開運用ガイド（Streamlit Cloud + OAuth + Supabase(Postgres) + OpenAI互換）

このリポジトリは「**公開運用**」を前提に、以下を実装済みです。
- OAuth(OIDC) ログイン必須（`st.login()` / `st.user` / `st.logout()`）
- 永続化：Supabase(Postgres) への保存（未設定時はローカルにフォールバックし警告）
- 保存方針：**最小保存（Flow/TOONのみ）**（プロンプト本文のDB保存はしない）
- データ保持：**30日**（`RETENTION_DAYS`）
- 乱用対策：**1日20回/ユーザー(email)**（`DAILY_LLM_REQUEST_LIMIT`）
- LLM：開発=Ollama、本番=OpenAI互換 API（`LLM_BACKEND`）

---

## 1. Streamlit Cloud（Community Cloud）でのOAuth(OIDC)設定

Streamlitの公式ドキュメントに従って、OIDCを設定してください。  
参考: [User authentication and information](https://docs.streamlit.io/develop/concepts/connections/authentication)

### 必須ポイント
- **redirect URI** は `https://<your-app>.streamlit.app/oauth2callback`
- `cookie_secret` は十分長いランダム文字列
- **email クレーム**を返す設定にしてください（本アプリは `st.user.email` を必須として使います）

---

## 2. Supabase(Postgres) の準備（永続ストレージ）

### 目的
Streamlit Cloud のローカルファイルは永続性が信用できないため、**DBへ保存**します。

### 必要なもの
- Supabase の **Postgres接続文字列（DSN）**
  - 例: `postgresql://postgres:<password>@<host>:5432/postgres?sslmode=require`

#### 接続エラーの典型（Cannot assign requested address）
ログに IPv6 アドレス（例: `2406:...`）が出て `Cannot assign requested address` になる場合、実行環境が IPv6 で外向き接続できていません。
その場合は以下を試してください。
- Supabase の **Connection string（ホスト名）** をそのまま使う（IPv6直書きにしない）
- Supabase の **Pooler（接続プーラー）** を使う（UIにある pooler の DSN / port 6543 を利用）
  - 接続先ホストがIPv4で解決しやすく、Streamlit Cloudで安定します。

### DBスキーマ
アプリ起動時に **自動で `CREATE TABLE IF NOT EXISTS`** します（手動マイグレーション不要）。
- `user_sessions`（ユーザーごとのセッション/TOON保存）
- `llm_daily_usage`（レート制限カウンタ）

---

## 3. Streamlit Cloud の Secrets 設定（必須）

Streamlit Cloud の「Secrets」に、以下を設定してください。

`.streamlit/secrets.toml` の例:

```toml
[auth]
redirect_uri = "https://<your-app>.streamlit.app/oauth2callback"
cookie_secret = "CHANGE_ME_LONG_RANDOM_STRING"
client_id = "CHANGE_ME"
client_secret = "CHANGE_ME"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[openai]
api_key = "CHANGE_ME"
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"

[supabase]
db_url = "postgresql://postgres:<password>@<host>:5432/postgres?sslmode=require"
```

### allowlist（任意）
「公開運用」でも、まずは allowlist 推奨です（事故を防ぎます）。

環境変数（Streamlit Cloud の Secrets からも設定可能）:
- `ALLOWED_EMAILS`: `a@x.com,b@y.com`
- `ALLOWED_EMAIL_DOMAINS`: `example.com,example.org`

---

## 4. 環境変数（推奨）

最低限これだけは本番で固定してください。

- `PRODUCTION_MODE=true`
- `SESSION_STORE_BACKEND=auto`（推奨：DSNがあればpostgres、なければlocal）
- `LLM_BACKEND=auto`（推奨：OpenAIキーがあればopenai、なければollama）
- `RETENTION_DAYS=30`
- `DAILY_LLM_REQUEST_LIMIT=20`

補足:
- `REQUIRE_AUTH=true` を **明示推奨** です（誤設定で認証無し公開になる事故を防ぐ）。
  - ただし `[auth]` が Secrets に存在する場合は、アプリ側で自動的にログイン必須になります（fail-closed）。
- OpenAIのキーは `OPENAI_API_KEY` でも渡せますが、Streamlit Cloudでは Secrets の `[openai]` 推奨です。

---

## 5. 動作確認（最低限の手順）
1. Streamlit Cloud でアプリを起動
2. ログインできること（未ログインならログイン画面になること）
3. フロー生成 → 保存 → 画面リロード → セッション一覧から復元できること
4. 1日上限（デフォルト20回）を超えるとブロックされること

---

## 6. 既知の制約（公開運用の現実）
- Retention削除はアプリ起動時に走るため、**アクセスが全く無い期間は削除が遅延**します。  
  本気でやるなら、別途スケジューラ（Cron）でDB側の削除を回してください。
- OAuthは「認証」であって「認可」ではありません。公開にするなら allowlist / 管理者UIを用意してください。

---

## 7. 次の拡張（Gemini追加）
現状は OpenAI互換 `/v1/chat/completions` を本番前提にしています。  
Geminiは互換ではないため、`LLM_BACKEND=gemini` を追加して実装します（次フェーズ）。

