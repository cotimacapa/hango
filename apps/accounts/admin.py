# apps/accounts/admin.py
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User  # UPDATED
from .forms import UserCreationForm, UserChangeForm
from hango.admin.widgets import WeekdayMaskField

# NEW: import the audit inline model
from .models import BlockEvent  # NEW


class UserAdminForm(UserChangeForm):
    # Checkboxes Seg..Dom → bitmask
    lunch_days_override_mask = WeekdayMaskField(
        label="Dias individuais de almoço",
        required=False,
        help_text="Usado somente quando a sobrescrita está ativada."
    )

    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        # Para contas de staff, ocultar os campos de sobrescrita (não se aplicam)
        if instance and instance.is_staff:
            self.fields["lunch_days_override_enabled"].widget = forms.HiddenInput()
            self.fields["lunch_days_override_mask"].widget = forms.HiddenInput()


# NEW: Inline somente leitura para histórico de bloqueios/desbloqueios
class BlockEventInline(admin.TabularInline):
    model = BlockEvent
    fk_name = "user"  # <-- FIX: qual FK liga o inline ao usuário pai
    extra = 0
    can_delete = False
    readonly_fields = ("action", "source", "by_user", "reason", "created_at")
    verbose_name = "Evento de bloqueio"
    verbose_name_plural = "Eventos de bloqueio"
    fields = readonly_fields  # mantém a mesma ordem no inline

    # Torna o inline 100% somente leitura: sem adicionar/editar/excluir
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    form = UserAdminForm  # <-- usar o form com WeekdayMaskField
    model = User

    # UPDATED: mostrar status de bloqueio e streak na lista
    list_display = (
        "cpf", "first_name", "last_name",
        "is_staff", "is_active",
        "is_blocked",            # NEW
        "no_show_streak",        # NEW
        "human_lunch_days_override",
    )
    ordering = ("cpf",)
    search_fields = ("cpf", "first_name", "last_name", "email")
    list_filter = ("is_staff", "is_active", "is_blocked")  # NEW

    # NEW: histórico inline
    inlines = [BlockEventInline]

    # UPDATED: fieldsets com seção de bloqueio
    fieldsets = (
        (None, {"fields": ("cpf", "password")}),
        ("Informações pessoais", {"fields": ("first_name", "last_name", "email")}),
        ("Almoço", {"fields": ("lunch_days_override_enabled", "lunch_days_override_mask")}),
        ("Bloqueio", {  # NEW
            "fields": (
                "is_blocked",
                "blocked_reason",
                "block_source",
                "blocked_at",
                "blocked_by",
                "no_show_streak",
                "last_no_show_at",
                "last_pickup_at",
            )
        }),
        ("Permissões", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Datas importantes", {"fields": ("last_login",)}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "cpf", "first_name", "last_name", "email",
                "password1", "password2",
                "is_active", "is_staff", "is_superuser",
            ),
        }),
    )

    # NEW: tornar certos campos somente leitura sempre (fonte/quem/quando e métricas)
    def get_readonly_fields(self, request, obj=None):
        ro = set(super().get_readonly_fields(request, obj) or ())
        ro.update({
            "block_source",
            "blocked_at",
            "blocked_by",
            "no_show_streak",
            "last_no_show_at",
            "last_pickup_at",
        })
        return tuple(sorted(ro))

    # NEW: garantir que toggles de bloqueio passem pelos helpers (cria eventos)
    def save_model(self, request, obj, form, change):
        """
        Se o admin marcar/desmarcar 'is_blocked', usamos User.block()/unblock()
        para registrar evento e manter consistência. 'blocked_reason' é usado
        como motivo quando aplicável.
        """
        if change:
            # estado anterior
            try:
                old = type(obj).objects.get(pk=obj.pk)
            except type(obj).DoesNotExist:
                old = None

            # Se mudou o flag de bloqueio, delega aos helpers
            if old and (old.is_blocked != obj.is_blocked):
                reason = form.cleaned_data.get("blocked_reason", "") if hasattr(form, "cleaned_data") else ""
                if obj.is_blocked and not old.is_blocked:
                    # passou de desbloqueado -> bloqueado
                    obj.block(source="manual", by=request.user, reason=reason)
                    return  # já salvou dentro de block()
                elif (not obj.is_blocked) and old.is_blocked:
                    # passou de bloqueado -> desbloqueado (somente staff, mas estamos no admin)
                    obj.unblock(by=request.user, reason=reason)
                    return  # já salvou dentro de unblock()

        # caminho normal (sem alternância de bloqueio)
        super().save_model(request, obj, form, change)

    # NEW: ações em massa (rápidas). Para motivo customizado, poderíamos fazer action com FormView.
    @admin.action(description="Bloquear selecionados (manual)")
    def action_block(self, request, queryset):
        for u in queryset:
            if not u.is_blocked:
                u.block(source="manual", by=request.user, reason="Bloqueio em massa via admin")

    @admin.action(description="Desbloquear selecionados")
    def action_unblock(self, request, queryset):
        for u in queryset:
            if u.is_blocked:
                u.unblock(by=request.user, reason="Desbloqueio em massa via admin")

    actions = ("action_block", "action_unblock")  # NEW
