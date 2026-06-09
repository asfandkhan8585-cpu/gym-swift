from .models import Gym, UserProfile

def current_gym(request):
    """Expose gym, theme choices, owner-mode flag, and currency symbol to templates.
    Reuses the request-cached gym set by get_gym() to avoid extra queries."""
    ctx = {
        'current_gym': None,
        'theme_choices': Gym.THEME_CHOICES,
        'owner_mode': bool(request.session.get('owner_mode')) if hasattr(request, 'session') else False,
        'currency': 'Rs.',
    }
    if request.user.is_authenticated:
        gym = getattr(request, '_gym_cache', None)
        if gym is None:
            try:
                gym = request.user.profile.gym
            except (UserProfile.DoesNotExist, AttributeError):
                gym = Gym.objects.filter(owner=request.user).first()
            request._gym_cache = gym
        ctx['current_gym'] = gym
        if gym:
            ctx['currency'] = gym.currency_symbol
    return ctx
