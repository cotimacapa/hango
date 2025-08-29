from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class StudentClass(models.Model):
    name = models.CharField(_("Name"), max_length=120, unique=True)

    # Default rule: only non-staff users can be picked as members.
    members = models.ManyToManyField(settings.AUTH_USER_MODEL,
        verbose_name=_("Students"),
        related_name="student_classes",
        blank=True,
        # Change below to limit_choices_to={"groups__name": "Students"}, but create that group first
        limit_choices_to={"is_staff": False}, 
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Class")
        verbose_name_plural = _("Classes")
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def member_count(self) -> int:
        return self.members.count()
    member_count.short_description = _("Students")
