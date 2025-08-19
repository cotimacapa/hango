from django import forms
class CheckoutForm(forms.Form):
    pickup_slot=forms.DateTimeField(required=False,help_text='Optional pickup time')
    notes=forms.CharField(required=False,widget=forms.Textarea(attrs={'rows':3}))
