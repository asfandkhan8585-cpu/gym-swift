"""Subscription gate: blocks a gym's access once its subscription lapses.
The software provider manages each gym's subscription via Django admin (/admin/)."""
from django.shortcuts import redirect
from django.urls import reverse


EXEMPT_PREFIXES = ('/admin', '/static', '/media')
EXEMPT_NAMES = {'login', 'logout', 'register', 'subscription_expired'}


class SubscriptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        path = request.path

        if (user is None or not user.is_authenticated or user.is_superuser
                or any(path.startswith(p) for p in EXEMPT_PREFIXES)):
            return self.get_response(request)

        try:
            match = request.resolver_match
            if match and match.url_name in EXEMPT_NAMES:
                return self.get_response(request)
        except Exception:
            pass

        # Resolve the user's gym and check subscription
        try:
            from .models import Gym, UserProfile
            gym = None
            try:
                profile = UserProfile.objects.select_related('gym').get(user=user)
                gym = profile.gym
            except UserProfile.DoesNotExist:
                gym = Gym.objects.filter(owner=user).first()
            if gym is not None:
                request._gym_cache = gym  # reuse downstream (views, context processor)
                if not gym.subscription_active and path != reverse('subscription_expired'):
                    return redirect('subscription_expired')
        except Exception:
            # never hard-fail a request because of the gate
            pass

        return self.get_response(request)
