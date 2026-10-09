"""按模板把 GAP 导出为独立 HTML 文件（图片内嵌，可直接打印成 PDF）。"""

import base64
import mimetypes
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config

TEMPLATES = {
    "general": ("通用卡片", "export_general.html.j2"),
    "table": ("单词表格", "export_table.html.j2"),
}

_env = Environment(
    loader=FileSystemLoader(config.BASE_DIR / "app" / "templates"),
    autoescape=select_autoescape(["html", "j2"]),
)


def _data_uri(image_path: str | None) -> str | None:
    if not image_path:
        return None
    path = config.UPLOAD_DIR / image_path
    if not path.exists():
        return None
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


_env.filters["data_uri"] = _data_uri


def render(template: str, gaps: list, title: str) -> str:
    _, filename = TEMPLATES[template]
    return _env.get_template(filename).render(
        gaps=gaps, title=title, generated_at=datetime.now()
    )
