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

        # If your AUTH_USER_MODEL is 'golden.Author', request.user is already an Author
        if isinstance(user, Author):
            request.current_author = user
            return view_func(request, *args, **kwargs)

        # Otherwise, resolve by username string
        username = getattr(user, "username", None) or user.get_username()
        try:
            request.current_author = Author.objects.get(username=username)
        except Author.DoesNotExist:
            # No Author record yet → send them to signup, as you requested
            return redirect("signup")

        return view_func(request, *args, **kwargs)
    return _wrapped

