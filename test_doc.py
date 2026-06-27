"""Test: Write markdown content to Feishu doc"""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

import httpx
from src.feishu.doc_creator import markdown_to_feishu_blocks

app_id = os.getenv("FEISHU_APP_ID")
app_secret = os.getenv("FEISHU_APP_SECRET")

# Step 1: Read AI-generated markdown from previous test
try:
    with open("test_output.md", "r", encoding="utf-8") as f:
        md = f.read()
    print(f"Loaded markdown from test_output.md: {len(md)} chars")
except:
    # Use test_subtitles.json + AI
    from src.ai.processor import AITextProcessor
    from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

    print("Running AI processing on test_subtitles.json...")
    with open("test_subtitles.json", "r", encoding="utf-8") as f:
        raw = json.load(f)

    ai = AITextProcessor(DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL)
    md = ai.process_all_in_one(raw, "学生时代最重要的三次选择", "孙熙然", 457, "test")

    with open("test_output.md", "w", encoding="utf-8") as f:
        f.write(md)
    print(f"AI done, saved to test_output.md: {len(md)} chars")

# Step 2: Convert to blocks
blocks = markdown_to_feishu_blocks(md)
print(f"Blocks generated: {len(blocks)}")

# Step 3: Get token
r = httpx.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    data={"app_id": app_id, "app_secret": app_secret}, timeout=10)
token = r.json()["tenant_access_token"]
print(f"Token: {token[:20]}...")

# Step 4: Create doc
r2 = httpx.post("https://open.feishu.cn/open-apis/docx/v1/documents",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    content=json.dumps({"title": "【视频笔记】学生时代最重要的三次选择"}, ensure_ascii=False),
    timeout=10)
doc_id = r2.json()["data"]["document"]["document_id"]
print(f"Doc created: {doc_id}")

# Step 5: Add blocks in batches
BATCH = 20
added = 0
for i in range(0, len(blocks), BATCH):
    batch = blocks[i:i+BATCH]
    r3 = httpx.post(
        f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks/{doc_id}/children",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        content=json.dumps({"children": batch}, ensure_ascii=False),
        timeout=30,
    )
    result = r3.json()
    if result.get("code") == 0:
        added += len(batch)
        print(f"  Batch {i//BATCH + 1}/{ (len(blocks) + BATCH - 1)//BATCH }: {len(batch)} blocks OK")
    else:
        print(f"  Batch {i//BATCH + 1}: FAILED - {result.get('msg', '')[:100]}")

# Step 6: Verify and report
r4 = httpx.get(
    f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks/{doc_id}/children",
    headers={"Authorization": f"Bearer {token}"}, timeout=10)
items = r4.json().get("data", {}).get("items", [])
doc_url = f"https://bytedance.feishu.cn/docx/{doc_id}"

print(f"\n=== RESULT ===")
print(f"Blocks added: {added}/{len(blocks)}")
print(f"Blocks verified: {len(items)}")
print(f"Document: {doc_url}")
