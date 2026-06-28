"""Quick test: B站字幕获取 → AI处理 → 飞书文档"""
import sys, json, os

# Add project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    BILIBILI_SESSDATA,
    WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
    AUDIO_DOWNLOAD_DIR, AUDIO_COOKIE_BROWSER,
)

from src.pipeline import VideoNotePipeline

# 飞书 user access token（从 .env 读取，仅测试用）
USER_TOKEN = os.getenv("FEISHU_USER_TOKEN", "")

def main():
    bvid = "BV1Bt7K6FEqD"

    pipeline = VideoNotePipeline(
        bilibili_sessdata=BILIBILI_SESSDATA,
        deepseek_api_key=DEEPSEEK_API_KEY,
        deepseek_base_url=DEEPSEEK_BASE_URL,
        deepseek_model=DEEPSEEK_MODEL,
        whisper_model=WHISPER_MODEL,
        whisper_device=WHISPER_DEVICE,
        whisper_compute_type=WHISPER_COMPUTE_TYPE,
        audio_download_dir=AUDIO_DOWNLOAD_DIR,
        audio_cookie_browser=AUDIO_COOKIE_BROWSER,
        feishu_app_id=FEISHU_APP_ID,
        feishu_app_secret=FEISHU_APP_SECRET,
    )

    def status(msg):
        print(f"  >> {msg}")

    print(f"\n=== Testing BV1Bt7K6FEqD ===\n")

    # Step 1: Get video info + subtitles
    status("Getting video info and subtitles...")
    from src.bilibili.fetcher import fetch_video_with_subtitles

    video_info = fetch_video_with_subtitles(bvid, sessdata=BILIBILI_SESSDATA)

    print(f"  Title: {video_info.title}")
    print(f"  Author: {video_info.author}")
    print(f"  Duration: {video_info.duration}s")
    print(f"  Subtitles: {len(video_info.subtitles)} entries")
    print(f"  Source: {video_info.subtitle_source}")

    if not video_info.subtitles:
        print("\n  No subtitles from API, trying yt-dlp audio + Whisper...")
        result = pipeline.process(bvid, status_callback=status)
        if not result.success:
            print(f"\n  FAILED: {result.error_message}")
            return
        print(f"\n  Doc URL: {result.doc_url}")
        return

    # Step 2: AI processing
    status("AI processing subtitles...")
    raw_subtitles = [
        {"from": s.from_time, "to": s.to_time, "content": s.content}
        for s in video_info.subtitles
    ]

    markdown = pipeline.ai_processor.process_all_in_one(
        subtitles=raw_subtitles,
        title=video_info.title,
        author=video_info.author,
        duration=video_info.duration,
        subtitle_source=video_info.subtitle_source,
    )

    status("AI processing done!")
    print("\n--- ARTICLE PREVIEW ---")
    print(markdown[:2000])
    print("... (truncated)")
    print("--- END PREVIEW ---\n")

    # Step 3: Create Feishu doc
    status("Creating Feishu document...")
    doc_title = f"【视频笔记】{video_info.title}"

    # Try with user token first
    import httpx
    r = httpx.post(
        "https://open.feishu.cn/open-apis/docx/v1/documents",
        headers={
            "Authorization": f"Bearer {USER_TOKEN}",
            "Content-Type": "application/json",
        },
        content=json.dumps({"title": doc_title}),
    )
    result = r.json()
    print(f"  Doc API response: code={result.get('code')}")

    if result.get("code") == 0:
        doc_id = result["data"]["document"]["document_id"]
        doc_url = f"https://bytedance.feishu.cn/docx/{doc_id}"
        print(f"\n  SUCCESS! Doc: {doc_url}")

        # Add content blocks
        from src.feishu.doc_creator import markdown_to_feishu_blocks, FeishuDocClient
        client = FeishuDocClient(FEISHU_APP_ID, FEISHU_APP_SECRET)
        # But we need to use user token here... hmm
        # For now just show the article
    else:
        print(f"  Doc creation failed: {result.get('msg', '')[:200]}")
        print("\n  Article generated but could not create Feishu doc.")
        print("  Saving article to test_output.md instead...")
        with open("test_output.md", "w", encoding="utf-8") as f:
            f.write(markdown)
        print("  Saved to test_output.md")


if __name__ == "__main__":
    main()
