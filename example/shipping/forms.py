"""Forms for the shipping example app."""

from django import forms
from sendparcel_django.registry import registry

from shipping.models import Shipment


class CreateShipmentForm(forms.ModelForm):
    """Form for creating a new shipment with address and parcel details."""

    provider = forms.ChoiceField(
        label="Dostawca",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Shipment
        fields = [
            "reference_id",
            "sender_name",
            "sender_street",
            "sender_city",
            "sender_postal_code",
            "sender_country_code",
            "receiver_name",
            "receiver_street",
            "receiver_city",
            "receiver_postal_code",
            "receiver_country_code",
            "weight",
            "width",
            "height",
            "length",
        ]
        labels = {
            "reference_id": "Numer referencyjny",
            "sender_name": "Nadawca - Nazwa",
            "sender_street": "Nadawca - Ulica",
            "sender_city": "Nadawca - Miasto",
            "sender_postal_code": "Nadawca - Kod pocztowy",
            "sender_country_code": "Nadawca - Kraj",
            "receiver_name": "Odbiorca - Nazwa",
            "receiver_street": "Odbiorca - Ulica",
            "receiver_city": "Odbiorca - Miasto",
            "receiver_postal_code": "Odbiorca - Kod pocztowy",
            "receiver_country_code": "Odbiorca - Kraj",
            "weight": "Waga (kg)",
            "width": "Szerokość (cm)",
            "height": "Wysokość (cm)",
            "length": "Długość (cm)",
        }
        widgets = {
            "reference_id": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "np. ZAM-123",
                }
            ),
            "sender_name": forms.TextInput(attrs={"class": "form-control"}),
            "sender_street": forms.TextInput(attrs={"class": "form-control"}),
            "sender_city": forms.TextInput(attrs={"class": "form-control"}),
            "sender_postal_code": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "sender_country_code": forms.TextInput(
                attrs={"class": "form-control", "maxlength": "2"}
            ),
            "receiver_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Jan Kowalski",
                }
            ),
            "receiver_street": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "ul. Przykładowa 1/2",
                }
            ),
            "receiver_city": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Kraków",
                }
            ),
            "receiver_postal_code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "30-001",
                }
            ),
            "receiver_country_code": forms.TextInput(
                attrs={"class": "form-control", "maxlength": "2"}
            ),
            "weight": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01"}
            ),
            "width": forms.NumberInput(attrs={"class": "form-control"}),
            "height": forms.NumberInput(attrs={"class": "form-control"}),
            "length": forms.NumberInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        provider_choices = kwargs.pop("provider_choices", None)
        super().__init__(*args, **kwargs)
        if provider_choices is None:
            provider_choices = registry.get_choices()
        self.fields["provider"].choices = provider_choices
