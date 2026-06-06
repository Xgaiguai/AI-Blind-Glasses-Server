"""
智慧導盲眼鏡 - 伺服器設定
請依實際需求修改
"""

import os

# 從 server/.env 載入環境變數（依 config 所在目錄，從哪執行都能讀到）
try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(_env_path)
except ImportError:
    pass

# ----- HTTP 伺服器 -----
HTTP_HOST = os.environ.get("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("HTTP_PORT", "4000"))
# Optional server IP advertised to ESP32 during UDP discovery. Useful when the
# PC has multiple network adapters and the default route picks the wrong one.
SERVER_IP = os.environ.get("SERVER_IP", "").strip()

# ----- UDP 探索（需與韌體 config.h 一致）-----
UDP_PORT = 9999
UDP_DISCOVERY_MSG = "WHO_IS_SERVER"
UDP_RESPONSE_PREFIX = "SERVER_IP: "
# 設為 1 時在終端機列出埠 9999 收到的每筆 UDP（僅探索用；陀螺儀仍走 HTTP /api/imu）
UDP_RECV_LOG = os.environ.get("UDP_RECV_LOG", "0") == "1"

# ----- MJPEG 串流（伺服器拉取 ESP32 的串流）-----
# 韌體 STREAM_PORT=81, STREAM_PATH="/stream"
ESP32_STREAM_PORT = 81
ESP32_STREAM_PATH = "/stream"

# 雲端部署：若你把 ESP32 的 MJPEG 串流用 tunnel/反代/port-forward 變成「雲端可存取」的公開 URL，
# 就在這裡填完整網址（例如 https://xxxx.ngrok-free.app/stream 或 https://your-domain/esp32/stream）。
# 若未設定，則依賴 UDP discovery / 首次 API 請求來源 IP 來推回來組 URL。
ESP32_STREAM_URL = os.environ.get("ESP32_STREAM_URL", "").strip()

# 雲端環境常常 UDP 不通，可關閉 UDP discovery 只靠 ESP32 直連的 HTTP 來源 host。
ENABLE_UDP_DISCOVERY = os.environ.get("ENABLE_UDP_DISCOVERY", "1") == "1"
STREAM_FRAME_TIMEOUT_SEC = 3.0  # 超過此時長未收到新 frame 視為無影像
# 拉眼鏡 MJPEG：connect 逾時、(chunk 之間) read 逾時；read 太小會頻繁斷線重連
STREAM_PULL_CONNECT_TIMEOUT_SEC = float(os.environ.get("STREAM_PULL_CONNECT_TIMEOUT_SEC", "3.0"))
STREAM_PULL_READ_TIMEOUT_SEC = float(os.environ.get("STREAM_PULL_READ_TIMEOUT_SEC", "25.0"))
STREAM_PULL_RETRY_SLEEP_SEC = float(os.environ.get("STREAM_PULL_RETRY_SLEEP_SEC", "0.25"))
# GET /stream 走「快取 MJPEG」時，multipart 輪詢間隔（秒）；越小越即時、頻寬越高
MJPEG_PUBLIC_CACHE_INTERVAL_SEC = float(os.environ.get("MJPEG_PUBLIC_CACHE_INTERVAL_SEC", "0.05"))
# 監控 WebSocket：1=略過疊字、直接推眼鏡原圖（較順、延遲較低；避障仍用原幀）
VIEWER_PREFER_RAW = os.environ.get("VIEWER_PREFER_RAW", "0") == "1"
# 監控疊字更新：間隔越小越即時，CPU 越高；每 N 幀處理一次（1=每幀）
VISION_OVERLAY_INTERVAL_SEC = float(os.environ.get("VISION_OVERLAY_INTERVAL_SEC", "0.12"))
VISION_FRAME_SKIP_N = max(1, int(os.environ.get("VISION_FRAME_SKIP_N", "1")))
VISION_JPEG_QUALITY = int(os.environ.get("VISION_JPEG_QUALITY", "72"))
ENABLE_VISION_OVERLAY = os.environ.get("ENABLE_VISION_OVERLAY", "1") == "1"

# ----- 併發與監控串流效能 -----
# 阻塞型任務（ASR / Gemini / LINE AI）分流到獨立 thread pool，避免互相搶 worker。
ASR_EXECUTOR_MAX_WORKERS = int(os.environ.get("ASR_EXECUTOR_MAX_WORKERS", "2"))
GEMINI_EXECUTOR_MAX_WORKERS = int(os.environ.get("GEMINI_EXECUTOR_MAX_WORKERS", "2"))
LINE_AI_EXECUTOR_MAX_WORKERS = int(os.environ.get("LINE_AI_EXECUTOR_MAX_WORKERS", "2"))
# 監控影像預設推送節奏（秒）；0.05 約 20fps，較 60fps 更省 CPU/頻寬。
# 監控頁 /ws/viewer 輪詢最新幀間隔（秒）；越小延遲越低，CPU 略增
VIEWER_WS_INTERVAL_SEC = float(os.environ.get("VIEWER_WS_INTERVAL_SEC", "0.02"))
# ASR 回應策略：預設 async 先回 202，再背景執行辨識與路由。
ASR_DEFAULT_ASYNC = os.environ.get("ASR_DEFAULT_ASYNC", "1") == "1"
# API 保護：同時處理中的 ASR / Gemini 請求上限（超過回 503，避免打爆 CPU）
API_ASR_MAX_JOBS = max(1, int(os.environ.get("API_ASR_MAX_JOBS", "8")))
API_GEMINI_MAX_JOBS = max(1, int(os.environ.get("API_GEMINI_MAX_JOBS", "3")))
# ASR 非同步模式：槽滿時可排入等候佇列（滿則丟棄最舊）；設 0 則維持立即 503
ASR_WAIT_QUEUE_MAX = max(0, int(os.environ.get("ASR_WAIT_QUEUE_MAX", "4")))
# 啟動時預載 Whisper（降低第一次語音延遲）；設 0 關閉
ASR_WHISPER_WARMUP = os.environ.get("ASR_WHISPER_WARMUP", "1") == "1"

# ----- 資料與日誌 -----
DATA_DIR = os.environ.get("DATA_DIR", "data")
LOG_REQUESTS = True
AUDIO_LATEST_PATH = "audio/latest.mp3"  # edge-tts 輸出，供 GET /audio/latest

# ----- YOLOv8 ONNX -----
YOLO_ONNX_PATH = os.environ.get("YOLO_ONNX_PATH", "models/yolov8n.onnx")
YOLO_INPUT_SIZE = (320, 320)  # 推論輸入尺寸，可改 416
YOLO_CONF_THRESH = 0.45
YOLO_IOU_THRESH = 0.45
YOLO_TARGET_CLASSES = ["person", "car", "motorcycle", "dog"]  # COCO 類別名
# 避障：中心區域佔比閾值（佔畫面面積比例）
OBSTACLE_CENTER_RATIO = 0.4   # 中心區域為畫面寬高各 40%
OBSTACLE_AREA_RATIO_MIN = 0.05  # 物件佔畫面至少 5% 才提醒

# ----- Gemini（免費版可用 2.5 Flash）-----
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")  # 或寫在 .env
GEMINI_API_KEY_1 = os.environ.get("GEMINI_API_KEY_1", GEMINI_API_KEY)
GEMINI_API_KEY_2 = os.environ.get("GEMINI_API_KEY_2", "")
GEMINI_MODEL = "gemini-2.5-flash"  # 免費版 Flash 2.5；亦可改 gemini-2.0-flash
GEMINI_SCENE_PROMPT = "請用一句簡短中文描述此畫面，適合語音播報給視障者（例如：前方有行人、路口有車輛）。不要列舉多項，只說最重要的一點。"
GEMINI_TRAFFIC_PROMPT = (
    "你現在只負責判斷紅綠燈狀態，請只回覆以下其中一個詞，不要任何說明：\n"
    "- 若畫面中清楚可見紅燈，回覆「紅燈」\n"
    "- 若畫面中清楚可見綠燈，回覆「綠燈」\n"
    "- 若主要是黃燈或綠燈倒數，回覆「黃燈」\n"
    "- 若畫面中看不出紅綠燈狀態，回覆「無法判斷」"
)

# ----- LINE 家屬通知 -----
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "").strip()
# 逗號分隔（userId/groupId/roomId）
LINE_TARGET_IDS = os.environ.get("LINE_TARGET_IDS", "").strip()
LINE_NOTIFY_ENABLE = os.environ.get("LINE_NOTIFY_ENABLE", "0") == "1"
LINE_NOTIFY_COOLDOWN_SEC = float(os.environ.get("LINE_NOTIFY_COOLDOWN_SEC", "90"))
LINE_REQUEST_TIMEOUT_SEC = float(os.environ.get("LINE_REQUEST_TIMEOUT_SEC", "6"))

