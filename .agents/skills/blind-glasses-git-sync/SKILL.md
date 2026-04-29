---
name: blind-glasses-git-sync
description: "WHAT: 規範完成開發與確認功能無誤後的 Git 版控與推播流程。 WHEN: 當使用者確認功能正常，或主動要求把改動推送到 GitHub 時觸發。"
---

# Git Sync Process

當觸發此技能時，AI Agent 必須執行以下標準流程，協助使用者將專案的安全改動推送到遠端 GitHub：

## 1. 狀態檢查 (Status Check)
- 自動執行 `git status` 檢查目前有哪些檔案被修改、新增或刪除。
- 確保當前目錄在正確的 Git 儲存庫內。

## 2. 暫存變更 (Stage Changes)
- 執行 `git add .` (或依照使用者要求加入特定檔案)，將所有變更加入暫存區。

## 3. 撰寫提交訊息 (Commit)
- 分析先前的修改內容或 `git diff` 結果。
- 自動生成專業、簡潔且具有結構性的 Commit Message (預設使用繁體中文)。
- 常用格式：
  - `feat: [功能名稱] 新增...` (例如：新增 BLE 連線與 WiFi 帳密設定)
  - `fix: [問題名稱] 修正...` (例如：修正 MainActivity.kt 權限警告)
  - `docs: [文件名稱] 更新...` 
  - `refactor: [模組名稱] 重構...`
- 執行 `git commit -m "自動生成的 Commit Message"`。

## 4. 推送到遠端 (Push)
- 執行 `git push` 將本機分支推送到遠端 GitHub。
- 若遇到衝突 (Conflict) 或權限問題，需主動停止操作，並清楚指導使用者如何排解。

## 5. 結案報告 (Report)
推播完成後，必須向使用者輸出簡單的總結報告：
- ✅ 推播狀態 (Success / Fail)
- 📝 使用的 Commit Message
- 📂 主要異動的檔案清單 (摘要)
