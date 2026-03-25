"""
AI 智慧導盲眼鏡 - 伺服器設定
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
HTTP_PORT = int(os.environ.get("HTTP_PORT", "5000"))

# ----- UDP 探索（需與韌體 config.h 一致）-----
UDP_PORT = 9999
UDP_DISCOVERY_MSG = "WHO_IS_SERVER"
UDP_RESPONSE_PREFIX = "SERVER_IP: "

# ----- MJPEG 串流（伺服器拉取 ESP32 的串流）-----
# 韌體 STREAM_PORT=81, STREAM_PATH="/stream"
ESP32_STREAM_PORT = 81
ESP32_STREAM_PATH = "/stream"
STREAM_FRAME_TIMEOUT_SEC = 3.0  # 超過此時長未收到新 frame 視為無影像

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
GEMINI_MODEL = "gemini-2.5-flash"  # 免費版 Flash 2.5；亦可改 gemini-2.0-flash
GEMINI_SCENE_PROMPT = "請用一句簡短中文描述此畫面，適合語音播報給視障者（例如：前方有行人、路口有車輛）。不要列舉多項，只說最重要的一點。"
GEMINI_TRAFFIC_PROMPT = (
    "你現在只負責判斷紅綠燈狀態，請只回覆以下其中一個詞，不要任何說明：\n"
    "- 若畫面中清楚可見紅燈，回覆「紅燈」\n"
    "- 若畫面中清楚可見綠燈，回覆「綠燈」\n"
    "- 若主要是黃燈或綠燈倒數，回覆「黃燈」\n"
    "- 若畫面中看不出紅綠燈狀態，回覆「無法判斷」"
)

# ----- edge-tts -----
EDGE_TTS_VOICE = "zh-TW-HsiaoChenNeural"
TTS_QUEUE_MAX_SIZE = 10

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

# ----- 紅綠燈/過馬路 -----
CROSSING_CONFIRM_FRAMES = int(os.environ.get("CROSSING_CONFIRM_FRAMES", "3"))

# ----- Line Bot -----
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
SERVER_BASE_URL = os.environ.get("SERVER_BASE_URL", "http://localhost:8000")
