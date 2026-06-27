"""Step 2: Write existing markdown to Feishu doc (no AI call)"""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

import httpx
from src.feishu.doc_creator import markdown_to_feishu_blocks

app_id = os.getenv("FEISHU_APP_ID")
app_secret = os.getenv("FEISHU_APP_SECRET")

# Read existing markdown
with open("test_output.md", "r", encoding="utf-8") as f:
    md = f.read()
print(f"Markdown: {len(md)} chars", flush=True)

# Convert to blocks
blocks = markdown_to_feishu_blocks(md)
print(f"Blocks: {len(blocks)}", flush=True)

# Get token
print("Getting token...", flush=True)
r = httpx.post(
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    data={"app_id": app_id, "app_secret": app_secret},
    timeout=15,
)
token = r.json()["tenant_access_token"]
print(f"Token OK: {token[:16]}...", flush=True)

# Create doc
print("Creating doc...", flush=True)
r2 = httpx.post(
    "https://open.feishu.cn/open-apis/docx/v1/documents",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    content=json.dumps({"title": "【视频笔记】学生时代最重要的三次选择"}, ensure_ascii=False),
    timeout=15,
)
doc_result = r2.json()
if doc_result.get("code") != 0:
    print(f"Doc create FAILED: {doc_result.get('msg')}", flush=True)
    sys.exit(1)
doc_id = doc_result["data"]["document"]["document_id"]
print(f"Doc created: {doc_id}", flush=True)

# Add blocks
BATCH = 20
added = 0
total_batches = (len(blocks) + BATCH - 1) // BATCH
for i in range(0, len(blocks), BATCH):
    batch = blocks[i:i+BATCH]
    batch_num = i // BATCH + 1
    try:
        r3 = httpx.post(
            f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks/{doc_id}/children",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            content=json.dumps({"children": batch}, ensure_ascii=False),
            timeout=30,
        )
        result = r3.json()
        if result.get("code") == 0:
            added += len(batch)
            print(f"  [{batch_num}/{total_batches}] {len(batch)} blocks OK", flush=True)
        else:
            code = result.get("code")
            msg = result.get("msg", "")
            print(f"  [{batch_num}/{total_batches}] FAIL: {code} - {msg[:120]}", flush=True)
    except Exception as e:
        print(f"  [{batch_num}/{total_batches}] ERROR: {e}", flush=True)

# Verify
r4 = httpx.get(
    f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks/{doc_id}/children",
    headers={"Authorization": f"Bearer {token}"},
    timeout=15,
)
items = r4.json().get("data", {}).get("items", [])
doc_url = f"https://bytedance.feishu.cn/docx/{doc_id}"

print(f"\n=== DONE ===", flush=True)
print(f"Added: {added}/{len(blocks)} blocks", flush=True)
print(f"Verified: {len(items)} in doc", flush=True)
print(f"URL: {doc_url}", flush=True)
