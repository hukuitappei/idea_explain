from __future__ import annotations

from core import config as app_config


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
        st.error(
            "OAuth(OIDC) が未設定です。Streamlit Cloud の Secrets に `[auth]` を設定してください。"
        )
        st.stop()

    # Streamlit >= 1.53 provides st.user / st.login / st.logout
    if not hasattr(st, "user") or not hasattr(st, "login") or not hasattr(st, "logout"):
        st.error("このStreamlit環境は `st.login()` / `st.user` / `st.logout()` に対応していません。Streamlitを更新してください。")
        st.stop()

    if not st.user.is_logged_in:
        st.title("Login required")
        st.write("このアプリを利用するにはログインが必要です。")
        st.button("Log in", on_click=st.login)
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

