"""端到端流程测试（演示模式，不调用真实模型）：截图提问 → 记录 → 列表 → 复习 → 导出。"""

import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="english_gap_test_")
os.environ["LLM_MODEL"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

# 1x1 PNG
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def new_conv() -> int:
    return client.post("/api/conversations").json()["id"]


def ask(conv_id: int, text: str, image: bool = False):
    files = {"image": ("shot.png", PNG, "image/png")} if image else None
    return client.post(f"/api/conversations/{conv_id}/messages", data={"text": text}, files=files)


def test_full_flow():
    cid = new_conv()
    r = ask(cid, "Normal University 里的 normal 是什么意思？", image=True)
    assert r.status_code == 200
    assert r.json()["user"]["image_url"].startswith("/uploads/")

    r = client.post(f"/api/conversations/{cid}/record")
    assert r.status_code == 200
    gaps = r.json()["gaps"]
    assert len(gaps) == 1 and gaps[0]["is_new"]
    gap_id = gaps[0]["gap_id"]

    # 没有新消息时不能重复记录
    assert client.post(f"/api/conversations/{cid}/record").status_code == 400

    listed = client.get("/api/gaps").json()
    gap = next(g for g in listed if g["id"] == gap_id)
    assert gap["occurrences"][0]["image_url"].startswith("/uploads/")

    # 复习：已解决后不再出现在队列中
    assert client.get("/api/review/next").json()["gap"] is not None
    assert client.post(f"/api/review/{gap_id}", json={"result": "solved"}).status_code == 200
    ids = [g["id"] for g in client.get("/api/gaps", params={"status": "active"}).json()]
    assert gap_id not in ids

    for template in ("general", "table"):
        r = client.get("/api/export", params={"template": template})
        assert r.status_code == 200
        assert "data:image/png;base64," in r.text


def test_same_anchor_merges_and_reactivates():
    cid = new_conv()
    ask(cid, "split the bill 是什么意思")
    first = client.post(f"/api/conversations/{cid}/record").json()["gaps"][0]
    client.post(f"/api/review/{first['gap_id']}", json={"result": "solved"})

    cid2 = new_conv()
    ask(cid2, "Split the bill 和 pay separately 有什么区别")
    second = client.post(f"/api/conversations/{cid2}/record").json()["gaps"][0]

    assert second["gap_id"] == first["gap_id"] and not second["is_new"]
    gap = next(g for g in client.get("/api/gaps").json() if g["id"] == first["gap_id"])
    assert gap["status"] == "active"
    assert len(gap["occurrences"]) == 2


def test_rejects_empty_message():
    cid = new_conv()
    assert ask(cid, "  ").status_code == 400
