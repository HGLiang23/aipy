"""Application errors raised by write actions.

State-changing endpoints need more than a bare HTTP status: the frontend has to
tell "you may not do this" (403) apart from "somebody else got there first"
(409/412) and "this action makes no sense here" (409). Each of those carries a
machine-readable ``code`` so the UI can react without parsing prose.
"""

from fastapi import HTTPException


class ActionError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail

    def as_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=self.status_code,
            detail={"code": self.code, "detail": self.detail},
        )
