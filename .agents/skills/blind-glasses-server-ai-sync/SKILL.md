---
name: blind-glasses-server-ai-sync
description: "WHAT: 當修改到伺服器核心 (排除 line_bot_router.py 與 App) 時，需生成給朋友的 AI 複製用說明。 WHEN: 完成任何伺服器後端程式碼的修改後觸發。"
---

> [!IMPORTANT]
> 這是專案的協作規範：因為後端伺服器 (Server) 主要是由使用者的朋友負責維護本地端，所以我們這裡的任何後端修改，都必須讓對方能夠輕鬆同步。

# Scope (適用範圍)
- **適用**：`main.py`, `monitor_api.py`, `navigation.py`, `event_engine.py` 等伺服器後端核心程式碼。
- **排除**：`line_bot_router.py` (LINE Bot 路由)、`App1/` (Android App 前端)。修改這些排除範圍內的檔案時 **不需要** 觸發此 Skill。

# Procedure (執行流程)
當你在對「適用範圍」的檔案進行了程式碼的修改、新增或刪除，並準備總結回報給使用者時，請務必在回覆的最後，獨立出一個明確的區塊，提供一段「**給對方 AI 的指示 prompt**」。

### Prompt 撰寫規定：
1. **角色設定**：語氣必須是「使用者的朋友向自己的 AI 助手下達的指令」。
2. **內容要素**：
   - 明確指出要修改的**檔案名稱** (例如 `main.py`)。
   - 簡單說明**修改原因** (背景脈絡)。
   - 給出**明確的程式碼片段**，並告訴對方的 AI 該把這段程式碼加在哪裡，或是替換掉哪一個舊的 function。
3. **格式化**：請用 Markdown 的文字區塊包裝起來，讓使用者可以點擊一鍵複製。

# Example Output Format (輸出範例)
您可以參考以下格式輸出給使用者：

***

### 📋 請複製以下內容傳給您朋友：
```text
請幫我修改 `main.py` 裡面的 `api_get_status` 函數。

【背景說明】
因為前端 App 需要一併取得最新的 GPS 定位資訊...

【實作要求】
請將原本的 `api_get_status` 函數替換為以下程式碼：
\`\`\`python
@app.get("/api/status")
async def api_get_status() -> dict:
    ...
\`\`\`
```
***
