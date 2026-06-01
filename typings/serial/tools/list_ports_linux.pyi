from __future__ import annotations

class SysFS:
    device: str
    description: str
    hwid: str
    vid: int | None
    pid: int | None
    product: str | None
    subsystem: str
    name: str

    def __init__(self, device: str) -> None: ...

def comports(
    include_links: bool = ..., _hide_subsystems: list[str] | None = ...
) -> list[SysFS]: ...
