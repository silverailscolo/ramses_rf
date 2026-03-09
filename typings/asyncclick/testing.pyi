"""Local type stubs for asyncclick.testing."""

from typing import Any

class Result:
    exit_code: int
    exception: BaseException | None
    return_value: Any
    output: str

class CliRunner:
    def __init__(self, **kwargs: Any) -> None: ...
    async def invoke(self, cli: Any, args: Any = None, **kwargs: Any) -> Result: ...
    def isolated_filesystem(self) -> Any: ...