# ----- 跌倒偵測（IMU）-----
FALL_ENABLE = os.environ.get("FALL_ENABLE", "1") == "1"
FALL_GZ_DPS_THRESHOLD = float(os.environ.get("FALL_GZ_DPS_THRESHOLD", "160"))
FALL_CONFIRM_SEC = float(os.environ.get("FALL_CONFIRM_SEC", "1.2"))
FALL_COOLDOWN_SEC = float(os.environ.get("FALL_COOLDOWN_SEC", "120"))

# ----- edge-tts -----
EDGE_TTS_VOICE = "zh-TW-HsiaoChenNeural"
TTS_QUEUE_MAX_SIZE = 10

# ----- 本地 Whisper（台灣版 ASR）-----
# 你韌體端錄音參數：
# - MIC_SAMPLE_RATE=16000
# - MIC_RECORD_SEC=4
# faster-whisper 的 base 模型通常可直接對這種 16kHz wav 轉寫。
ASR_WHISPER_MODEL = os.environ.get("ASR_WHISPER_MODEL", "base")
ASR_WHISPER_LANG = os.environ.get("ASR_WHISPER_LANG", "zh")
ASR_WHISPER_DEVICE = os.environ.get("ASR_WHISPER_DEVICE", "cpu")
ASR_WHISPER_COMPUTE_TYPE = os.environ.get("ASR_WHISPER_COMPUTE_TYPE", "int8")
# 可選：若你已手動下載 whisper 模型，可指定本地資料夾，避免台灣下載不穩
ASR_WHISPER_MODEL_DIR = os.environ.get("ASR_WHISPER_MODEL_DIR", "")

