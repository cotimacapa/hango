from django.contrib import admin
from .models import DiaSemAtendimento

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
