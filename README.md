# AI 智慧導盲眼鏡 - FastAPI 伺服器

與 ESP32-S3 韌體對接的 Python 伺服器：UDP 發現、MJPEG 拉流、YOLOv8 避障、Gemini 場景分析、edge-tts 語音佇列。

## 功能

- **UDP 探索**：port 9999 監聽 `WHO_IS_SERVER`，回覆 `SERVER_IP: <本機IP>`，並記錄 ESP32 IP 以拉取串流
- **MJPEG 串流**：背景拉取 `http://<ESP32_IP>:81/stream`，維護最新一幀（thread-safe）
- **YOLOv8 ONNX**：對最新幀做目標偵測（person, car, motorcycle, dog），中心且佔比大時產出避障文字
- **Gemini**：`POST /api/gemini` 以目前影格做場景分析，描述文字送入 TTS 佇列
- **edge-tts**：語音佇列（zh-TW-HsiaoChenNeural），依序產出 `audio/latest.mp3`，供 `GET /audio/latest`
- **多意圖 ASR 路由**：`/api/asr` 會分流「導航到家 / 停止導航 / 描述畫面 / 找物品 / 紅綠燈」
- **連續導航 tick**：背景固定執行 step 推進、到點提醒、停止導航
- **IMU + GPS 融合**：輸出 heading / turning / confidence，供監控與導航參考
- **紅綠燈流程**：WAIT/GO/RECHECK 三態，多數表決降低誤判
- **監控面板**：`/monitor` 可看即時畫面、目前模式、最近語音、最近導航 step

## 建置與執行

```bash
cd server
pip install -r requirements.txt
```

設定環境變數（可選，或寫在 `server/.env`）：

- `GEMINI_API_KEY`：Gemini API 金鑰（場景分析與語音意圖辨識）
- `GOOGLE_MAPS_API_KEY`：Google Maps API 金鑰（導航到家用 Directions API）
- `HOME_LAT`、`HOME_LNG`：家的經緯度（預設 25.0, 121.5，請改為自家座標）
- `HTTP_PORT`：預設 5000
- `YOLO_ONNX_PATH`：預設 `models/yolov8n.onnx`

啟動：

```bash
uvicorn main:app --host 0.0.0.0 --port 5000
```

或 `python main.py`。

## YOLOv8 模型

請自行匯出 ONNX 並放到 `models/yolov8n.onnx`，例如：

```bash
pip install ultralytics
yolo export model=yolov8n.pt format=onnx imgsz=320
# 將產生的 yolov8n.onnx 複製到 server/models/
```

未放置模型時，避障偵測不執行，其餘功能正常。

## API

| 端點 | 方法 | 說明 |
|------|------|------|
| /health | GET | 健康檢查 |
| /api/obstacle | GET | 目前 YOLO 避障文字 |
| /api/gemini | POST | 場景分析 + TTS 佇列，可帶 `?mode=general\|light\|item_search` |
| /api/asr | POST | 上傳 WAV，回覆已收到並可送入 TTS |
| /api/imu | POST | JSON 上傳 |
| /api/gps | POST | JSON 上傳 |
| /audio/latest | GET | 最新 TTS 語音檔 |
| /monitor | GET | 開發監控頁 |
| /api/monitor/state | GET | 監控狀態（模式、導航、fusion、traffic） |
| /api/monitor/events | GET | 導航事件 ring buffer |
| /api/monitor/frame | GET | 最新 JPEG 畫面 |

## 新增模式說明

- **導航狀態機**：`idle`、`navigating`、`rerouting`、`arrived`、`crossing_wait`、`crossing_go`
- **語音意圖分類**：`NAV_HOME`、`STOP_NAV`、`SCENE_DESC`、`ITEM_SEARCH`、`TRAFFIC_LIGHT`
- **紅綠燈流程**：
  - `WAIT`：等待穩定綠燈
  - `GO`：綠燈可通行
  - `RECHECK`：通行中定期複查，若變紅燈會提示停止

## 調參建議

- `NAV_REROUTE_MIN_SEC`：重規劃最短間隔，建議 20~45 秒
- `NAV_ARRIVAL_RADIUS_M`：到點半徑，建議 15~30 公尺
- `HEADING_SMOOTH_ALPHA`：heading 平滑係數，建議 0.2~0.4
- `TURN_THRESHOLD_DPS`：左右轉判定角速度，建議 12~20 deg/s
- `CROSSING_CONFIRM_FRAMES`：紅綠燈確認幀數，建議 3~5

