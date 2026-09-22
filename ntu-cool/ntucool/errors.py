"""本套件共用的例外型別。"""


class NtuCoolError(Exception):
    """所有本套件錯誤的基底。"""


class ConfigError(NtuCoolError):
    """設定缺漏或不合法（例如沒有權杖）。"""


class ApiError(NtuCoolError):
    """API 回應非 2xx。"""

    def __init__(self, message, *, status=None, url=None, body=None):
        super().__init__(message)
        self.status = status
        self.url = url
        self.body = body


class AuthError(ApiError):
    """權杖無效或過期（401）。"""


class ForbiddenError(ApiError):
    """沒有權限讀取此資源（403），例如課程關閉了「檔案」分頁。"""


class NotFoundError(ApiError):
    """資源不存在（404）。"""


class RateLimitError(ApiError):
    """被 Canvas 限流。"""
