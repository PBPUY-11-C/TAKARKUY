from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.cache import patch_cache_control

from apps.recipe.views import api

from .maps import MapLimited, lookup_places, read_places
from .services import dashboard_data


@login_required
def dashboard_page(request):
    response = render(
        request,
        "home/home.html",
        {
            **dashboard_data(request.user),
            "map_places": read_places(),
            "map_config": {"tiles": settings.MAP_TILE_URL, "online": settings.MAP_LOOKUP_ENABLED},
        },
    )
    patch_cache_control(response, private=True, no_store=True)
    response["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@api
def market_lookup(request, data):
    try:
        return JsonResponse(lookup_places(request.user, data))
    except MapLimited as exc:
        response = JsonResponse({"error": str(exc)}, status=429)
        response["Retry-After"] = str(exc.retry_after)
        return response
