# 導盲眼鏡功能補強 Roadmap

> 基於 ModelScope 公開導航用權重與現有伺服器模組的對照分析

---

## 現有模型權重盤點

| 檔案 | 用途 | 狀態 |
|------|------|------|
| `yoloe-11l-seg.pt` | YOLOv11-Large 語意分割（通用障礙/物件偵測） | **已接入** `yolomedia.py` → `item_search` |
| `yolo-seg.pt` | 導盲路徑/斑馬線分割模型 | **已接入** `vision_controller.py` → `BlindTileDetector`，也可作為 `yolomedia.py` fallback |
| `trafficlight.pt` | 紅綠燈/行人號誌專用偵測模型 | **已接入** `traffic_crossing.py` |
| `best.pt` | traffic_light 偵測模型 | **已接入** `vision_controller.py` overlay |
| `yolov8n.onnx` / `yolov8n.pt` | 通用 COCO 偵測（人/車/機車/狗） | **已接入** `yolo_detector.py` → 避障語音 |
| `hand_landmarker.task` | MediaPipe 手部姿態 | 備用，尚未接入 |

---

## 分層功能清單

### Tier 1：立即可做（僅靠現有權重 + 程式碼修改）

| # | 功能 | 對應模組 | 做法 |
|---|------|----------|------|
| 1 | **紅綠燈偵測強化** | `traffic_crossing.py` | 將 `trafficlight.pt` 設定為 `TRAFFIC_LIGHT_YOLO_MODEL_PATH`，啟用專用模型替代目前的色域 fallback |
| 2 | **物品搜索語意分割引導** | `item_search_worker.py` + `yolomedia.py` | ✅ 已完成：使用 `yoloe-11l-seg.pt` 提供方向引導 |
| 3 | **Monitor 信度儀表板** | `main.py` + `monitor.html` | ✅ 已完成：即時顯示 top-k 偵測信度 |
| 4 | **多模型切換** | `yolomedia.py` | 新增 env 變數 `YOLOMEDIA_MODEL_SELECT`，支援 runtime 切換 `yoloe-11l-seg` / `yolo-seg` |
| 5 | **導盲磚偵測 + 語音** | `vision_controller.py` | 現有 `BlindTileDetector` 已可疊字；加入 TTS 觸發邏輯（偵測到導盲磚 → "前方有導盲磚，可沿其行走"） |
| 6 | **避障距離語意提示** | `yolo_detector.py` | 利用 bbox 面積比推估相對距離，從「左方有人」→「左方 2 公尺有人靠近」 |

### Tier 2：需要少量規則/標註

| # | 功能 | 需求 | 做法 |
|---|------|------|------|
| 7 | **行人穿越道偵測** | 分割 mask 中提取斑馬線 polygon | 用 `yoloe-11l-seg` 的 segmentation mask，判斷前方地面是否為斑馬線 |
| 8 | **路緣/階梯高度差警示** | 需定義 "road edge" class threshold | 若 seg mask 包含 road/sidewalk boundary → 語音提醒「前方有階梯」 |
| 9 | **動態障礙追蹤（光流）** | 需整合 optical flow（OpenCV） | 結合 YOLO 框 + 光流向量判斷移動方向，預警「右方車輛正靠近」 |
| 10 | **手勢控制** | `hand_landmarker.task` + 手勢規則 | 偵測使用者手勢（張手=暫停、指向=啟動搜索），替代實體按鍵 |
| 11 | **紅綠燈倒數秒估算** | `trafficlight.pt` + 數字 OCR | 偵測紅綠燈後用 OCR 讀取倒數秒數，語音播報剩餘等候時間 |

### Tier 3：需要額外模型或資料集

| # | 功能 | 需要什麼 | 說明 |
|---|------|----------|------|
| 12 | **場景分類（室內/室外/電梯/樓梯）** | 場景分類模型（如 Places365） | 根據場景自動切換偵測策略（室內→找物品優先，戶外→避障優先） |
| 13 | **文字辨識 / 招牌讀取** | OCR 模型（PaddleOCR / EasyOCR） | 對準招牌或路牌後語音播報內容 |
| 14 | **深度估計** | Monocular depth model（MiDaS / Depth Anything） | 精確距離感知，可與避障結合生成「3D 語音地圖」 |
| 15 | **人臉辨識** | 人臉辨識模型 + 人臉資料庫 | 辨識熟人並語音提示（需隱私機制） |
| 16 | **多語言 TTS / ASR** | 多語言 TTS 引擎 | 支援英文、日文等環境下的導盲 |

---

## 建議實作優先順序

```
Phase A (目前已完成)
  ├─ yolomedia adapter (item_search)  ✅
  ├─ monitor confidence display        ✅
  └─ this roadmap                      ✅

Phase B (下一步 - 1~2 天)
  ├─ #1 紅綠燈模型接入
  ├─ #5 導盲磚語音觸發
  └─ #4 多模型切換

Phase C (短期 - 1 週)
  ├─ #6 避障距離語意
  ├─ #7 斑馬線偵測
  └─ #9 動態障礙追蹤

Phase D (中期 - 2~4 週)
  ├─ #10 手勢控制
  ├─ #11 紅綠燈倒數
  └─ #8 階梯警示

Phase E (長期 - 需資源)
  ├─ #12~#16
  └─ 依使用者回饋與硬體能力決定優先
```

---

## 現有模組對照表

| 現有模組 | 可補強方向 |
|----------|-----------|
| `yolo_detector.py` | → #6 距離語意、#9 光流追蹤 |
| `traffic_crossing.py` | → #1 專用模型、#11 倒數秒 |
| `item_search_worker.py` | → #2 ✅、#7 斑馬線 |
| `vision_controller.py` | → #5 導盲磚語音、#8 階梯 |
| `monitor.html` | → #3 ✅、未來各功能狀態可視化 |
| `yolomedia.py` (新) | → 統一推論介面、#4 多模型 |
| (尚無) `gesture_controller.py` | → #10 手勢控制 |
| (尚無) `depth_estimator.py` | → #14 深度估計 |
| (尚無) `ocr_reader.py` | → #13 文字辨識 |

---

## 結論

目前已完成最小可行整合（Phase A）。下一步建議優先做 **紅綠燈專用模型接入**（#1），因為 `trafficlight.pt` 權重已就位、模組已有接口，只需在 `.env` 設定路徑即可啟用。
