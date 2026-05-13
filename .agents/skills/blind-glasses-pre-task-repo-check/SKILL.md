---
name: blind-glasses-pre-task-repo-check
description: "WHAT: 在執行任務前，強制先刷新並檢視遠端 blind-glasses 儲存庫最新狀態。 WHEN: 在每次接收到使用者新需求，準備開始執行任何任務前觸發。"
---

# Auto-Sync & Inspect Repo Protocol

## Objective
為了避免因為韌體 (Firmware) 或其他相關端點有更新，導致我們開發的 App 發生規格不一致的情形。每次執行任務前，必須先自動從遠端確認 <https://github.com/YuQian081122/blind-glasses-firmware> 的最新狀況。

## Execution Steps

1. **同步本地韌體專案並檢視狀態**
   - 請使用 `run_command` 工具，切換目錄（Cwd）至本地的韌體參考資料夾 `d:\API server\server4\firmware_reference`。
   - 在該目錄下執行 `git pull` 指令，確保本地擁有一份最新且同步的韌體與協定程式碼。
   - 執行完 pull 後，可以利用 `git log -n 3` 檢視最近的 Commit，或是閱讀變更的檔案，來確認最新的更新重點。

2. **檢視與分析異動**
   - 特別關注任何與藍牙 BLE 協定 (UUIDs、通訊指令)、API Endpoint、ESP32 Firmware 或系統架構有關的更動。
   - 評估這些遠端專案的更新是否會影響當前或接下來要執行的任務。

3. **回報與接續任務**
   - 簡單向使用者回報遠端專案的檢視結果（例如：「已確認遠端韌體庫無重大更新」或「發現遠端有新的 BLE 指令，將一併考量」）。
   - 完成檢視後，才能正式著手進行使用者原本指派的任務。

## Strict Rules
- **必備前置動作**：不可略過此檢查步驟，否則可能會因規格不同步寫出無法互動的程式碼。
- **確認衝突**：如果發現遠端規格與本地邏輯有衝突，請先與使用者確認，不要自行盲目覆蓋或修改本地現有且運行正常的程式碼。
