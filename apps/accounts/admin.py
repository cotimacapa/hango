# apps/accounts/admin.py
from __future__ import annotations

from django import forms
from django.apps import apps as django_apps
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db.models import Case, When, Value, IntegerField, Exists, OuterRef
from django.utils.html import format_html
from django.templatetags.static import static

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


# --- Custom widget: disable specific choices -----------------------------

class RoleSelect(forms.Select):
    def __init__(self, *args, disabled_values=None, **kwargs):
        self.disabled_values = set(disabled_values or [])
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value in self.disabled_values:
            option["attrs"]["disabled"] = True
            option["attrs"]["aria-disabled"] = "true"
            option["attrs"]["title"] = "Somente Admin pode atribuir este papel."
        return option


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

        # Non-superusers: show 'Admin' but disabled (cannot select)
        if self.request and not self.request.user.is_superuser:
            self.fields["role"].widget = RoleSelect(
                choices=self.fields["role"].choices, disabled_values=[ROLE_ADMIN]
            )

        # Remove block-related fields when target user is not a Student
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
        # Non-superusers: show 'Admin' but disabled
        if self.request and not self.request.user.is_superuser:
            self.fields["role"].widget = RoleSelect(
                choices=self.fields["role"].choices, disabled_values=[ROLE_ADMIN]
            )


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
        "display_role",           # Papel (Aluno/Equipe/Admin)
        "is_active",
        "display_blocked",        # icons + custom sort
        "no_show_streak",
        "human_lunch_days_override",
    )
    ordering = ("cpf",)
    search_fields = ("cpf", "first_name", "last_name", "email")
    list_filter = ("is_active", "is_blocked")

    # >>> Pagination & performance
    list_per_page = 50
    list_max_show_all = 200
    show_full_result_count = False
    # list_select_related = ()  # add FKs here if you surface them in list_display

    # Pretty columns
    @admin.display(description="Papel", ordering="is_staff")
    def display_role(self, obj: User) -> str:
        m = {ROLE_STUDENT: "Aluno", ROLE_STAFF: "Equipe", ROLE_ADMIN: "Admin"}
        return m.get(compute_role(obj), "—")

    @admin.display(description="Bloqueado para pedir", ordering="blocked_sort_key")
    def display_blocked(self, obj: User) -> str:
        role = compute_role(obj)
        if role != ROLE_STUDENT:
            # Solid white dot
            return format_html(
                '<span title="N/A" aria-label="N/A" '
                'style="display:inline-block;width:13px;height:13px;border-radius:50%;'
                'background:#fff;border:1px solid rgba(0,0,0,.25);vertical-align:middle;"></span>'
            )
        if getattr(obj, "is_blocked", False):
            return format_html(
                '<img src="{}" alt="Sim" class="icon-yes" />',
                static("admin/img/icon-yes.svg"),
            )
        return format_html(
            '<img src="{}" alt="Não" class="icon-no" />',
            static("admin/img/icon-no.svg"),
        )

    # Base fieldsets (no Bloqueio here; added conditionally)
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

    # Dynamic fieldsets
