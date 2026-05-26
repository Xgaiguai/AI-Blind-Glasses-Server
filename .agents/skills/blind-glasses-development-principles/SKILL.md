---
name: blind-glasses-development-principles
description: "WHAT: 規範開發與修改程式碼時的原則：維持簡化、模組化、邏輯清晰，避免一次性產出龐雜的程式碼。 WHEN: 在進行任何程式碼撰寫、修改或架構規劃時觸發。"
---

# Code Simplification & Clear Logic Protocol

## Objective
確保專案（特別是 Android App）在開發過程中，程式碼的修改都能保持簡化、模組化與邏輯清晰。避免像過往一樣產生單一且龐雜的巨大檔案（如過去幾萬字的 `MainActivity.kt`），確保每次的迭代都易於閱讀、維護與除錯。

## Core Principles

1. **單一職責原則 (Single Responsibility)**
   - 每個 Class、Function 或 Composable 應該只負責一件事情。
   - 不要把 UI 渲染、硬體連線（如藍牙）、生命週期管理全部塞在同一個區塊裡。將它們拆分到適當的 ViewModel、Repository 或獨立的管理類別中。

2. **模組化與重構思維 (Modular & Refactoring Mindset)**
   - 即使一次進行多個檔案的修改，重點在於「邏輯是否解耦」。
   - 不要把所有功能塞回同一個檔案。例如：要加入前景服務，就把 Service 獨立出來，藍牙邏輯獨立成 Singleton，ViewModel 單純作為橋樑。一次做完沒問題，只要架構清晰即可。

3. **邏輯清晰與架構分明 (Clear Logic)**
   - 程式邏輯必須直觀，避免過度嵌套（Nested）的條件判斷。
   - 使用清楚且具描述性的變數與函數命名。
   - 嚴格遵守專案既有的架構（如 Android 的 MVVM 模式），讓 UI 層單純處理畫面顯示，商業與硬體邏輯交給後端控制層。

4. **無障礙功能的優雅整合 (Integrate Accessibility Gracefully)**
   - 未來在將視障者需要的核心功能（TTS 語音播報、實體按鍵攔截、前景常駐服務）加回新架構時，必須以「模組化」的方式進行。
   - 例如：建立專屬的 `TtsManager` 來處理語音，而不是把發聲邏輯散落在 UI 元件中。

## Strict Rules
- **拒絕大雜燴**：如果發現接下來的修改會讓單一檔案塞入過多邏輯，請**主動暫停**，並先將邏輯拆分成獨立的方法或類別。
- **邏輯至上**：不需要為了「小步快跑」而強迫把一件有連貫性的任務硬切成好幾次詢問。只要你能確保「架構漂亮、檔案職責分明」，就可以一次把完整的功能（如：完整前景服務綁定）實作到位。
