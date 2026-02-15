"""Form hooks for django-sendparcel."""

from __future__ import annotations

from django import forms

from sendparcel_django.registry import registry


class ProviderChoiceForm(forms.Form):
    """Simple provider selector form backed by plugin registry."""

    provider = forms.ChoiceField(choices=[])

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["provider"].choices = registry.get_choices()
