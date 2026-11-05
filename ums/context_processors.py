def navigation(request):
    if not request.user.is_authenticated:
        return {}
    from .views import _role_modules
    return {"modules": _role_modules(request.user), "unread_notifications": request.user.notifications.filter(read_at__isnull=True).count()}