# ----- 物品查找（ITEM_SEARCH）-----
# 目前 worker 預設使用 Gemini；若你之後接上 YOLOE+MediaPipe，這些路徑就會用到。
ITEM_SEARCH_INTERVAL_SEC = float(os.environ.get("ITEM_SEARCH_INTERVAL_SEC", "0.4"))
ITEM_SEARCH_TTS_MIN_INTERVAL_SEC = float(os.environ.get("ITEM_SEARCH_TTS_MIN_INTERVAL_SEC", "1.0"))

# 物品查找自動結束（OK 連續達標 / 超時）
ITEM_SEARCH_AUTO_STOP_ENABLE = os.environ.get("ITEM_SEARCH_AUTO_STOP_ENABLE", "1") == "1"
# 連續偵測到 direction=OK 的次數（達到後自動停止）
ITEM_SEARCH_OK_CONSECUTIVE_COUNT = int(os.environ.get("ITEM_SEARCH_OK_CONSECUTIVE_COUNT", "3"))
# 最長搜尋時間（秒）；超時仍會自動停止，避免無限播報
ITEM_SEARCH_MAX_SECONDS = float(os.environ.get("ITEM_SEARCH_MAX_SECONDS", "90"))

# YOLOE/手部模型路徑（留空時 yolomedia 會自動搜尋 models/ 內的 .pt）
YOLOE_MODEL_PATH = os.environ.get("YOLOE_MODEL_PATH", "models/yoloe-11l-seg.pt")
HAND_LANDMARKER_TASK_PATH = os.environ.get("HAND_LANDMARKER_TASK_PATH", "models/hand_landmarker.task")
TRAFFIC_LIGHT_YOLO_MODEL_PATH = os.environ.get("TRAFFIC_LIGHT_YOLO_MODEL_PATH", "models/trafficlight.pt")

# 是否嘗試啟用視覺模型（未實作時仍會回退 Gemini；保留介面給後續接上）
ENABLE_ITEM_SEARCH_VISION = os.environ.get("ENABLE_ITEM_SEARCH_VISION", "0") == "1"

# ----- 導航到家 -----
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
HOME_LAT = float(os.environ.get("HOME_LAT", "25.0"))
HOME_LNG = float(os.environ.get("HOME_LNG", "121.5"))
LAST_GPS_MAX_AGE_SEC = 60

