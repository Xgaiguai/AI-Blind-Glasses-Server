---
name: blind-glasses-frontend-qa
description: "WHAT: 規範前端驗證與回歸測試流程，確保產出品質。 WHEN: 完成任意前端實作、API 串接後，或使用者要求驗證與 QA 時觸發。"
---

# Test Checklist
可直接勾選：
- [ ] 基本渲染是否正常
- [ ] API 成功 / 失敗 / 逾時的處理與顯示
- [ ] loading / error / empty state 狀態是否明確
- [ ] 模式切換 UI 與狀態是否同步更新
- [ ] BLE 快速連線提示流程是否完整
- [ ] 響應式介面（手機 / 桌機）適應性

# Regression Focus
重點測試容易壞的區塊：
1. 狀態同步 (State Sync 失敗或競態條件)
2. 錯誤提示 (有沒有被吃掉或沒清除)
3. 重試流程 (斷線或 Timeout 後的 Retry 行為)

# Observability
- 需要包含清楚的 console log（如連接中、模式切換中）。
- UI 上需要能顯示明確的錯誤或提示訊息給終端用戶。

# Done Criteria
- 什麼條件下才算完成：所有 Checklist 皆滿足，且沒有在終端機報錯。不可只靠「看起來可以」就當作完成。

# Report Format
測試完畢後輸出：
- 測試結果 (Pass/Fail)
- 未過項目 (Failed Items)
- 風險等級 (High/Medium/Low)
- 建議修正順序 (Recommended Fix steps)
