# apps/accounts/admin.py
from __future__ import annotations

from django import forms
from django.apps import apps as django_apps
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from .models import User, BlockEvent
from .forms import UserCreationForm, UserChangeForm
from hango.admin.widgets import WeekdayMaskField

# --- Roles ---------------------------------------------------------------

ROLE_STUDENT = "student"   # Aluno
ROLE_STAFF   = "staff"     # Equipe (operador)
ROLE_ADMIN   = "admin"     # Superuser

ROLE_CHOICES = (
    (ROLE_STUDENT, "Aluno"),
    (ROLE_STAFF,   "Equipe"),
    (ROLE_ADMIN,   "Admin"),
)

OP_PERMS = (
    "orders.can_view_kitchen",
    "orders.can_manage_delivery",
    "orders.can_view_orders",
)

BLOCK_FIELDS = (
    "is_blocked", "blocked_reason", "block_source", "blocked_at", "blocked_by",
    "no_show_streak", "last_no_show_at", "last_pickup_at",
)

# --- Helpers -------------------------------------------------------------

def get_staff_group() -> Group:
    name_candidates = ["Staff", "Equipe"]
    g = None
    for nm in name_candidates:
        g = Group.objects.filter(name=nm).first()
        if g:
            break
    if not g:
        g = Group.objects.create(name="Staff")

    try:
        Order = django_apps.get_model("orders", "Order")
        ct = ContentType.objects.get_for_model(Order)
        perms = Permission.objects.filter(content_type=ct, codename__in=OP_PERMS)
        if perms.count():
            g.permissions.add(*perms)
    except Exception:
        pass
    return g


def compute_role(u: User) -> str:
    if getattr(u, "is_superuser", False):
        return ROLE_ADMIN
    has_ops = any(u.has_perm(p) for p in OP_PERMS)
    in_staff_group = u.groups.filter(name__in=["Staff", "Equipe"]).exists()
    if has_ops or in_staff_group or getattr(u, "is_staff", False):
        return ROLE_STAFF
    return ROLE_STUDENT


# --- Inline: audit -------------------------------------------------------

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


# --- Admin forms ---------------------------------------------------------

class UserAdminForm(UserChangeForm):
    """
    Change form with 'role' selector.
    Shows Bloqueio fields only for Aluno (role == student). For other roles,
    those fields are REMOVED from the form (cannot be posted/changed).
    """
    role = forms.ChoiceField(choices=ROLE_CHOICES, label="Papel", required=True)

    lunch_days_override_mask = WeekdayMaskField(
        label="Dias individuais de almoço",
        required=False,
        help_text="Usado somente quando a sobrescrita está ativada.",
    )

    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("_request", None)
        super().__init__(*args, **kwargs)

        # Never require lunch override fields at the form layer
        for fname in ("lunch_days_override_enabled", "lunch_days_override_mask"):
            if fname in self.fields:
                self.fields[fname].required = False

        # Effective role
        if self.instance and self.instance.pk:
            eff_role = compute_role(self.instance)
        else:
            eff_role = ROLE_STUDENT
        self.initial["role"] = eff_role

        # Hide/lock raw auth knobs unless explicitly requested by superuser
        show_advanced = bool(self.request and self.request.user.is_superuser and
                             self.request.GET.get("show_advanced") == "1")
        if not show_advanced:
            for fname in ("is_staff", "is_superuser", "groups", "user_permissions"):
                if fname in self.fields:
                    self.fields.pop(fname)

        # Staff UX: replace mask with hidden integer 0 so no “list required”
        instance = getattr(self, "instance", None)
        if instance and instance.is_staff:
            self.fields["lunch_days_override_enabled"] = forms.BooleanField(
                required=False, initial=False, widget=forms.HiddenInput()
            )
            self.initial["lunch_days_override_enabled"] = False
            self.fields["lunch_days_override_mask"] = forms.IntegerField(
                required=False, initial=0, widget=forms.HiddenInput()
            )
            self.initial["lunch_days_override_mask"] = 0

        # If editor is not superuser, drop 'Admin' from choices
        if self.request and not self.request.user.is_superuser:
            self.fields["role"].choices = [c for c in ROLE_CHOICES if c[0] != ROLE_ADMIN]

        # CRUCIAL: remove block-related fields when target user is not a Student
        if eff_role != ROLE_STUDENT:
            for f in BLOCK_FIELDS:
                self.fields.pop(f, None)

    def clean(self):
        cleaned = super().clean()
        # Students: if override enabled, require non-zero mask
        if not cleaned.get("is_staff") and cleaned.get("lunch_days_override_enabled"):
            mask = int(cleaned.get("lunch_days_override_mask") or 0)
            if mask <= 0:
                self.add_error("lunch_days_override_mask", "Selecione ao menos um dia da semana.")
        # Guard: non-superusers cannot set Admin
        if self.request and not self.request.user.is_superuser:
            if cleaned.get("role") == ROLE_ADMIN:
                self.add_error("role", "Somente Admin pode atribuir o papel 'Admin'.")
        return cleaned


