"""Generate mock subtitles for pipeline testing."""
import json, os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

prompt = """请为B站视频《学生时代最重要的三次选择是什么？》(UP主: 孙熙然, 约7分37秒) 生成一份模拟的讲座类字幕数据。

要求：
1. 生成约50条字幕，模拟真实口语节奏
2. 每条字幕JSON格式: {"from": 开始秒数, "to": 结束秒数, "content": "字幕文本"}
3. 内容主题：初中/高中/大学三个关键选择节点，对人生的影响
4. 每句话10-30字，模拟真实讲座口吻
5. 覆盖完整7分钟
6. 直接输出纯JSON数组，不要markdown代码块，不要任何其他文字"""

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.7,
    max_tokens=8192,
)

content = response.choices[0].message.content.strip()

# Clean up markdown code blocks if present
if content.startswith("```"):
    lines = content.split("\n")
    content = "\n".join(lines[1:]) if len(lines) > 1 else content
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

# Validate JSON
data = json.loads(content)
print(f"Generated {len(data)} subtitle entries")

with open("test_subtitles.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Saved to test_subtitles.json")
