---
name: blind-glasses-firmware-api-context
description: "WHAT: 提供前端依賴的 firmware 與 API 事實查證流程，避免誤判。 WHEN: 進行前端資料串接前，或使用者提到韌體 API、藍牙BLE指令、裝置狀態時觸發。"
---

> [!CAUTION]
> **關於 FIRMWARE 代碼的編輯權限**
> 1. Firmware 由使用者的朋友負責維護。
> 2. **允許同步**：根據 `blind-glasses-pre-task-repo-check` 指令執行 `git pull` 同步最新規格是必要的。
> 3. **禁止編輯**：禁止對 `firmware_reference` 資料夾下的檔案進行任何手動修改或編輯。
> 4. **處理需求**：若需求涉及韌體更動，請在 App 端實作對應邏輯，並產出「韌體修改建議清單」交給使用者轉達給其朋友。

# Source of Truth
- 優先依據本地實際程式碼 (Workspace 內的 codebase)
- Firmware Repo URL: <https://github.com/YuQian081122/blind-glasses-firmware>

# Capability Matrix
- BLE 快速連線：支援指令傳遞與快速狀態交換（不包含耳機音訊串流）。
- 模式切換：僅支援 general / light / item_search 三種模式。
- API 路徑與用途：[僅列出已從本地程式碼查證確認的 Endpoints]

# Verification Procedure
遇到需求提及新欄位或新 endpoint：
1. 使用 `grep_search` 搜尋本地專案。
2. 閱讀相關的 firmware / backend 檔案確認協定。
3. 若沒有相關程式碼，停止猜測並依據下方條件回報。

# Ambiguity Handling
無法確認時，必須輸出：
- 已確認：[列出確實找到的規格]
- 未確認：[列出未確認的規格]
- 需要使用者補充：[請使用者提供文件或程式碼路徑]

# Safe Assumptions
- 允許：假設 API 失敗時會有 HTTP 錯誤碼 或 Status Code。
- 禁止：禁止把 BLE 快速連線誤寫成藍牙耳機音訊串流能力 (A2DP/HFP)。
- 禁止：禁止直接修改 firmware 協定定義（除非使用者明確要求）。
- 禁止：不可杜撰不存在的 API、欄位或 BLE 指令。

# Terminology Lock
請固定使用以下術語：
- BLE 快速連線
- 模式切換（general / light / item_search）
- 裝置狀態
