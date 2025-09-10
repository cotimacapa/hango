from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

# ⬇️ Domain rule import: Mon–Fri default and pretty-printer
from hango.core.weekdays import MON_FRI_MASK, human_days as human_days_str


class StudentClass(models.Model):
    name = models.CharField(_("Name"), max_length=120, unique=True)

    # Weekday mask: Mon..Sun via bitmask (1,2,4,8,16,32,64)
    days_mask = models.PositiveSmallIntegerField(
        default=MON_FRI_MASK,
        help_text=_("Weekdays this class receives lunch (Mon–Sun). Applies to all students without an individual override.")
    )

    # Default rule: only non-staff users can be picked as members.
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Students"),
        related_name="student_classes",
        blank=True,
        # Change below to limit_choices_to={"groups__name": "Students"}, but create that group first
        limit_choices_to={"is_staff": False, "groups__name": "Aluno"},
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

    # Nice string for admin list_display / detail pages
    def human_days(self) -> str:
        return human_days_str(self.days_mask)
    human_days.short_description = _("Lunch days")
