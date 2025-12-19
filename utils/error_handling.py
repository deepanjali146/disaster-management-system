from functools import wraps
from flask import flash, redirect, url_for
from utils.logger import log_exception


def handle_errors(redirect_endpoint: str, default_message: str = "An error occurred.", category: str = "danger"):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as err:
                # Log error and flash a friendly message
                try:
                    log_exception(err, context=f"{func.__name__}:")
                except Exception:
                    pass
                try:
                    flash(f"{default_message} {err}", category)
                except Exception:
                    pass
                try:
                    return redirect(url_for(redirect_endpoint))
                except Exception:
                    # As a last resort, just redirect to root
                    return redirect("/")
        return wrapper
    return decorator


