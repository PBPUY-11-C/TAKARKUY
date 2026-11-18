from django.contrib.auth.decorators import login_required

from .plan_views import account_page
from .planner import build_plan


@login_required
def planner_page(request):
    """Halaman planner (wajib login): merender account_page dengan build_plan sebagai mesin rencana."""
    return account_page(request, build_plan)
