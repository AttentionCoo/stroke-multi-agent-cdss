"""前端实际链路验证: backend SSE → model"""
import sys

sys.path.insert(0, "/app")
import httpx
import json

# 登录获取 token
login = httpx.post(
    "http://localhost:8080/api/user/login",
    json={"name": "admin", "password": "admin123"},
    timeout=15,
)
token = login.json()["data"]["token"]
print("LOGIN_OK token_len:", len(token))

# 通过 backend SSE 发病例(前端真实路径)
url = "http://localhost:8080/api/user/ques/streamingQues"
body = {
    "question": "男69岁,突发右侧偏瘫、混合性失语90分钟,房颤史,NIHSS评分18分,CT未见出血",
    "talkId": "", "images": [],
}
headers = {"token": token, "Authorization": token}

errors = 0
done = False
nodes = set()
with httpx.stream("POST", url, json=body, headers=headers, timeout=600) as r:
    print("STATUS:", r.status_code)
    for line in r.iter_lines():
        if not line.strip():
            continue
        raw = line.strip()
        if raw.startswith("data:"):
            raw = raw[5:].strip()
        try:
            ev = json.loads(raw)
        except Exception:
            continue
        t = ev.get("type", "")
        if t == "error":
            errors += 1
        if t == "thinking":
            th = ev.get("thinking", {}) or {}
            nodes.add(th.get("step", "") or th.get("title", ""))
        if t == "done":
            done = True

print("DONE:", done)
print("ERRORS:", errors)
print("THINKING_STEPS:", len(nodes))
print("SAMPLE:", sorted(nodes)[:8])
