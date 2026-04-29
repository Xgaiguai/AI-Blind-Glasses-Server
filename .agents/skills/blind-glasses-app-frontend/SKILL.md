---
name: blind-glasses-app-frontend
description: "WHAT: 規範前端控制台（Web App）的開發流程，包含裝置狀態、模式切換與BLE連線。 WHEN: 當使用者要求開發、修改或驗證前端頁面、控制台、監控介面、模式切換或BLE配對流程時觸發。"
---

# Quick Start
1. 收到前端需求後，第一步先讀取 `blind-glasses-firmware-api-context` skill，並確認 API 與協定。
2. 不得假設任何 API 存在，需從本地 firmware / route 程式碼查證。

# Trigger Conditions
- 使用者提到「前端頁面」
- 使用者提到「控制台」
- 使用者提到「監控介面」
- 使用者提到「模式切換」
- 使用者提到「BLE 配對流程」

# Required Inputs
開發前必查資訊：
1. API 路徑 (Endpoint path)
2. 回應格式 (Response payload format)
3. 錯誤格式 (Error format)
4. 狀態欄位 (State fields)

# Workflow
- Step 1: 讀 firmware/api context 確認資訊。
- Step 2: 先做資訊架構（頁面區塊安排）。
- Step 3: 實作元件與資料流。
- Step 4: 接 API + 錯誤處理 + loading + 空狀態 (empty state)。
- Step 5: 執行驗證與交付。

# UI Scope (MVP)
- 裝置狀態卡：顯示 WiFi、BLE、模式、最近事件。
- 模式切換區：general / light / item_search。
- BLE 快速連線操作與提示區：引導裝置快速連線，包含失敗重試。
- API 測試面板：手動觸發測試用。
- MJPEG 預覽：僅在 firmware 確認可用時實作。

# Non-Goals
- 嚴格排除且不實作「A2DP/HFP 音訊耳機功能」。

# Output Contract
每次完成工作必回報：
1. 變更檔案清單
2. 測試步驟
3. 風險
4. 下一步建議
