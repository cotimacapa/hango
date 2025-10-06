from django.contrib import admin
from .models import DiaSemAtendimento
from django import forms
from datetime import time

from django.urls import reverse
from django.shortcuts import redirect

from .models import OrderCutoffSetting

@admin.register(DiaSemAtendimento)
class DiaSemAtendimentoAdmin(admin.ModelAdmin):
    list_display = ("data", "rotulo", "repete_anualmente")
    date_hierarchy = "data"
    search_fields = ("rotulo",)
    list_filter = ("repete_anualmente",)
    ordering = ("data",)

    def get_readonly_fields(self, request, obj=None):
        # Staff can view-only; Admin (superuser) can edit
        if request.user.is_superuser:
            return ()
        return tuple(f.name for f in self.model._meta.fields)

    def has_view_permission(self, request, obj=None):
        # Equipe (is_staff) and Admin can open and view
        return request.user.is_superuser or request.user.is_staff

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_actions(self, request):
        # No bulk actions for staff
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            return {}
        return actions

def _half_hour_choices():
    # 00:00 → 23:30
    out = []
    for h in range(0, 24):
        for m in (0, 30):
            out.append((time(h, m), f"{h:02d}:{m:02d}"))
    return out

class OrderCutoffForm(forms.ModelForm):
    cutoff_time = forms.TypedChoiceField(
        label="Horário limite",
        coerce=lambda s: time.fromisoformat(s),
        choices=[(f"{h:02d}:{m:02d}", f"{h:02d}:{m:02d}") for h in range(24) for m in (0, 30)],
        required=False,
        help_text="Ex.: 15:00. Se vazio, usa 15:00 por padrão."
    )

    class Meta:
        model = OrderCutoffSetting
        fields = ["cutoff_time"]

    def initial_from_instance(self):
        if self.instance and self.instance.cutoff_time:
            self.initial["cutoff_time"] = self.instance.cutoff_time.strftime("%H:%M")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial_from_instance()

@admin.register(OrderCutoffSetting)
class OrderCutoffAdmin(admin.ModelAdmin):
    form = OrderCutoffForm

    def has_add_permission(self, request):
        # Enforce singleton: allow add only if none exists
        return not OrderCutoffSetting.objects.exists()

    def changelist_view(self, request, extra_context=None):
        obj = OrderCutoffSetting.objects.first()
        if obj:
            url = reverse(
                f"admin:{OrderCutoffSetting._meta.app_label}_{OrderCutoffSetting._meta.model_name}_change",
                args=[obj.pk],
            )
            return redirect(url)
        return super().changelist_view(request, extra_context)