# ----- 連續導航與重規劃 -----
NAV_REROUTE_MIN_SEC = float(os.environ.get("NAV_REROUTE_MIN_SEC", "30"))
NAV_ARRIVAL_RADIUS_M = float(os.environ.get("NAV_ARRIVAL_RADIUS_M", "25"))

# ----- IMU/GPS 融合 -----
HEADING_SMOOTH_ALPHA = float(os.environ.get("HEADING_SMOOTH_ALPHA", "0.3"))
TURN_THRESHOLD_DPS = float(os.environ.get("TURN_THRESHOLD_DPS", "15"))
# 走停判斷（is_moving / motion_state）
MOTION_ACC_DELTA_MOVE_G = float(os.environ.get("MOTION_ACC_DELTA_MOVE_G", "0.08"))
MOTION_ACC_DELTA_STOP_G = float(os.environ.get("MOTION_ACC_DELTA_STOP_G", "0.04"))
MOTION_GYRO_MOVE_DPS = float(os.environ.get("MOTION_GYRO_MOVE_DPS", "18"))
MOTION_GYRO_STOP_DPS = float(os.environ.get("MOTION_GYRO_STOP_DPS", "8"))
MOTION_HOLD_SEC = float(os.environ.get("MOTION_HOLD_SEC", "0.35"))

# ----- 紅綠燈/過馬路 -----
CROSSING_CONFIRM_FRAMES = int(os.environ.get("CROSSING_CONFIRM_FRAMES", "3"))

# ----- 背景循環輪詢間隔（Phase 1-A 調參區）-----
# 數值越小反應越快，但 CPU 負載越高；調整時搭配 benchmark_latency.py 驗證。
YOLO_INTERVAL_SEC = float(os.environ.get("YOLO_INTERVAL_SEC", "0.10"))
NAV_INTERVAL_SEC = float(os.environ.get("NAV_INTERVAL_SEC", "0.5"))
CROSSING_INTERVAL_SEC = float(os.environ.get("CROSSING_INTERVAL_SEC", "0.4"))

# ----- Cloudflare Tunnel / 雲端部署 -----
CLOUDFLARE_TUNNEL_TOKEN = os.environ.get("CLOUDFLARE_TUNNEL_TOKEN", "").strip()
DEVICE_API_TOKEN = os.environ.get("DEVICE_API_TOKEN", "").strip()
REQUIRE_DEVICE_API_TOKEN = os.environ.get("REQUIRE_DEVICE_API_TOKEN", "0") == "1"
PUBLIC_BASE_URL = os.environ.get("LINE_SNAPSHOT_BASE_URL", "").strip()

# ----- 導盲磚偵測（monitor 視覺框）-----
# Monitor overlay YOLO .pt models. The first existing model is loaded by
# default; set multiple comma-separated paths to run several detectors.
VISION_MODEL_PATHS = [
    x.strip()
    for x in os.environ.get(
        "VISION_MODEL_PATHS",
        "models/best.pt,models/trafficlight.pt,models/yolo-seg.pt,models/yoloe-11l-seg.pt",
    ).split(",")
    if x.strip()
]
VISION_DETECT_CONF_THRES = float(os.environ.get("VISION_DETECT_CONF_THRES", "0.35"))
VISION_DETECT_IOU_THRES = float(os.environ.get("VISION_DETECT_IOU_THRES", "0.45"))
VISION_TARGET_CLASSES = [
    x.strip().lower()
    for x in os.environ.get("VISION_TARGET_CLASSES", "").split(",")
    if x.strip()
]

BLIND_TILE_MODEL_PATH = os.environ.get("BLIND_TILE_MODEL_PATH", "models/yolo-seg.pt")
BLIND_TILE_CONF_THRES = float(os.environ.get("BLIND_TILE_CONF_THRES", "0.35"))
BLIND_TILE_IOU_THRES = float(os.environ.get("BLIND_TILE_IOU_THRES", "0.45"))
BLIND_TILE_TARGET_CLASSES = [
    x.strip().lower()
    for x in os.environ.get("BLIND_TILE_TARGET_CLASSES", "road_crossing,blind_path")
    .split(",")
    if x.strip()
]
