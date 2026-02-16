"""Forms for the shipping example app."""

from django import forms

from shipping.models import Order


class OrderForm(forms.ModelForm):
    """Form for creating a new order."""

    class Meta:
        model = Order
        fields = [
            "description",
            "package_size",
            "recipient_name",
            "recipient_email",
            "recipient_phone",
            "recipient_line1",
            "recipient_city",
            "recipient_postal_code",
        ]
        widgets = {
            "description": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "np. Elektronika, Książki",
                }
            ),
            "package_size": forms.Select(attrs={"class": "form-select"}),
            "recipient_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Jan Kowalski",
                }
            ),
            "recipient_email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "jan@example.com",
                }
            ),
            "recipient_phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "+48 123 456 789",
                }
            ),
            "recipient_line1": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "ul. Przykładowa 10/2",
                }
            ),
            "recipient_city": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Kraków",
                }
            ),
            "recipient_postal_code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "30-001",
                }
            ),
        }


class CreateShipmentForm(forms.Form):
    """Form for creating a shipment from an order."""

    provider = forms.ChoiceField(
        label="Dostawca",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        provider_choices = kwargs.pop("provider_choices", [])
        super().__init__(*args, **kwargs)
        self.fields["provider"].choices = provider_choices
