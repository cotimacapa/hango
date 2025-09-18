# apps/accounts/views.py
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse, reverse_lazy, NoReverseMatch


class ForcePasswordChangeView(PasswordChangeView):
    """
    Password change page used when must_change_password is set.
    On success: clear the flag and show a site-styled success flash.
    """
    template_name = "registration/password_change_form.html"
    success_url = reverse_lazy("post_login_redirect")

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        if getattr(user, "must_change_password", False):
            user.must_change_password = False
            user.save(update_fields=["must_change_password"])
        messages.success(self.request, "Senha atualizada com sucesso.")
        return response


@login_required
def post_login_redirect(request):
    """
    After a successful login, decide where to send the user:

      - If the user MUST change password, force redirect to the password change page
        (ignores ?next=).
      - Otherwise, if a safe ?next= is provided, honor it.
      - Else staff -> Kitchen; non-staff -> Menu.
    """
    # 1) Enforce password change flow (no email needed)
    if getattr(request.user, "must_change_password", False):
        # Try common URL names; fall back to a sensible path if not wired yet.
        target = None
        for name in ("accounts:password_change", "password_change"):
            try:
                target = reverse(name)
                break
            except NoReverseMatch:
                continue
        if not target:
            target = "/accounts/password-change/"
        return redirect(target)

    # 2) Honor ?next= if it's safe
    next_url = request.GET.get("next") or request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={*settings.ALLOWED_HOSTS, "localhost", "127.0.0.1"},
        require_https=False,
    ):
        return redirect(next_url)

    # 3) Default routing by role
    if request.user.is_staff:
        return redirect("orders:kitchen")
    return redirect("menu:list")
