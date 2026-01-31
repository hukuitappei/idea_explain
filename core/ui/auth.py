from __future__ import annotations

import re

from core import config as app_config


def _validate_oidc_secrets_or_show_error(st) -> bool:
    """Validate st.secrets['auth'] without printing any secret values.

    Streamlit may redact st.login() errors, so we fail early with actionable hints.
    """
    try:
        auth = st.secrets.get("auth") or {}
    except Exception:
        auth = {}

    if not isinstance(auth, dict) or not auth:
        st.error("OAuth(OIDC) が未設定です。Streamlit Cloud の Secrets に `[auth]` を設定してください。")
        return False

    missing: list[str] = []
    for k in ("redirect_uri", "cookie_secret"):
        if not auth.get(k):
            missing.append(k)

    # Provider config: either in [auth] (single provider) or in [auth.<provider>]
    provider = None
    if any(auth.get(k) for k in ("client_id", "client_secret", "server_metadata_url")):
        provider = auth
    else:
        for _, v in auth.items():
            if isinstance(v, dict) and any(v.get(k) for k in ("client_id", "client_secret", "server_metadata_url")):
                provider = v
                break

    if provider is None:
        missing.extend(["client_id", "client_secret", "server_metadata_url"])
    else:
        for k in ("client_id", "client_secret", "server_metadata_url"):
            if not provider.get(k):
                missing.append(k)

    if missing:
        # Don't show values; show keys only.
        st.error(
            "OAuth(OIDC) の Secrets 設定が不完全です。`[auth]` に以下のキーが必要です:\n"
            f"- {', '.join(sorted(set(missing)))}\n\n"
            "特に redirect_uri は `https://<your-app>.streamlit.app/oauth2callback` と一致させてください。"
        )
        return False

    # ---- sanity checks (avoid redacted StreamlitAuthError) ----
    redirect_uri = str(auth.get("redirect_uri") or "").strip()
    cookie_secret = str(auth.get("cookie_secret") or "").strip()
    client_id = str((provider or {}).get("client_id") or "").strip()
    client_secret = str((provider or {}).get("client_secret") or "").strip()
    server_metadata_url = str((provider or {}).get("server_metadata_url") or "").strip()

    problems: list[str] = []

    # redirect_uri must end with oauth2callback
    if not redirect_uri.startswith("https://"):
        problems.append("redirect_uri は https:// で始めてください。")
    if not redirect_uri.endswith("/oauth2callback"):
        problems.append("redirect_uri は末尾を /oauth2callback にしてください。")

    # cookie secret length
    if len(cookie_secret) < 32:
        problems.append("cookie_secret は32文字以上のランダム文字列にしてください（推奨64以上）。")

    # Google client_id format (most common)
    if "google" in server_metadata_url and not re.search(r"\.apps\.googleusercontent\.com$", client_id):
        problems.append("Googleの client_id は末尾が .apps.googleusercontent.com の値です（例: 1234-xxxx.apps.googleusercontent.com）。")

    if client_secret.strip() == "":
        problems.append("client_secret が空です（Googleが発行した値を入れてください）。")

    # Obvious placeholders
    for key_name, value in (
        ("client_id", client_id),
        ("client_secret", client_secret),
        ("cookie_secret", cookie_secret),
    ):
        if value.upper().startswith("CHANGE_ME") or "<" in value or ">" in value:
            problems.append(f"{key_name} がテンプレのままです（実値を入れてください）。")

    if problems:
        st.error("OAuth(OIDC) の設定値が不正です。以下を修正してください:\n- " + "\n- ".join(problems))
        return False

    return True


def _login_callback(st) -> None:
    if not _validate_oidc_secrets_or_show_error(st):
        st.stop()
    try:
        st.login()
    except Exception:
        # Streamlit may redact auth errors; show actionable next steps.
        st.error(
            "ログイン開始に失敗しました。\n"
            "1) Streamlit Cloud の Secrets の [auth] 設定\n"
            "2) Google Cloud Console の Authorized redirect URIs\n"
            "が一致しているかを確認してください。"
        )
        st.stop()


def resolve_user_key_or_stop(st) -> str:
    """Resolve current user key (email) based on Streamlit OIDC settings.

    Returns:
        user_key (email) or "anonymous" when auth is disabled.
    """

    # Auto-enable auth when Streamlit OIDC is configured (fail-closed).
    require_auth = bool(app_config.REQUIRE_AUTH)
    try:
        auth_cfg_present = bool(st.secrets.get("auth"))
    except Exception:
        auth_cfg_present = False
    if auth_cfg_present:
        require_auth = True

    if not require_auth:
        return "anonymous"

    # Fail-closed: auth required but not configured
    if not auth_cfg_present:
        _validate_oidc_secrets_or_show_error(st)
        st.stop()

    # Streamlit >= 1.53 provides st.user / st.login / st.logout
    if not hasattr(st, "user") or not hasattr(st, "login") or not hasattr(st, "logout"):
        st.error("このStreamlit環境は `st.login()` / `st.user` / `st.logout()` に対応していません。Streamlitを更新してください。")
        st.stop()

    if not st.user.is_logged_in:
        st.title("Login required")
        st.write("このアプリを利用するにはログインが必要です。")
        # Validate secrets before calling st.login() to avoid redacted errors
        st.button("Log in", on_click=_login_callback, args=(st,))
        st.stop()

    user_email = (getattr(st.user, "email", "") or "").strip().lower()
    if not user_email:
        st.error("ログインユーザーの email を取得できません。OIDC設定で email スコープ/クレームを有効にしてください。")
        st.stop()

    # Optional allowlist
    if app_config.ALLOWED_EMAILS and user_email not in app_config.ALLOWED_EMAILS:
        st.error("このアカウントは許可されていません。")
        st.stop()

    if app_config.ALLOWED_EMAIL_DOMAINS:
        domain = user_email.split("@")[-1] if "@" in user_email else ""
        if domain not in app_config.ALLOWED_EMAIL_DOMAINS:
            st.error("このドメインのアカウントは許可されていません。")
            st.stop()

    # Logout button (sidebar)
    st.sidebar.button("Log out", on_click=st.logout, use_container_width=True)
    return user_email

