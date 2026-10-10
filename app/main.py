import asyncio
import hashlib
import hmac
import uuid
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, export, extract, llm
from .db import get_db, init_db
from .models import Conversation, Gap, Message, Occurrence, ReviewEvent
from .prompts import CHAT_SYSTEM

ALLOWED_IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}

init_db()
app = FastAPI(title="Personal English Agent")
app.mount("/static", StaticFiles(directory=config.BASE_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")


# ---------- 访问密码 ----------

AUTH_COOKIE = "access"
LOGIN_PAGE = config.BASE_DIR / "static" / "login.html"


def _auth_token() -> str:
    # 由密码派生；修改密码后旧的登录状态自动失效
    return hmac.new(config.ACCESS_PASSWORD.encode(), b"english-gap-access", hashlib.sha256).hexdigest()


@app.middleware("http")
async def require_password(request: Request, call_next):
    path = request.url.path
    if config.ACCESS_PASSWORD and path != "/login" and not path.startswith("/static/"):
        if not hmac.compare_digest(request.cookies.get(AUTH_COOKIE, ""), _auth_token()):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "请先登录"}, status_code=401)
            return RedirectResponse("/login", status_code=303)
    return await call_next(request)


@app.get("/login")
def login_page():
    return FileResponse(LOGIN_PAGE)


@app.post("/login")
async def login(request: Request, password: str = Form("")):
    if not config.ACCESS_PASSWORD:
        return RedirectResponse("/", status_code=303)
    if not hmac.compare_digest(password.encode(), config.ACCESS_PASSWORD.encode()):
        await asyncio.sleep(1)  # 拖慢暴力猜密码
        return RedirectResponse("/login?error=1", status_code=303)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        AUTH_COOKIE,
        _auth_token(),
        max_age=30 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=request.headers.get("x-forwarded-proto") == "https",
    )
    return resp


@app.get("/")
def index():
    return FileResponse(config.BASE_DIR / "static" / "index.html")


@app.get("/api/status")
def status():
    return {"model": config.LLM_MODEL, "mock": llm.is_mock()}


# ---------- 序列化 ----------

def _image_url(path: str | None) -> str | None:
    return f"/uploads/{path}" if path else None


def message_out(m: Message) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "text": m.text,
        "image_url": _image_url(m.image_path),
        "recorded": m.record_batch_id is not None,
        "created_at": m.created_at.isoformat(),
    }


def gap_out(g: Gap) -> dict:
    return {
        "id": g.id,
        "anchor_text": g.anchor_text,
        "kind": g.kind,
        "skills": g.skills,
        "core_note": g.core_note,
        "status": g.status,
        "review_count": g.review_count,
        "created_at": g.created_at.isoformat(),
        "updated_at": g.updated_at.isoformat(),
        "occurrences": [
            {
                "id": o.id,
                "conversation_id": o.conversation_id,
                "scene": o.scene,
                "question": o.question,
                "user_attempt": o.user_attempt,
                "error": o.error,
                "clarified": o.clarified,
                "evidence": o.evidence,
                "image_url": _image_url(o.image_path),
                "created_at": o.created_at.isoformat(),
            }
            for o in g.occurrences
        ],
    }


def _get_conv(db: Session, conv_id: int) -> Conversation:
    conv = db.get(Conversation, conv_id)
    if conv is None:
        raise HTTPException(404, "对话不存在")
    return conv


def _get_gap(db: Session, gap_id: int) -> Gap:
    gap = db.get(Gap, gap_id)
    if gap is None:
        raise HTTPException(404, "GAP 不存在")
    return gap


# ---------- 对话 ----------

@app.post("/api/conversations")
def create_conversation(db: Session = Depends(get_db)):
    conv = Conversation(source="screenshot")
    db.add(conv)
    db.commit()
    return {"id": conv.id, "title": conv.title}


@app.get("/api/conversations")
def list_conversations(db: Session = Depends(get_db)):
    convs = db.scalars(select(Conversation).order_by(Conversation.id.desc()).limit(100)).all()
    return [
        {
            "id": c.id,
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "pending": sum(1 for m in c.messages if m.record_batch_id is None),
        }
        for c in convs
    ]


@app.get("/api/conversations/{conv_id}")
def get_conversation(conv_id: int, db: Session = Depends(get_db)):
    conv = _get_conv(db, conv_id)
    return {"id": conv.id, "title": conv.title, "messages": [message_out(m) for m in conv.messages]}


