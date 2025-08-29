import re
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

class CPFOrUsernameBackend(ModelBackend):
    """
    Authenticate with:
      - CPF (digits only, via Profile.cpf)
      - or username (for staff/fallback)
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        user = None
        digits = re.sub(r'\D', '', username)

        try:
            if len(digits) == 11:
                # try CPF via related Profile
                user = User.objects.select_related("profile").get(profile__cpf=digits)
            else:
                # try username as usual
                user = User.objects.get(Q(username=username))
        except User.DoesNotExist:
            return None

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
