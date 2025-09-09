from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme


@login_required
def post_login_redirect(request):
    """
    After a successful login, decide where to send the user:
      - If a safe ?next= is provided, honor it.
      - Else staff -> Kitchen; non-staff -> Menu.
    """
    # Honor ?next= if it's safe
    next_url = request.GET.get("next") or request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={*settings.ALLOWED_HOSTS, "localhost", "127.0.0.1"},
        require_https=False,
    ):
        return redirect(next_url)

    # Default routing by role
    if request.user.is_staff:
        return redirect("orders:kitchen")
    return redirect("menu:list")
