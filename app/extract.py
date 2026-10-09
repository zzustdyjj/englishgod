"""“记录”流程：把上次记录之后的对话交给模型提炼 GAP，再与已有 GAP 合并入库。"""

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, llm
from .models import Conversation, Gap, Message, Occurrence, RecordBatch
from .prompts import EXTRACT_SYSTEM

EXISTING_GAP_LIMIT = 300
EVIDENCE_LEVELS = {"已解释", "提示下复述", "独立说出", "新场景用对"}
SKILLS = {"读", "听", "说", "写"}


class NothingToRecord(Exception):
    pass


def norm_key(text: str) -> str:
    text = text.lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"[\"“”.,!?;:()\[\]]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _build_prompt(db: Session, messages: list[Message]) -> tuple[list[dict], dict[int, str]]:
    """返回给模型的 user 内容（文字 + 截图），以及 截图编号 → 文件名 的映射。"""
    parts: list[dict] = []
    image_map: dict[int, str] = {}

    existing = db.scalars(
        select(Gap).order_by(Gap.updated_at.desc()).limit(EXISTING_GAP_LIMIT)
    ).all()
    gap_lines = "\n".join(f"#{g.id} {g.anchor_text}" for g in existing) or "（暂无）"
    parts.append({"type": "text", "text": f"已有 GAP 列表：\n{gap_lines}\n\n本次学习对话："})

    for m in messages:
        speaker = "用户" if m.role == "user" else "AI"
        line = f"{speaker}：{m.text}"
        if m.image_path:
            n = len(image_map) + 1
            image_map[n] = m.image_path
            line += f" [图片{n}]"
        parts.append({"type": "text", "text": line})
        if m.image_path:
            parts.append(llm.image_part(config.UPLOAD_DIR / m.image_path))
    return parts, image_map


def _clean_str(value) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def record(db: Session, conv: Conversation) -> list[dict]:
    pending = [m for m in conv.messages if m.record_batch_id is None]
    if not pending:
        raise NothingToRecord()

    parts, image_map = _build_prompt(db, pending)
    raw = llm.complete(
        [{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": parts}]
    )
    items = llm.parse_json(raw).get("gaps") or []

    batch = RecordBatch(conversation_id=conv.id)
    db.add(batch)
    db.flush()

    results = []
    for item in items:
        anchor = _clean_str(item.get("anchor_text"))
        occ = item.get("occurrence") or {}
        if not anchor:
            continue

        gap = None
        gid = item.get("existing_gap_id")
        if isinstance(gid, int):
            gap = db.get(Gap, gid)
        if gap is None:
            gap = db.scalars(select(Gap).where(Gap.norm_key == norm_key(anchor))).first()

        is_new = gap is None
        if is_new:
            gap = Gap(
                anchor_text=anchor,
                norm_key=norm_key(anchor),
                kind=_clean_str(item.get("kind")) or "",
                skills=[s for s in item.get("skills") or [] if s in SKILLS],
                core_note=_clean_str(item.get("core_note")) or "",
            )
            db.add(gap)
            db.flush()
        else:
            # 再次遇见说明还没掌握：重新激活，并补充新出现的技能类别
            gap.status = "active"
            new_skills = [s for s in item.get("skills") or [] if s in SKILLS]
            gap.skills = sorted(set(gap.skills) | set(new_skills))
            gap.updated_at = datetime.now()

        evidence = _clean_str(occ.get("evidence"))
        image_ref = occ.get("image_ref")
        db.add(
            Occurrence(
                gap_id=gap.id,
                conversation_id=conv.id,
                record_batch_id=batch.id,
                scene=_clean_str(occ.get("scene")) or "",
                question=_clean_str(occ.get("question")) or "",
                user_attempt=_clean_str(occ.get("user_attempt")),
                error=_clean_str(occ.get("error")),
                clarified=_clean_str(occ.get("clarified")) or "",
                evidence=evidence if evidence in EVIDENCE_LEVELS else "已解释",
                image_path=image_map.get(image_ref) if isinstance(image_ref, int) else None,
            )
        )
        results.append({"gap_id": gap.id, "anchor_text": gap.anchor_text, "is_new": is_new})

    for m in pending:
        m.record_batch_id = batch.id
    db.commit()
    return results
