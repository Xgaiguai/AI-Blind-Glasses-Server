# 智慧導盲眼鏡 - FastAPI 伺服器

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

## 公網存取（不必隨身帶筆電跑伺服器）

- **家裡／實驗室長開一台機器**：用 **Cloudflare Tunnel** 把本機 `localhost:5000` 接到 `https://blind-glasses.org`，眼鏡設 **`CLOUD_MODE=1`** 即可從外面連線。詳見專案內 **[Cloudflare Tunnel 部署指南](../docs/cloudflare-tunnel-setup.md)**；Windows 可雙擊專案根目錄 **`start_cloud.bat`**（需先在 `server/.env` 設定 `CLOUDFLARE_TUNNEL_TOKEN`）。
- **完全託管在雲主機**：將本 `server/` 部署到 VPS 或 PaaS，並處理下方「雲端部署準備」中的 **MJPEG 可達性**（`ESP32_STREAM_URL` 或裝置 Header）。

## 雲端部署準備（ESP32 影像串流可被雲端存取）

目前伺服器端會主動拉取 ESP32 的 MJPEG 串流（預設：`http://<ESP32_IP>:81/stream`）。如果你的雲端 server 無法直接連到 ESP32 的私網 IP，就需要把 ESP32 的 `:81/stream` 暴露成「雲端可存取」的公開 URL。

1. 設定串流 URL（擇一即可）
- **環境變數（伺服器端）**：在 `server/config.py`/`.env` 設 `ESP32_STREAM_URL` 為公開 MJPEG 網址（完整 URL，含 `/stream`）
  - 範例：`ESP32_STREAM_URL=https://xxxx.ngrok-free.app/stream` 或 `http://你的公開IP:81/stream`（需轉發 81）
