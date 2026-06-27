"""
基于 Flask 的 B站视频笔记 Web 界面
手机和电脑在同一 WiFi 下，手机浏览器访问电脑 IP:7777 即可使用
"""
import sys, os, json, logging, re, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, render_template_string
from src.pipeline import VideoNotePipeline
from src.feishu.doc_creator import send_feishu_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web_bot")

app = Flask(__name__)
pipeline = None

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
USER_OPEN_ID = "ou_8f095b2b3e6f57cc218fd91e003b831c"

PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>B站视频笔记</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, sans-serif; background: #f5f5f5; padding: 16px; }
h1 { font-size: 20px; text-align: center; margin: 16px 0; color: #333; }
.card { background: white; border-radius: 12px; padding: 16px; margin: 12px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
input { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 16px; }
button { width: 100%; padding: 14px; background: #00a6ff; color: white; border: none; border-radius: 8px; font-size: 18px; margin-top: 12px; cursor: pointer; }
button:active { opacity: 0.8; }
#status { margin-top: 12px; padding: 12px; border-radius: 8px; display: none; font-size: 14px; }
#status.processing { display: block; background: #fff3cd; color: #856404; }
#status.done { display: block; background: #d4edda; color: #155724; }
#status.error { display: block; background: #f8d7da; color: #721c24; }
a { color: #00a6ff; word-break: break-all; }
.spinner { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
</style>
</head>
<body>
<h1>📺 B站视频 → 飞书笔记</h1>
<div class="card">
    <input id="url" type="text" placeholder="粘贴B站视频链接或BV号" autofocus>
    <button onclick="submit()">生成笔记</button>
    <div id="status"></div>
</div>
<script>
async function submit() {
    const url = document.getElementById('url').value.trim();
    if (!url) return;

    const status = document.getElementById('status');
    status.className = 'processing';
    status.innerHTML = '<span class="spinner">⏳</span> 处理中...';

    try {
        const resp = await fetch('/process', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url: url})
        });
        const data = await resp.json();
        if (data.success) {
            status.className = 'done';
            status.innerHTML = '✅ 完成！<br><br>📝 全文实录：<br><a href="' + data.transcript + '">' + data.transcript + '</a><br><br>📋 结构化笔记：<br><a href="' + data.notes + '">' + data.notes + '</a>';
        } else {
            status.className = 'error';
            status.textContent = '❌ ' + data.error;
        }
    } catch(e) {
        status.className = 'error';
        status.textContent = '❌ 网络错误：' + e.message;
    }
}
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/process", methods=["POST"])
def process():
    data = request.get_json()
    url = data.get("url", "").strip()
    if not url:
        return {"success": False, "error": "请输入B站链接"}

    logger.info(f"Processing: {url}")

    try:
        result = pipeline.process(url, user_open_id=USER_OPEN_ID)
        if result.success:
            # 获取两个文档链接
            # result.doc_url 是 transcript 的 URL
            # 需要从 pipeline 获取 notes 文档的 URL
            return {"success": True, "transcript": result.doc_url, "notes": "请查看飞书通知"}
        else:
            return {"success": False, "error": result.error_message}
    except Exception as e:
        return {"success": False, "error": str(e)}


def start(p: VideoNotePipeline, port: int = 7777):
    global pipeline
    pipeline = p

    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    print("=" * 60)
    print("  B站视频笔记 - Web界面")
    print(f"  手机浏览器打开: http://{local_ip}:{port}")
    print("=" * 60)

    app.run(host="0.0.0.0", port=port, debug=False)
