"""数据模型。

原始对话（Conversation / Message）永远保留；
Gap 是从对话中提炼出的“表达锚点”，每次遇见记为一条 Occurrence。
"""

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="新对话")
    # screenshot | text | voice | course，demo 只用 screenshot
    source: Mapped[str] = mapped_column(String(20), default="screenshot")
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.id", cascade="all, delete-orphan"
    )


class RecordBatch(Base):
    """用户点一次“记录”产生一批，覆盖上次记录之后的所有消息。"""

    __tablename__ = "record_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    text: Mapped[str] = mapped_column(Text, default="")
    image_path: Mapped[str | None] = mapped_column(String(300))  # 相对 UPLOAD_DIR
    record_batch_id: Mapped[int | None] = mapped_column(ForeignKey("record_batches.id"))
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Gap(Base):
    __tablename__ = "gaps"

    id: Mapped[int] = mapped_column(primary_key=True)
    anchor_text: Mapped[str] = mapped_column(String(300))
    norm_key: Mapped[str] = mapped_column(String(300), index=True)
    kind: Mapped[str] = mapped_column(String(50), default="")  # 单词/词块/表达/语法/发音/听辨…（开放）
    skills: Mapped[list] = mapped_column(JSON, default=list)  # 读/听/说/写
    core_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | solved
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.now)
    last_reviewed_at: Mapped[datetime | None] = mapped_column()
    review_count: Mapped[int] = mapped_column(default=0)

    occurrences: Mapped[list["Occurrence"]] = relationship(
        back_populates="gap", order_by="Occurrence.id", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["ReviewEvent"]] = relationship(cascade="all, delete-orphan")


class Occurrence(Base):
    """一次遇见：情景 + 疑问 + 用户原话/错误 + 弄清楚了什么。"""

    __tablename__ = "occurrences"

    id: Mapped[int] = mapped_column(primary_key=True)
    gap_id: Mapped[int] = mapped_column(ForeignKey("gaps.id"))
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    record_batch_id: Mapped[int] = mapped_column(ForeignKey("record_batches.id"))
    scene: Mapped[str] = mapped_column(Text, default="")
    question: Mapped[str] = mapped_column(Text, default="")
    user_attempt: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    clarified: Mapped[str] = mapped_column(Text, default="")
    # 已解释 / 提示下复述 / 独立说出 / 新场景用对
    evidence: Mapped[str] = mapped_column(String(30), default="已解释")
    image_path: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    gap: Mapped[Gap] = relationship(back_populates="occurrences")


class ReviewEvent(Base):
    __tablename__ = "review_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    gap_id: Mapped[int] = mapped_column(ForeignKey("gaps.id"))
    result: Mapped[str] = mapped_column(String(20))  # remembered | forgot | solved
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