- **韌體 Header（裝置端）**：`CLOUD_MODE=1` 時可在 `firmware/include/config.h`（整包工作區；若單獨 clone 韌體倉庫則為根目錄 `include/config.h`）設定 `DEVICE_PUBLIC_STREAM_URL`；眼鏡每次 POST `/api/imu` 會帶 `X-Device-Stream-Url`，伺服器優先用此 URL 拉流（適用 [監控頁](https://blind-glasses.org/monitor) 經 CDN、無法用「請求來源 IP:81」的情境）。若同時設了 `ESP32_STREAM_URL`，仍以裝置 Header 為優先。

2. 關閉 UDP discovery（雲端通常不通）
- 設 `ENABLE_UDP_DISCOVERY=0`
- 原因：雲端環境常常 UDP 不通，所以不啟動 `9999/WHO_IS_SERVER` 的 discovery thread

3. CPU-only 與模型快取（避免每次重啟重下載）
- faster-whisper 第一次轉寫會下載 Whisper 模型權重；建議部署前先跑過一次 ASR，讓 HF cache 落在持久化磁碟

## YOLOv8 模型

請自行匯出 ONNX 並放到 `models/yolov8n.onnx`，例如：

```bash
pip install ultralytics
yolo export model=yolov8n.pt format=onnx imgsz=320
# 將產生的 yolov8n.onnx 複製到 server/models/
```

Monitor overlay can also load YOLO `.pt` weights directly through Ultralytics.
The default imported model is:

```env
YOLOE_MODEL_PATH=models/yoloe-11l-seg.pt
TRAFFIC_LIGHT_YOLO_MODEL_PATH=models/trafficlight.pt
VISION_MODEL_PATHS=models/best.pt,models/trafficlight.pt,models/yolo-seg.pt,models/yoloe-11l-seg.pt
VISION_TARGET_CLASSES=
VISION_DETECT_CONF_THRES=0.35
VISION_DETECT_IOU_THRES=0.45
BLIND_TILE_MODEL_PATH=models/yolo-seg.pt
BLIND_TILE_TARGET_CLASSES=road_crossing,blind_path
```

`VISION_MODEL_PATHS` accepts comma-separated `.pt` paths. Leave
`VISION_TARGET_CLASSES` empty to draw every detected class, or set values such
as `traffic_light,road_crossing,blind_path` to filter the overlay.

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

## 延遲量測與調參 (Phase 0 + Phase 1)

### 延遲量測工具

```bash
cd server
python benchmark_latency.py --host 127.0.0.1 --port 5000 --runs 30
```

輸出包含三條測試路徑的 P50/P95/Max/Avg：
1. **Gemini/Traffic**：`/api/gemini?mode=light` 端到端
2. **ASR/Intent**：`/api/asr` 語音辨識 + 意圖路由
3. **Monitor State**：crossing tick 回應時間

結果自動存為 `benchmark_results.json`。調參後再跑一次，可用對比模式：

```bash
cp benchmark_results.json baseline.json
# ... 修改參數 ...
python benchmark_latency.py --runs 30
python benchmark_latency.py compare baseline.json benchmark_results.json
```

### 驗證門檻

| 路徑 | 目標 |
|------|------|
| traffic/gemini | P50 < 1.5s、P95 < 3s |
| asr | 相對 baseline 至少降 25% |
| 誤觸/重複播報 | 不得高於 baseline |
| 斷網 API 請求 | 不造成服務主流程阻塞 |

### Server 輪詢間隔（config.py 環境變數可調）

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `YOLO_INTERVAL_SEC` | 0.15 | YOLO 避障偵測週期 |
| `NAV_INTERVAL_SEC` | 0.5 | 導航 tick 週期 |
| `CROSSING_INTERVAL_SEC` | 0.4 | 紅綠燈偵測週期 |
| `ITEM_SEARCH_INTERVAL_SEC` | 0.4 | 物品查找偵測週期 |
| `ITEM_SEARCH_TTS_MIN_INTERVAL_SEC` | 1.0 | 物品查找語音最小間隔 |

### Firmware 延遲參數（config.h）

| 參數 | 低延遲 | 高穩定 | 說明 |
|------|--------|--------|------|
| `MIC_RECORD_SEC` | 2 | 3 | 錄音秒數 |
| `API_TIMEOUT_MS` | 5000 | 8000 | HTTP 超時 |
| `TTS_GRACE_MS` (main.cpp) | 300 | 500 | 等 TTS 生成完畢的寬限 |

### 智慧音訊抓取機制

韌體不再使用固定延遲等待音訊。新的流程：

1. 事件觸發（API/控制端）→ Gemini/ASR 請求入 HttpTaskQueue（非阻塞）
2. 主 loop 持續運作（IMU、GPS、相機不中斷）
3. 當 HttpTaskQueue 回報任務完成 → 等待 `TTS_GRACE_MS` 讓 TTS 生成
4. 再執行 `playFromServer()` 抓取音訊

此機制確保：
- 不會播到舊音檔（等任務實際完成後才 fetch）
- 主 loop 不被 HTTP 阻塞
- 有 fallback 超時（8 秒）防止任務遺失時卡住

## 實機測試指南（拿到板子與眼鏡後）

> 註：目前按鈕操作仍在開發中，以下測試流程以 API 觸發為主。

### 事前準備

1. **同一網路**：執行伺服器的電腦與眼鏡要連到**同一個 WiFi**（或同一網段），否則 UDP 探索與 HTTP 無法互通。
2. **韌體**（整包時 `firmware/include/config.h`；單獨韌體倉庫則根目錄 `include/config.h`）：
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
| 4. 觸發導航模式 | `curl -X POST "http://<電腦IP>:5000/api/gemini?mode=general"`（或由前端/測試工具呼叫） | 伺服器應產生新的 TTS，`/audio/latest` 可下載最新音檔 |
| 5. 測試 ASR 路由 | 上傳一段 WAV 到 `/api/asr`（可用 Postman/curl） | 應回覆已接收，並在後續流程產生語音回饋 |

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
- **辨識 FPS**：`config.py` 內 `YOLO_INPUT_SIZE` 可設為 (320,320) 或 (416,416)；YOLO 輪詢間隔可透過環境變數 `YOLO_INTERVAL_SEC` 調整（預設 0.15 秒）。YOLOv8 目前使用 ONNXRuntime CPU；若有 GPU 可在 `yolo_detector.py` 改用 `CUDAExecutionProvider`。
- **ESP32 送幀**：韌體端可將串流幀率控制在約 5–10 FPS，以配合伺服器推論與網路負載。
- **非阻塞 HTTP**：韌體的 Gemini/ASR 請求透過 `HttpTaskQueue` 在背景執行緒執行，主 loop 不受 API 延遲影響。
- **TTS 版本控制**：server 的 `tts_queue.py` 使用序號機制（`latest_000001.mp3`），避免寫入/讀取衝突。韌體透過任務完成信號確保只播新音檔。
