"""ntucool — 自動擷取 NTU COOL 課程資訊與檔案的工具。

NTU COOL 是 Canvas LMS，因此本套件全部透過官方 `/api/v1` REST API 存取，
不解析網頁、不模擬登入，只需要一個個人存取權杖（access token）。
"""

__version__ = "1.0.0"
