"""Brand imagery: the Deep Research Agent illustration, cropped and resized once per process."""
from __future__ import annotations

import base64
import io

import streamlit as st

from src.config import PROJECT_ROOT

LOGO_PATH = PROJECT_ROOT / "images" / "res_agent_in_lapcoat.jpg"


@st.cache_resource(show_spinner=False)
def _variants() -> dict[str, bytes]:
    """JPEG bytes for the hero illustration and a square avatar crop of the robot's face (empty if missing)."""
    if not LOGO_PATH.exists():
        return {}
    from PIL import Image

    with Image.open(LOGO_PATH) as original:
        image = original.convert("RGB")
    w, h = image.size
    side = int(min(w, h) * 0.62)  # the robot's head sits a little right of centre, in the upper half
    left = max(0, min(w - side, int(w * 0.515) - side // 2))
    top = max(0, min(h - side, int(h * 0.30) - side // 2))
    square = image.crop((left, top, left + side, top + side)).resize((256, 256), Image.LANCZOS)
    hero = image.copy()
    hero.thumbnail((1280, 1280), Image.LANCZOS)

    def encode(img) -> bytes:
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=84, optimize=True)
        return buffer.getvalue()
    return {"hero": encode(hero), "square": encode(square)}


def logo_bytes(kind: str = "square") -> bytes | None:
    return _variants().get(kind)


def logo_data_uri(kind: str = "hero") -> str:
    data = logo_bytes(kind)
    return f"data:image/jpeg;base64,{base64.b64encode(data).decode()}" if data else ""


def brand_logo() -> None:
    """The robot avatar at the top of the sidebar menu."""
    square = logo_bytes("square")
    if square:
        st.logo(square, size="large", icon_image=square)