# apps/accounts/admin.py

    def get_fieldsets(self, request, obj=None):
        # On the ADD view, render the creation fieldsets so password1/password2 appear
        if obj is None:
            return self.add_fieldsets

        # ----- existing change-view logic stays the same below -----
        show_advanced = request.user.is_superuser and request.GET.get("show_advanced") == "1"

        # Effective role of the TARGET user (being viewed/edited)
        eff_role = compute_role(obj)

        # If a NON-superuser is viewing an Admin user, show read-only label instead of the form field
        if obj.is_superuser and not request.user.is_superuser:
            papel_fields = ("display_role",)
        else:
            papel_fields = ("role",)

        fieldsets = [
            (None, {"fields": ("cpf", "password")}),
            ("Informações pessoais", {"fields": ("first_name", "last_name", "email")}),
            ("Papel", {"fields": papel_fields}),
            ("Almoço", {"fields": ("lunch_days_override_enabled", "lunch_days_override_mask")}),
        ]

        if eff_role == ROLE_STUDENT:
            fieldsets.append(("Senha", {"fields": ("must_change_password",)}))
            fieldsets.append(("Bloqueio", {"fields": BLOCK_FIELDS}))

        if show_advanced:
            fieldsets.append(("Permissões (avançado)", {
                "fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")
            }))

        return tuple(fieldsets)

    # Inlines only for Students
    def get_inlines(self, request, obj):
        if obj and compute_role(obj) == ROLE_STUDENT:
            return [BlockEventInline]
        return []

    def get_readonly_fields(self, request, obj=None):
        ro = set(super().get_readonly_fields(request, obj) or ())
        ro.update({"block_source", "blocked_at", "blocked_by", "no_show_streak", "last_no_show_at", "last_pickup_at"})
        if not request.user.is_superuser:
            ro.update({"is_superuser"})
            # When staff views an Admin, the Papel field is a computed label
            if obj and getattr(obj, "is_superuser", False):
                ro.add("display_role")
        return tuple(sorted(ro))

    def get_queryset(self, request):
        """
        Annotate a custom sort key so 'Bloqueado para pedir' orders as:
        N/A (0) < Não (1) < Sim (2).
        N/A covers: superusers, is_staff, users in Staff/Equipe group, or users
        granted operator perms directly.
        """
        qs = super().get_queryset(request)

        # user in Staff/Equipe group?
        staff_group_exists = Exists(
            Group.objects.filter(name__in=["Staff", "Equipe"], user__pk=OuterRef("pk"))
        )
        # user has any operator permission directly?
        direct_op_perm_exists = Exists(
            User.objects.filter(pk=OuterRef("pk"), user_permissions__codename__in=OP_PERMS)
        )

        qs = qs.annotate(
            blocked_sort_key=Case(
                When(is_superuser=True, then=Value(0)),
                When(is_staff=True, then=Value(0)),
                When(staff_group_exists, then=Value(0)),
                When(direct_op_perm_exists, then=Value(0)),
                When(is_blocked=True, then=Value(2)),   # Student & blocked
                default=Value(1),                       # Student & not blocked
                output_field=IntegerField(),
            )
        )

        # NOTE: we no longer exclude superusers here — staff can see Admins,
        # but they won't be able to edit/delete them (see permissions below).
        return qs

    # ---- Permissions: staff can VIEW admin users, but cannot CHANGE/DELETE --

    def _obj_is_admin(self, obj):
        return bool(obj and getattr(obj, "is_superuser", False))

    def has_view_permission(self, request, obj=None):
        # Allow viewing anything the user normally can; do not block Admin objects.
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if not request.user.is_superuser and self._obj_is_admin(obj):
            # Read-only view for staff when opening an Admin user
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if not request.user.is_superuser and self._obj_is_admin(obj):
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        """
        Map 'role' to flags/groups with server-side enforcement.
        Also prevents staff from modifying Admin users.
        Additionally: on ADD of a Student, default must_change_password=True.
        """
        if change and not request.user.is_superuser:
            old = type(obj).objects.filter(pk=obj.pk).only("is_superuser").first()
            if old and old.is_superuser:
                raise PermissionDenied("Apenas Admin pode editar um usuário Admin.")

        role = form.cleaned_data.get("role") or compute_role(obj)
        staff_group = get_staff_group()

        # Admin
        if role == ROLE_ADMIN:
            if not request.user.is_superuser:
                form.add_error("role", "Somente Admin pode atribuir o papel 'Admin'.")
                return
            obj.is_superuser = True
            obj.is_staff = True
            obj.save()
            return

        # Staff
        if role == ROLE_STAFF:
            obj.is_superuser = False
            obj.is_staff = True
            obj.save()
            obj.groups.add(staff_group)
            return

        # Student
        obj.is_superuser = False
        obj.is_staff = False
        # On first creation of a Student, force password change by default
        if not change and not obj.must_change_password:
            obj.must_change_password = True
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


# --- Groups: visible to Equipe, editable only by Admin -------------------

try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass

@admin.register(Group)
class GroupAdmin(DjangoGroupAdmin):
    # Equipe (is_staff) and Admin can open the list and detail pages
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.is_staff

    # Only Admin can add/change/delete groups
    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    # No bulk actions for Equipe (prevents any mass ops)
    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            return {}
        return actions
