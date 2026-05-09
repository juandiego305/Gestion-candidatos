from rest_framework.exceptions import AuthenticationFailed
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """Normalize auth timeout errors to a predictable JSON shape."""
    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, AuthenticationFailed):
        detail = response.data.get("detail")
        if isinstance(detail, dict):
            response.data = {
                "error_code": str(detail.get("error_code", "AUTHENTICATION_FAILED")),
                "detail": str(detail.get("detail", "Authentication failed.")),
            }

    return response
