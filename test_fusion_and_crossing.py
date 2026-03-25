"""
快速測試：
- IMU+GPS 融合輸出 heading / turning / confidence
- 紅綠燈文字解析
"""

import time

from imu_gps_fusion import ImuGpsFusion
from traffic_crossing import _parse_traffic_color


def test_fusion_basic() -> None:
    f = ImuGpsFusion()
    f.update_gps(25.0330, 121.5654, course=90)
    f.update_imu({"gz": 20.0})
    time.sleep(0.05)
    f.update_imu({"gz": 20.0})

    snap = f.get_snapshot()
    assert snap["heading_deg"] is not None
    assert snap["turning"] in ("left", "right", None)
    assert 0.0 <= snap["confidence"] <= 1.0


def test_traffic_parse() -> None:
    assert _parse_traffic_color("紅燈") == "red"
    assert _parse_traffic_color("綠燈") == "green"
    assert _parse_traffic_color("黃燈") == "yellow"
    assert _parse_traffic_color("無法判斷") == "unknown"


if __name__ == "__main__":
    test_fusion_basic()
    test_traffic_parse()
    print("fusion/crossing 測試通過")

