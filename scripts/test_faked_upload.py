import json
import time
import urllib.request
from pathlib import Path

BASE = "http://localhost:8000"
PATH = "data/Faked_List_proportional (2).xlsx"
OUT = "scripts/faked_upload_dump.txt"

lines = []

# 1. Загрузка файла
boundary = "----evrazbench"
with open(PATH, "rb") as fh:
    content = fh.read()
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="{Path(PATH).name}"\r\n'
    f"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

req = urllib.request.Request(
    f"{BASE}/files/upload",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=60) as resp:
    upload = json.loads(resp.read().decode("utf-8"))
lines.append(f"upload: {json.dumps(upload, ensure_ascii=False)[:300]}")
file_id = upload["file"]["id"]
lines.append(f"file_id: {file_id}")

# 2. Ждём обработку
for attempt in range(30):
    time.sleep(2)
    with urllib.request.urlopen(f"{BASE}/files/{file_id}/status", timeout=30) as resp:
        status = json.loads(resp.read().decode("utf-8"))
    st = status.get("status", "?")
    lines.append(f"attempt {attempt}: status={st}")
    if st in ("processed", "ready", "error"):
        break

lines.append(f"final: {json.dumps(status, ensure_ascii=False, indent=2)[:2000]}")

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
print("written", OUT)