"""Error envelope {error:{code,message,details}, request_id}; codes from contracts/behavior.md."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger('ottv2.errors')

MESSAGES = {
    'INVALID_REQUEST': 'Dữ liệu không hợp lệ',
    'UNAUTHORIZED': 'Chưa đăng nhập hoặc phiên đã hết hạn',
    'FORBIDDEN': 'Không có quyền thực hiện thao tác này',
    'NOT_FOUND': 'Không tìm thấy tài nguyên',
    'STATE_CONFLICT': 'Trạng thái hiện tại không cho phép thao tác này',
    'IDEMPOTENCY_CONFLICT': 'Idempotency-Key đã được dùng cho yêu cầu khác',
    'REQUEST_IN_PROGRESS': 'Yêu cầu cùng Idempotency-Key đang được xử lý',
    'PAYLOAD_TOO_LARGE': 'Dữ liệu tải lên quá lớn',
    'RATE_LIMITED': 'Gửi yêu cầu quá nhanh, vui lòng thử lại sau',
    'SERVICE_UNAVAILABLE': 'Dịch vụ tạm thời không sẵn sàng',
    'INTERNAL_ERROR': 'Lỗi máy chủ',
    'SUBMISSION_NOT_READY': 'Bản nộp chưa sẵn sàng',
    'SELF_SCRIMMAGE': 'Không thể đánh tập với chính đội mình',
    'QUOTA_EXCEEDED': 'Đã hết hạn mức đánh tập hôm nay',
    'ROUND_NOT_FROZEN': 'Vòng đấu chưa được đóng băng',
    'DOWNSTREAM_STARTED': 'Vòng sau đã đóng băng hoặc giải đã kết thúc',
    'RULESET_UNCONFIRMED': 'Bộ luật chưa được ban tổ chức xác nhận; chưa thể điều hành giải',
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str | None = None, details: dict[str, Any] | None = None,
                 headers: dict[str, str] | None = None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message or MESSAGES.get(code, code)
        self.details = details or {}
        self.headers = headers or {}


def invalid(message: str | None = None, **details: Any) -> ApiError:
    return ApiError(422, 'INVALID_REQUEST', message, details)


def not_found(message: str | None = None) -> ApiError:
    return ApiError(404, 'NOT_FOUND', message)


def conflict(code: str = 'STATE_CONFLICT', message: str | None = None, **details: Any) -> ApiError:
    return ApiError(409, code, message, details)


def request_id(request: Request) -> str:
    rid = getattr(request.state, 'request_id', None)
    if rid is None:
        rid = str(uuid.uuid4())
        request.state.request_id = rid
    return rid


def envelope(request: Request, status: int, code: str, message: str, details: dict | None = None,
             headers: dict[str, str] | None = None) -> JSONResponse:
    body = {'error': {'code': code, 'message': message, 'details': details or {}}, 'request_id': request_id(request)}
    return JSONResponse(body, status_code=status, headers=headers)


def install(app: FastAPI) -> None:
    @app.middleware('http')
    async def _request_id(request: Request, call_next):
        rid = request_id(request)
        response = await call_next(request)
        response.headers['X-Request-ID'] = rid
        return response

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        request.state.error_code = exc.code
        return envelope(request, exc.status, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        fields = [{'field': '/' + '/'.join(str(p) for p in e.get('loc', ())), 'reason': str(e.get('msg', ''))[:300]}
                  for e in exc.errors()][:20]
        return envelope(request, 422, 'INVALID_REQUEST', MESSAGES['INVALID_REQUEST'], {'errors': fields})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {401: 'UNAUTHORIZED', 403: 'FORBIDDEN', 404: 'NOT_FOUND', 413: 'PAYLOAD_TOO_LARGE',
                429: 'RATE_LIMITED'}.get(exc.status_code, 'INVALID_REQUEST')
        return envelope(request, exc.status_code, code, MESSAGES[code])

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        log.exception('Unhandled error request_id=%s', request_id(request))
        return envelope(request, 500, 'INTERNAL_ERROR', MESSAGES['INTERNAL_ERROR'])