class UserAdminAddForm(UserCreationForm):
    """Add form that includes the non-model 'role' field."""
    role = forms.ChoiceField(choices=ROLE_CHOICES, label="Papel", required=True)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("_request", None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            self.fields["role"].choices = [c for c in ROLE_CHOICES if c[0] != ROLE_ADMIN]


# --- User Admin -----------------------------------------------------------

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserAdminAddForm
    form = UserAdminForm
    model = User

    class Media:
        css = {"all": ("admin/css/override.css",)}  # keep error lists visible

    list_display = (
        "cpf", "first_name", "last_name",
        "is_staff", "is_active",
        "is_blocked", "no_show_streak",
        "human_lunch_days_override",
    )
    ordering = ("cpf",)
    search_fields = ("cpf", "first_name", "last_name", "email")
    list_filter = ("is_staff", "is_active", "is_blocked")

    # Base fieldsets (no Bloqueio here; we add it conditionally below)
    base_fieldsets = (
        (None, {"fields": ("cpf", "password")}),
        ("Informações pessoais", {"fields": ("first_name", "last_name", "email")}),
        ("Papel", {"fields": ("role",)}),
        ("Almoço", {"fields": ("lunch_days_override_enabled", "lunch_days_override_mask")}),
    )
    block_fieldset = ("Bloqueio", {"fields": BLOCK_FIELDS})
    advanced_fieldset = ("Permissões (avançado)", {
        "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")
    })

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "cpf", "first_name", "last_name", "email",
                "password1", "password2",
                "role",
                "is_active",
            ),
        }),
    )

    # Inject request into forms
    def get_form(self, request, obj=None, **kwargs):
        form_class = super().get_form(request, obj, **kwargs)
        class BoundForm(form_class):
            def __init__(self_inner, *a, **kw):
                kw["_request"] = request
                super().__init__(*a, **kw)
        return BoundForm

    # Show fieldsets dynamically:
    # - Bloqueio only for Students
    # - Advanced only for superusers with ?show_advanced=1
    def get_fieldsets(self, request, obj=None):
        show_advanced = request.user.is_superuser and request.GET.get("show_advanced") == "1"
        fieldsets = list(self.base_fieldsets)

        # Compute effective role: from object if editing, else from POST (or default)
        if obj:
            eff_role = compute_role(obj)
        else:
            eff_role = request.POST.get("role") or request.GET.get("role") or ROLE_STUDENT
            if eff_role not in {ROLE_STUDENT, ROLE_STAFF, ROLE_ADMIN}:
                eff_role = ROLE_STUDENT

        if eff_role == ROLE_STUDENT:
            fieldsets.append(self.block_fieldset)

        if show_advanced:
            fieldsets.append(self.advanced_fieldset)

        return tuple(fieldsets)

    # Show BlockEvent inline only for Students
    def get_inlines(self, request, obj):
        if obj and compute_role(obj) == ROLE_STUDENT:
            return [BlockEventInline]
        return []

    def get_readonly_fields(self, request, obj=None):
        ro = set(super().get_readonly_fields(request, obj) or ())
        ro.update({"block_source", "blocked_at", "blocked_by", "no_show_streak", "last_no_show_at", "last_pickup_at"})
        if not request.user.is_superuser:
            ro.update({"is_superuser"})
        return tuple(sorted(ro))

    def save_model(self, request, obj, form, change):
        """
        Map 'role' to flags/groups with server-side enforcement.
        """
        role = form.cleaned_data.get("role") or compute_role(obj)
        staff_group = get_staff_group()

        if role == ROLE_ADMIN:
            if not request.user.is_superuser:
                form.add_error("role", "Somente Admin pode atribuir o papel 'Admin'.")
                return
            obj.is_superuser = True
            obj.is_staff = True
            obj.save()
            return

        if role == ROLE_STAFF:
            obj.is_superuser = False
            obj.is_staff = True
            obj.save()
            obj.groups.add(staff_group)
            return

        # ROLE_STUDENT
        obj.is_superuser = False
        obj.is_staff = False
        obj.save()
        obj.groups.remove(staff_group)

    # Loud logging if something goes sideways
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


# --- Lock down Group admin to superusers only ----------------------------

try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass

@admin.register(Group)
class GroupAdmin(DjangoGroupAdmin):
    def has_view_permission(self, request, obj=None):   return request.user.is_superuser
    def has_add_permission(self, request):               return request.user.is_superuser
    def has_change_permission(self, request, obj=None):  return request.user.is_superuser
    def has_delete_permission(self, request, obj=None):  return request.user.is_superuser