@app.post("/api/conversations/{conv_id}/messages")
def send_message(
    conv_id: int,
    text: str = Form(""),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    conv = _get_conv(db, conv_id)
    text = text.strip()
    image_path = None
    if image is not None and image.filename:
        ext = ALLOWED_IMAGE_TYPES.get(image.content_type or "")
        if ext is None:
            raise HTTPException(400, "只支持 PNG / JPEG / WebP / GIF 图片")
        image_path = f"{uuid.uuid4().hex}{ext}"
        (config.UPLOAD_DIR / image_path).write_bytes(image.file.read())
    if not text and not image_path:
        raise HTTPException(400, "请输入问题或选择截图")

    user_msg = Message(conversation_id=conv.id, role="user", text=text, image_path=image_path)
    db.add(user_msg)
    if conv.title == "新对话":
        conv.title = text[:30] if text else "截图提问"
    db.flush()

    history: list[dict] = [{"role": "system", "content": CHAT_SYSTEM}]
    for m in conv.messages:
        if m.role == "user":
            parts: list[dict] = [{"type": "text", "text": m.text or "（请看截图）"}]
            if m.image_path:
                parts.append(llm.image_part(config.UPLOAD_DIR / m.image_path))
            history.append({"role": "user", "content": parts})
        else:
            history.append({"role": "assistant", "content": m.text})

    try:
        reply = llm.complete(history)
    except llm.LLMError as e:
        db.rollback()
        raise HTTPException(502, str(e))

    ai_msg = Message(conversation_id=conv.id, role="assistant", text=reply)
    db.add(ai_msg)
    db.commit()
    return {"user": message_out(user_msg), "assistant": message_out(ai_msg)}


@app.post("/api/conversations/{conv_id}/record")
def record_conversation(conv_id: int, db: Session = Depends(get_db)):
    conv = _get_conv(db, conv_id)
    try:
        results = extract.record(db, conv)
    except extract.NothingToRecord:
        raise HTTPException(400, "上次记录之后没有新的对话")
    except llm.LLMError as e:
        db.rollback()
        raise HTTPException(502, str(e))
    return {"gaps": results}


# ---------- GAP ----------

def _query_gaps(db: Session, start: date | None, end: date | None, skill: str | None, status: str | None):
    stmt = select(Gap)
    if start or end:
        occ = select(Occurrence.gap_id)
        if start:
            occ = occ.where(Occurrence.created_at >= datetime.combine(start, datetime.min.time()))
        if end:
            occ = occ.where(Occurrence.created_at < datetime.combine(end + timedelta(days=1), datetime.min.time()))
        stmt = stmt.where(Gap.id.in_(occ))
    if status:
        stmt = stmt.where(Gap.status == status)
    gaps = db.scalars(stmt.order_by(Gap.updated_at.desc())).all()
    if skill:  # skills 是 JSON 列，在 Python 里过滤更直观
        gaps = [g for g in gaps if skill in g.skills]
    return gaps


@app.get("/api/gaps")
def list_gaps(
    start: date | None = None,
    end: date | None = None,
    skill: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    return [gap_out(g) for g in _query_gaps(db, start, end, skill, status)]


class GapPatch(BaseModel):
    anchor_text: str | None = None
    core_note: str | None = None
    status: Literal["active", "solved"] | None = None


@app.patch("/api/gaps/{gap_id}")
def update_gap(gap_id: int, patch: GapPatch, db: Session = Depends(get_db)):
    gap = _get_gap(db, gap_id)
    if patch.anchor_text is not None:
        gap.anchor_text = patch.anchor_text.strip()
        gap.norm_key = extract.norm_key(gap.anchor_text)
    if patch.core_note is not None:
        gap.core_note = patch.core_note.strip()
    if patch.status is not None:
        gap.status = patch.status
    gap.updated_at = datetime.now()
    db.commit()
    return gap_out(gap)


@app.delete("/api/gaps/{gap_id}")
def delete_gap(gap_id: int, db: Session = Depends(get_db)):
    db.delete(_get_gap(db, gap_id))
    db.commit()
    return {"ok": True}


# ---------- 复习（翻卡） ----------

@app.get("/api/review/next")
def review_next(skill: str | None = None, db: Session = Depends(get_db)):
    """未解决的 GAP 中，最久没复习的排在最前；从没复习过的最优先。"""
    gaps = _query_gaps(db, None, None, skill, "active")
    if not gaps:
        return {"gap": None, "remaining": 0}
    gaps.sort(key=lambda g: (g.last_reviewed_at is not None, g.last_reviewed_at or g.created_at))
    return {"gap": gap_out(gaps[0]), "remaining": len(gaps)}


class ReviewIn(BaseModel):
    result: Literal["remembered", "forgot", "solved"]


@app.post("/api/review/{gap_id}")
def review_gap(gap_id: int, body: ReviewIn, db: Session = Depends(get_db)):
    gap = _get_gap(db, gap_id)
    db.add(ReviewEvent(gap_id=gap.id, result=body.result))
    gap.last_reviewed_at = datetime.now()
    gap.review_count += 1
    if body.result == "solved":
        gap.status = "solved"
    db.commit()
    return {"ok": True}


# ---------- 导出 ----------

@app.get("/api/templates")
def list_templates():
    return [{"id": k, "name": v[0]} for k, v in export.TEMPLATES.items()]


@app.get("/api/export", response_class=HTMLResponse)
def export_gaps(
    template: str = "general",
    start: date | None = None,
    end: date | None = None,
    skill: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    if template not in export.TEMPLATES:
        raise HTTPException(400, "未知模板")
    gaps = _query_gaps(db, start, end, skill, status)
    period = f"{start or '最早'} 至 {end or '今天'}"
    title = f"英语 GAP 整理（{period}{'，' + skill if skill else ''}）"
    html = export.render(template, gaps, title)
    filename = f"gaps_{date.today().isoformat()}.html"
    return HTMLResponse(html, headers={"Content-Disposition": f'inline; filename="{filename}"'})
