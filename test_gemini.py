"""快速測試 Gemini API 金鑰與模型是否串接成功。"""
import sys
import config

def main():
    key = getattr(config, "GEMINI_API_KEY", "")
    if not key:
        print("FAIL: GEMINI_API_KEY 未設定（請檢查 .env 或環境變數）")
        return 1
    print(f"API Key: {key[:10]}...{key[-4:]}")
    print(f"Model: {config.GEMINI_MODEL}")

    try:
        import google.generativeai as genai  # type: ignore[import-untyped]
        from google.generativeai import GenerativeModel  # type: ignore[attr-defined]
        genai.configure(api_key=key)  # type: ignore[attr-defined]
        model = GenerativeModel(config.GEMINI_MODEL)
        response = model.generate_content("請說一種動物")
        text = (response and response.text or "").strip()
        if text:
            print(f"Gemini 回覆: {text}")
            print("OK: Gemini 串接成功")
            return 0
        print("FAIL: Gemini 無回覆內容")
        return 1
    except Exception as e:
        print(f"FAIL: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
