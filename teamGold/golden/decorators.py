from functools import wraps
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from .models import Author

def require_author(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return redirect("login")

        if isinstance(user, Author):
            request.current_author = user
            return view_func(request, *args, **kwargs)

        username = getattr(user, "username", None) or user.get_username()
        try:
            request.current_author = Author.objects.get(username=username)
        except Author.DoesNotExist:
            return redirect("signup")

        return view_func(request, *args, **kwargs)
    return _wrapped