## 實機測試指南（拿到板子與眼鏡後）

### 事前準備

1. **同一網路**：執行伺服器的電腦與眼鏡要連到**同一個 WiFi**（或同一網段），否則 UDP 探索與 HTTP 無法互通。
2. **韌體**（`firmware/include/config.h`）：
   - 設定 `WIFI_SSID`、`WIFI_PASSWORD`。
   - 燒錄完成後可開 Serial Monitor（115200 baud）觀察連線與 API 回覆。
3. **伺服器**（`server/`）：
   - `.env` 內要有 `GEMINI_API_KEY`、`GOOGLE_MAPS_API_KEY`。
   - `config.py` 或環境變數設定 **家的座標**：`HOME_LAT`、`HOME_LNG`（可從 Google 地圖右鍵取得經緯度）。

### 啟動順序

1. **先開伺服器**（在 `server` 目錄）：
   - 雙擊 `run.bat`，或：`uvicorn main:app --host 0.0.0.0 --port 5000`
   - 看到 `Uvicorn running on http://0.0.0.0:5000` 即表示就緒。
2. **再開眼鏡**：上電後等約 10–30 秒，讓 WiFi 連線、UDP 探索到伺服器。

### 建議測試流程

| 步驟 | 做法 | 預期結果 |
|------|------|----------|
| 1. 連線 | 瀏覽器開 `http://<你電腦的IP>:5000/health`（與眼鏡同 WiFi 的手機或電腦） | 看到 `{"status":"ok","server_ip":"..."}` |
| 2. 眼鏡找伺服器 | 看 Serial Monitor 或等眼鏡開機完成 | 應有「找到伺服器」或類似 log，之後才會送 API |
| 3. 送 GPS（導航起點） | 到**戶外或窗邊**讓 GPS 定位；或先用電腦模擬：`curl -X POST http://<電腦IP>:5000/api/gps -H "Content-Type: application/json" -d "{\"lat\":25.033,\"lng\":121.565}"` | 伺服器會記住這筆位置，60 秒內說「導航到家」會用這當起點 |
| 4. 語音「導航到家」 | **切換鍵長按約 5 秒** → 聽到提示後說「導航到家」→ 鬆開 | 眼鏡應播放 TTS：第一段導航指示（或「目前無法取得位置」若尚無有效 GPS） |
| 5. 其他語音 | 同樣長按切換鍵，改說「現在幾點」等 | 應播放「已收到語音指令，正在處理。」 |

### 若沒有聲音或沒反應

- **先確認有 GPS**：導航到家會用「最後一筆 GPS」當起點；若超過 60 秒沒收到 `/api/gps`，會播「目前無法取得位置」。可先用步驟 3 的 curl 手動送一筆再測語音。
- **確認 TTS 有產生**：用瀏覽器開 `http://<電腦IP>:5000/audio/latest`，若有檔案會下載 mp3；若 404 表示尚未有語音佇列產出。
- **看 Serial**：確認 `POST /api/asr`、`GET /audio/latest` 是否成功（狀態碼 200）。
- **看伺服器終端**：是否有 Python 錯誤或 Directions API / Gemini 錯誤（金鑰、配額等）。

### 快速檢查清單

- [ ] 電腦與眼鏡同一 WiFi
- [ ] 伺服器已啟動且 `/health` 可連
- [ ] 韌體已燒錄且 `config.h` 的 WiFi 正確
- [ ] `.env` 有 `GEMINI_API_KEY`、`GOOGLE_MAPS_API_KEY`
- [ ] `HOME_LAT`、`HOME_LNG` 已設為家的座標
- [ ] 測「導航到家」前有送過 GPS（實機定位或 curl 模擬）

---

## 效能優化建議

- **傳輸延遲**：ESP32 端可調低解析度與 JPEG 品質（如 320×240、quality 10–15）；使用單向 MJPEG 拉流，避免頻繁連線。
- **辨識 FPS**：`config.py` 內 `YOLO_INPUT_SIZE` 可設為 (320,320) 或 (416,416)；`main.py` 中 YOLO 輪詢間隔 `_yolo_interval_sec` 可調（預設 0.2 秒）。YOLOv8 目前使用 ONNXRuntime CPU；若有 GPU 可在 `yolo_detector.py` 改用 `CUDAExecutionProvider`。
- **ESP32 送幀**：韌體端可將串流幀率控制在約 5–10 FPS，以配合伺服器推論與網路負載。
