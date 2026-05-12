"""
延遲基準量測腳本 (Phase 0)

用法：
  python benchmark_latency.py [--host HOST] [--port PORT] [--runs N]

會分別測三條路徑：
  1. /api/gemini?mode=light（模擬 TrafficShort 路徑）
  2. /api/asr（模擬語音上傳路徑）
  3. /api/monitor/latency（收集 server 端累計統計）

結果以表格印出 P50 / P95 / Max / Avg。
"""

import argparse
import json
import os
import statistics
import struct
import time
from typing import Dict, List

import requests

WAV_SAMPLE_RATE = 16000
WAV_DURATION_SEC = 2


def make_silent_wav(duration_sec: float = WAV_DURATION_SEC, sample_rate: int = WAV_SAMPLE_RATE) -> bytes:
    num_samples = int(sample_rate * duration_sec)
    data_size = num_samples * 2
    file_size = 36 + data_size
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", file_size, b"WAVE",
        b"fmt ", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b"data", data_size,
    )
    return header + b"\x00" * data_size


def percentile(data: List[float], p: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * p / 100.0)
    idx = min(idx, len(sorted_data) - 1)
    return sorted_data[idx]


def run_gemini_benchmark(base_url: str, runs: int) -> List[float]:
    url = f"{base_url}/api/gemini?mode=light"
    latencies = []
    for i in range(runs):
        t0 = time.time()
        try:
            r = requests.post(url, timeout=10)
            elapsed_ms = (time.time() - t0) * 1000
            if r.status_code == 200:
                body = r.json()
                server_lat = body.get("latency_ms")
                if server_lat and isinstance(server_lat, dict) and "total_ms" in server_lat:
                    latencies.append(server_lat["total_ms"])
                else:
                    latencies.append(elapsed_ms)
            else:
                latencies.append(elapsed_ms)
        except Exception:
            latencies.append((time.time() - t0) * 1000)
        time.sleep(0.3)
    return latencies


def run_asr_benchmark(base_url: str, runs: int) -> List[float]:
    url = f"{base_url}/api/asr"
    wav_data = make_silent_wav()
    latencies = []
    for i in range(runs):
        t0 = time.time()
        try:
            r = requests.post(url, data=wav_data, headers={"Content-Type": "audio/wav"}, timeout=15)
            elapsed_ms = (time.time() - t0) * 1000
            if r.status_code == 200:
                body = r.json()
                server_lat = body.get("latency_ms")
                if server_lat and isinstance(server_lat, dict) and "total_ms" in server_lat:
                    latencies.append(server_lat["total_ms"])
                else:
                    latencies.append(elapsed_ms)
            else:
                latencies.append(elapsed_ms)
        except Exception:
            latencies.append((time.time() - t0) * 1000)
        time.sleep(0.5)
    return latencies


def run_crossing_benchmark(base_url: str, runs: int) -> List[float]:
    """Crossing tick 由 server 背景跑，這裡量的是 /api/monitor/state 拿到 crossing 狀態的延遲。"""
    url = f"{base_url}/api/monitor/state"
    latencies = []
    for i in range(runs):
        t0 = time.time()
        try:
            r = requests.get(url, timeout=5)
            elapsed_ms = (time.time() - t0) * 1000
            latencies.append(elapsed_ms)
        except Exception:
            latencies.append((time.time() - t0) * 1000)
        time.sleep(0.2)
    return latencies


def print_stats(name: str, latencies: List[float]) -> Dict[str, float]:
    if not latencies:
        print(f"  {name}: NO DATA")
        return {}
    avg = statistics.mean(latencies)
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    mx = max(latencies)
    mn = min(latencies)
    print(f"  {name}:")
    print(f"    Runs: {len(latencies)}")
    print(f"    Avg:  {avg:.1f} ms")
    print(f"    P50:  {p50:.1f} ms")
    print(f"    P95:  {p95:.1f} ms")
    print(f"    Max:  {mx:.1f} ms")
    print(f"    Min:  {mn:.1f} ms")
    return {"name": name, "avg": avg, "p50": p50, "p95": p95, "max": mx, "min": mn, "runs": len(latencies)}


def main():
    parser = argparse.ArgumentParser(description="Latency baseline benchmark")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--runs", type=int, default=30)
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    print(f"Target: {base_url}")
    print(f"Runs per path: {args.runs}")
    print()

    # Health check
    try:
        r = requests.get(f"{base_url}/health", timeout=3)
        if r.status_code != 200:
            print("Server not reachable. Exiting.")
            return
    except Exception:
        print("Server not reachable. Exiting.")
        return

    print("=" * 50)
    print("BASELINE LATENCY MEASUREMENT")
    print("=" * 50)

    results = []

    print("\n[1/3] Gemini/Traffic path (/api/gemini?mode=light)")
    lats = run_gemini_benchmark(base_url, args.runs)
    results.append(print_stats("gemini_traffic", lats))

    print("\n[2/3] ASR path (/api/asr)")
    lats = run_asr_benchmark(base_url, args.runs)
    results.append(print_stats("asr_intent", lats))

    print("\n[3/3] Monitor state (crossing tick responsiveness)")
    lats = run_crossing_benchmark(base_url, args.runs)
    results.append(print_stats("monitor_state", lats))

    # Server-side latency stats
    print("\n[+] Server accumulated latency stats:")
    try:
        r = requests.get(f"{base_url}/api/monitor/latency", timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"    {json.dumps(data.get('stats', {}), indent=4)}")
        else:
            print(f"    (status {r.status_code})")
    except Exception as e:
        print(f"    (error: {e})")

    # Save results
    out_path = os.path.join(os.path.dirname(__file__), "benchmark_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "target": base_url,
            "runs_per_path": args.runs,
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {out_path}")


def compare():
    """比較兩份 benchmark_results.json，印出差異。"""
    parser = argparse.ArgumentParser(description="Compare two benchmark results")
    parser.add_argument("before", help="Path to baseline result JSON")
    parser.add_argument("after", help="Path to new result JSON")
    args = parser.parse_args()

    with open(args.before, encoding="utf-8") as f:
        before = json.load(f)
    with open(args.after, encoding="utf-8") as f:
        after = json.load(f)

    print(f"{'Path':<20} {'Metric':<8} {'Before':>10} {'After':>10} {'Delta':>10} {'Change':>8}")
    print("-" * 70)
    for b_res, a_res in zip(before["results"], after["results"]):
        name = b_res.get("name", "?")
        for metric in ["avg", "p50", "p95", "max"]:
            bv = b_res.get(metric, 0)
            av = a_res.get(metric, 0)
            delta = av - bv
            pct = (delta / bv * 100) if bv else 0
            sign = "+" if delta > 0 else ""
            print(f"{name:<20} {metric:<8} {bv:>10.1f} {av:>10.1f} {sign}{delta:>9.1f} {sign}{pct:>6.1f}%")
        print()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "compare":
        sys.argv.pop(1)
        compare()
    else:
        main()
