---
name: blind-glasses-modification-safeguard
description: "WHAT: 規範 AI 修改程式碼時的安全防護機制，防止 AI 擅自刪除既有功能、大幅度重構或未經確認覆蓋核心架構。 WHEN: 準備進行大範圍程式碼修改、整合功能，或提出實作計畫 (Implementation Plan) 時觸發。"
---

# Modification Safeguard & Anti-Hallucination Protocol

## Objective
此技能的目的是設立一道「防呆與防爆」的安全防線。為了避免系統「自動執行 (Auto-proceed)」或 AI 為了便宜行事而擅自刪除專案原有的功能（例如過往發生的：UI 被截斷、GPS 與地圖被移除、藍牙核心被亂改），AI 必須嚴格遵守以下防護機制。

## Strict Safeguard Rules

1. **增量修改原則 (Incremental Changes Only)**
   - 預設情況下，**只能新增**功能，**絕對禁止刪除或簡化**原有的業務邏輯與 UI 畫面（除非使用者明確授權與要求）。
   - 在合併不同版本的程式碼時，必須以「保留雙方所有功能」為最高指導原則。絕對不能因為「覺得原始碼太長或太複雜」就擅自生一個簡化版或包含假資料的閹割版本。

2. **核心架構鎖定 (Core Architecture Lockdown)**
   - 專案的底層連線機制（如：藍牙連線 `BleManager`、通訊協定 UUID）、資料流架構，若未經使用者的**明確指示**，絕對不可擅自重構、替換為 Singleton 或改變原本的初始化邏輯。

3. **變更透明化與雙重檢核 (Transparency & Self-Check)**
   - 當提出 Implementation Plan 時，如果涉及**檔案覆蓋**或**結構性變更**，必須在計畫中**顯著標示（使用 `[!WARNING]` 或 `[!CAUTION]` 警告區塊）**哪些原有的程式碼會被影響。
   - 即使 IDE 觸發了自動執行 (Auto-proceed)，AI 在覆寫檔案或取代程式碼之前，都必須強制進行自我檢核：「這項改動，會不會導致舊有功能消失？」如果有疑慮，寧可不改。

4. **主動防禦機制 (Proactive Pause)**
   - 如果發現使用者的需求與目前的專案架構有嚴重衝突，或是整合的風險極高，AI **必須放棄自動執行，主動停止並提出警告**，向使用者說明風險，絕對不可以直接硬改或是默默把衝突的部分刪除。
