"""TOON処理用のカスタム例外クラス"""


class TOONError(Exception):
    """TOON処理の基底例外"""
    pass


class TOONParseError(TOONError):
    """TOON形式のパースエラー"""
    pass


class LLMAPIError(TOONError):
    """LLM API呼び出しエラー"""
    pass


class FlowchartValidationError(TOONError):
    """Flowchartバリデーションエラー"""
    pass
