from django import forms
from django.core.exceptions import ValidationError

class CheckoutForm(forms.Form):
    pickup_slot = forms.DateTimeField(required=False, help_text="Optional pickup time")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        # Pass request.user when constructing the form: CheckoutForm(..., user=request.user)
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        user = getattr(self, "user", None)

        # If no user was provided, don't hard-fail—view-level guards still apply.
        if user is None:
            return cleaned

        # Operators (staff or superuser) cannot place orders.
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            raise ValidationError("Operadores não podem realizar pedidos.")

        # Blocked users cannot place orders either.
        if getattr(user, "is_blocked", False):
            raise ValidationError("Seu usuário está bloqueado para fazer pedidos. Procure a equipe.")

        return cleaned
