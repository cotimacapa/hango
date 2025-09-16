# apps/accounts/admin.py
from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, BlockEvent
from .forms import UserCreationForm, UserChangeForm
from hango.admin.widgets import WeekdayMaskField


class UserAdminForm(UserChangeForm):
    """
    Admin change form that:
      - Uses WeekdayMaskField for students (nice UI).
      - For staff, *replaces* the mask field with IntegerField(0) + HiddenInput
        so the field won't demand a list and block saves.
    """
    # Default field: for students we want the mask widget/field
    lunch_days_override_mask = WeekdayMaskField(
        label="Dias individuais de almoço",
        required=False,
        help_text="Usado somente quando a sobrescrita está ativada.",
    )

    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ensure override fields are never 'required' at the HTML/form layer
        for fname in ("lunch_days_override_enabled", "lunch_days_override_mask"):
            if fname in self.fields:
                self.fields[fname].required = False

        # For staff, *replace* field definitions to avoid "list required" validation
        instance = getattr(self, "instance", None)
        if instance and instance.is_staff:
            # Hide + force defaults: enabled=False, mask=0
            if "lunch_days_override_enabled" in self.fields:
                self.fields["lunch_days_override_enabled"] = forms.BooleanField(
                    required=False, initial=False, widget=forms.HiddenInput()
                )
                self.initial["lunch_days_override_enabled"] = False

            # CRUCIAL: replace the WeekdayMaskField with IntegerField
            self.fields["lunch_days_override_mask"] = forms.IntegerField(
                required=False, initial=0, widget=forms.HiddenInput()
            )
            self.initial["lunch_days_override_mask"] = 0


class BlockEventInline(admin.TabularInline):
    model = BlockEvent
    fk_name = "user"
    extra = 0
    can_delete = False
    readonly_fields = ("action", "source", "by_user", "reason", "created_at")
    fields = readonly_fields
    verbose_name = "Evento de bloqueio"
    verbose_name_plural = "Eventos de bloqueio"

    def has_add_permission(self, request, obj=None): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    form = UserAdminForm
    model = User

    # Force visibility of error lists on this page only
    class Media:
        css = {"all": ("admin/css/override.css",)}

    list_display = (
        "cpf", "first_name", "last_name",
        "is_staff", "is_active",
        "is_blocked", "no_show_streak",
        "human_lunch_days_override",
    )
    ordering = ("cpf",)
    search_fields = ("cpf", "first_name", "last_name", "email")
    list_filter = ("is_staff", "is_active", "is_blocked")

    inlines = [BlockEventInline]

    fieldsets = (
        (None, {"fields": ("cpf", "password")}),
        ("Informações pessoais", {"fields": ("first_name", "last_name", "email")}),
        ("Almoço", {"fields": ("lunch_days_override_enabled", "lunch_days_override_mask")}),
        ("Bloqueio", {
            "fields": (
                "is_blocked", "blocked_reason", "block_source", "blocked_at", "blocked_by",
                "no_show_streak", "last_no_show_at", "last_pickup_at",
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

    def get_readonly_fields(self, request, obj=None):
        ro = set(super().get_readonly_fields(request, obj) or ())
        ro.update({
            "block_source", "blocked_at", "blocked_by",
            "no_show_streak", "last_no_show_at", "last_pickup_at",
        })
        return tuple(sorted(ro))

    def save_model(self, request, obj, form, change):
        """
        If 'is_blocked' flips, use model helpers to create proper BlockEvent entries.
        """
        if change:
            try:
                old = type(obj).objects.get(pk=obj.pk)
            except type(obj).DoesNotExist:
                old = None

            if old and (old.is_blocked != obj.is_blocked):
                reason = form.cleaned_data.get("blocked_reason", "") if hasattr(form, "cleaned_data") else ""
                if obj.is_blocked and not old.is_blocked:
                    obj.block(source="manual", by=request.user, reason=reason)
                    return
                elif (not obj.is_blocked) and old.is_blocked:
                    obj.unblock(by=request.user, reason=reason)
                    return

        super().save_model(request, obj, form, change)

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

    actions = ("action_block", "action_unblock")

    # If form is invalid, emit a detailed error so it can't hide
    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        resp = super().render_change_form(request, context, add, change, form_url, obj)
        if request.method == "POST":
            adminform = context.get("adminform")
            if adminform and hasattr(adminform, "form"):
                form = adminform.form
                if not form.is_valid():
                    try:
                        print("ADMIN FORM ERRORS:", form.errors.as_json(), "NON_FIELD:", form.non_field_errors().as_text())
                    except Exception:
                        pass
                    non_field = form.non_field_errors()
                    if non_field:
                        messages.error(request, "Erro no formulário: " + "; ".join(non_field))
        return resp
