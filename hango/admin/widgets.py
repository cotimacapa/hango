# hango/admin/widgets.py
from django import forms
from hango.core.weekdays import bools_from_mask, mask_from_bools, WEEKDAY_LABELS_PT


class WeekdayMaskWidget(forms.MultiWidget):
    """
    Widget para editar um bitmask de dias da semana.
    Renderiza 7 checkboxes (Seg..Dom) com os rótulos apropriados.
    """
    def __init__(self, attrs=None):
        widgets = [forms.CheckboxInput() for _ in range(7)]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value is None:
            value = 0
        return bools_from_mask(int(value))

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        # Adiciona labels para que o template saiba exibir "Seg..Dom"
        ctx["widget"]["weekday_labels"] = WEEKDAY_LABELS_PT
        return ctx

    def format_output(self, rendered_widgets):
        # Django >= 1.11 não usa mais; mantido por compatibilidade
        return super().format_output(rendered_widgets)


class WeekdayMaskField(forms.MultiValueField):
    """
    Campo que traduz os 7 checkboxes em um único inteiro (bitmask).
    """
    def __init__(self, *args, **kwargs):
        fields = [forms.BooleanField(required=False, label=WEEKDAY_LABELS_PT[i]) for i in range(7)]
        super().__init__(fields=fields, require_all_fields=False, *args, **kwargs)
        self.widget = WeekdayMaskWidget()

    def compress(self, data_list):
        if data_list:
            return mask_from_bools(data_list)
        return 0
