# apps/classes/models.py
from django.db import models, transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# ⬇️ Domain rule import: Mon–Fri default and pretty-printer
from hango.core.weekdays import MON_FRI_MASK, human_days as human_days_str


class StudentClass(models.Model):
    # Human name for the class/cohort (kept unique as in your current schema)
    name = models.CharField("Nome", max_length=120, unique=True)

    # NEW: canonical academic year for this cohort (e.g., 2025)
    # Keep your existing academic_year for compatibility, but prefer 'year' going forward.
    year = models.PositiveIntegerField("Ano", null=True, blank=True, db_index=True)

    # Legacy/compat: existing field you already had
    academic_year = models.PositiveSmallIntegerField(
        "Ano acadêmico",
        null=True,
        blank=True,
        help_text=_("Ex.: 2025. Usado para relatórios e filtros."),
    )

    # Weekday mask: Mon..Sun via bitmask (1,2,4,8,16,32,64)
    days_mask = models.PositiveSmallIntegerField(
        default=MON_FRI_MASK,
        help_text=_(
            "Dias da semana em que a turma recebe almoço (Seg–Dom). "
            "Aplicado a todos os estudantes sem sobrescrita individual."
        ),
    )

    # Default rule: only non-staff users (group "Aluno") can be picked as members.
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name="Alunos",
        related_name="student_classes",
        blank=True,
        limit_choices_to={"is_staff": False, "groups__name": "Aluno"},
    )

    # NEW: link to previous-year class; gives you obj.next_year automatically
    prev_year = models.OneToOneField(
        "self",
        verbose_name=_("Turma do ano anterior"),
        related_name="next_year",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text=_("Turma correspondente do ano anterior."),
    )

    # Legacy/compat: you already had a successor pointer. We'll keep it, but
    # the canonical forward link used by admin will be next_year (above).
    successor = models.ForeignKey(
        "self",
        verbose_name="Turma do próximo ano (legacy)",
        related_name="predecessors",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text=_("Ponte legada para a turma do próximo ano/nível."),
    )

    # Archive toggle: keep historical classes without deleting
    is_active = models.BooleanField(
        "Ativa",
        default=True,
        help_text=_("Desmarque para arquivar esta turma (permanece visível em relatórios)."),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Turma"
        verbose_name_plural = "Turmas"
        ordering = ("name",)
        indexes = [
            models.Index(fields=("is_active",)),
            models.Index(fields=("academic_year",)),
            models.Index(fields=("year",)),
        ]

    def __str__(self) -> str:
        # Prefer 'year' if present; fall back to academic_year
        yr = self.year or self.academic_year
        return f"{self.name} ({yr})" if yr else self.name

    # --- Validation / integrity -------------------------------------------------
    def clean(self):
        super().clean()
        # prevent self-link
        if self.prev_year_id and self.prev_year_id == self.pk:
            raise ValidationError({"prev_year": _("A turma anterior não pode ser a própria turma.")})

        # if previous already has a different successor, block
        if self.prev_year and getattr(self.prev_year, "next_year_id", None):
            if self.prev_year.next_year_id != self.pk:
                raise ValidationError(
                    {"prev_year": _("A turma anterior já está vinculada a outra sucessora.")}
                )

    # --- Convenience / niceties ------------------------------------------------

    def member_count(self) -> int:
        return self.members.count()
    member_count.short_description = "Alunos"

    # Nice string for admin list_display / detail pages
    def human_days(self) -> str:
        return human_days_str(self.days_mask)
    human_days.short_description = "Dias de almoço"

    def spawn_successor(
        self,
        *,
        name: str | None = None,
        year: int | None = None,
        carry_members: bool = False,
    ) -> "StudentClass":
        """
        Create and return the 'next-year' class, copying configuration and (optionally)
        current members. Links as both next_year (preferred) and successor (legacy).
        """
        # compute the numeric year to assign
        new_year = (
            year if year is not None
            else ((self.year or self.academic_year) + 1 if (self.year or self.academic_year) else None)
        )
        with transaction.atomic():
            next_class = StudentClass.objects.create(
                name=name or f"{self.name} — próximo",
                days_mask=self.days_mask,
                year=new_year,
                academic_year=new_year if self.academic_year is not None else None,
                is_active=True,
            )
            if carry_members:
                next_class.members.set(self.members.all())

            # Wire both the modern and legacy forward links
            self.next_year = next_class
            self.successor = next_class
            self.save(update_fields=["successor"])  # next_year saved via reverse relation

        return next_class
