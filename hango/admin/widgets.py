# hango/admin/widgets.py
from django import forms
from django.utils.safestring import mark_safe
from hango.core.weekdays import bools_from_mask, mask_from_bools, WEEKDAY_LABELS_PT

class WeekdayMaskWidget(forms.MultiWidget):
    """
    Widget para editar um bitmask de dias da semana como botões on/off (Seg..Dom).
    Usa template custom e CSS próprio via Media.
    """
    template_name = "admin/widgets/weekday_mask.html"

    def __init__(self, attrs=None):
        # 7 checkboxes "internos" — serão estilizados como botões
        widgets = [forms.CheckboxInput() for _ in range(7)]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value is None:
            value = 0
        return bools_from_mask(int(value))

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["weekday_labels"] = WEEKDAY_LABELS_PT
        return ctx

    class Media:
        css = {
            "all": ("hango/admin/weekday_mask.css",)  # <- coloque este arquivo em static/
        }
        # sem JS obrigatório

class WeekdayMaskField(forms.MultiValueField):
    """
    Campo que traduz os 7 toggles em um inteiro (bitmask).
    """
    def __init__(self, *args, **kwargs):
        fields = [forms.BooleanField(required=False) for _ in range(7)]
        super().__init__(fields=fields, require_all_fields=False, *args, **kwargs)
        self.widget = WeekdayMaskWidget()

    def compress(self, data_list):
        if data_list:
            return mask_from_bools(data_list)
        return 0
