from django.contrib.auth.decorators import login_required

from .plan_views import account_page
from .planner import build_plan


@login_required
def planner_page(request):
    return account_page(request, build_plan)
