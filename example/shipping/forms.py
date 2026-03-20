"""Forms for the shipping example app."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django import forms
from sendparcel_django.registry import registry

from shipping.models import Shipment

if TYPE_CHECKING:
    ShipmentFormBase = forms.ModelForm[Shipment]
else:
    ShipmentFormBase = forms.ModelForm


class CreateShipmentForm(ShipmentFormBase):
    """Form for creating a new shipment with address and parcel details."""

    provider = forms.ChoiceField(
        label="Provider",
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
            "reference_id": "Reference ID",
            "sender_name": "Sender name",
            "sender_street": "Sender street",
            "sender_city": "Sender city",
            "sender_postal_code": "Sender postal code",
            "sender_country_code": "Sender country code",
            "receiver_name": "Receiver name",
            "receiver_street": "Receiver street",
            "receiver_city": "Receiver city",
            "receiver_postal_code": "Receiver postal code",
            "receiver_country_code": "Receiver country code",
            "weight": "Weight (kg)",
            "width": "Width (cm)",
            "height": "Height (cm)",
            "length": "Length (cm)",
        }
        widgets = {
            "reference_id": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. ORD-123",
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
                    "placeholder": "Jane Smith",
                }
            ),
            "receiver_street": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "10 Example Street",
                }
            ),
            "receiver_city": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Krakow",
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        provider_choices = kwargs.pop("provider_choices", None)
        super().__init__(*args, **kwargs)
        if provider_choices is None:
            provider_choices = registry.get_choices()
        provider_field = cast(forms.ChoiceField, self.fields["provider"])
        provider_field.choices = provider_choices
