import logging

from fastapi import HTTPException, Request, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    headers: dict | None = None,
):
    """
    Build a standardized JSON error response.

    Args:
        request (Request): Incoming FastAPI request.
        status_code (int): HTTP status code to return.
        code (str): Application-specific error identifier.
        message (str): Error message to return to the client.
        headers (dict | None): Optional HTTP response headers.

    Returns:
        JSONResponse: Standardized error response containing the error code, message, and correlation ID.
    """
        
    correlation_id = getattr(
        request.state, "correlation_id", None
    )

    return JSONResponse(
        status_code=status_code,
        headers={
            **(headers or {}),
            "X-Correlation-ID": correlation_id or "",
        },
        content={
            "error": {
                "code": code,
                "message": message,
                "correlation_id": correlation_id,
            }
        },
    )


def register_exception_handlers(app: FastAPI):
    """
    Register custom exception handlers with the FastAPI application.

    Handles application-specific errors, HTTP exceptions, request validation errors, and unexpected exceptions to ensure consistent error responses.

    Args:
        app (FastAPI): The FastAPI application instance.
    """

    handlers = {
        AppException: app_exception_handler,
        HTTPException: http_exception_handler,
        RequestValidationError: validation_exception_handler,
        Exception: unexpected_exception_handler,
    }

    for exception_type, handler in handlers.items():
        app.add_exception_handler(exception_type, handler)


async def app_exception_handler(
    request: Request,
    exc: AppException,
):
    """
    Handle custom application exceptions.

    Args:
        request (Request): Incoming FastAPI request.
        exc (AppException): Application-specific exception raised during request processing.

    Returns:
        JSONResponse: Standardized error response using the exception's status code, error code, and message.
    """
    return error_response(
        request, exc.status_code, exc.error_code, exc.message
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
):
    """
    Handle FastAPI HTTP exceptions.

    Args:
        request (Request): Incoming FastAPI request.
        exc (HTTPException): HTTP exception raised during request processing, including authentication failures.

    Returns:
        JSONResponse: Standardized HTTP error response containing the status code, error message, and correlation ID.
    """
    return error_response(
        request,
        exc.status_code,
        "HTTP_ERROR",
        str(exc.detail),
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    """
    Handle request validation errors raised by FastAPI/Pydantic.

    Args:
        request (Request): Incoming FastAPI request.
        exc (RequestValidationError): Exception raised when request data fails schema validation.

    Returns:
        JSONResponse: HTTP 422 response with a standardized validation error message and correlation ID.
    """
        
    return error_response(
        request,
        422,
        "VALIDATION_ERROR",
        "Invalid request data",
    )


async def unexpected_exception_handler(
    request: Request,
    exc: Exception,
):
    """
    Handle unexpected exceptions during request processing.

    Logs the original exception with its traceback and correlation ID for debugging and monitoring, while returning a generic error message to the client.

    Args:
        request (Request): Incoming FastAPI request.
        exc (Exception): Unhandled exception raised during request processing.

    Returns:
        JSONResponse: HTTP 500 response containing a generic error message and correlation ID, without exposing internal implementation details.
    """
        
    logger.error(
        "Unhandled request error; correlation_id=%s",
        getattr(request.state, "correlation_id", None),
        exc_info=(type(exc), exc, exc.__traceback__),
    )

    return error_response(
        request,
        500,
        "INTERNAL_SERVER_ERROR",
        "An unexpected error occurred",
    )