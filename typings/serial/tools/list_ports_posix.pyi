from __future__ import annotations

from typing import Protocol

class ListPortInfo(Protocol):
    device: str
    description: str
    hwid: str
    vid: int | None
    pid: int | None
    product: str | None
    name: str

def comports() -> list[ListPortInfo]: ...
