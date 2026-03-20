"""Form hooks for django-sendparcel."""

from __future__ import annotations

from typing import Any, cast

from django import forms

from sendparcel_django.registry import registry


class ProviderChoiceForm(forms.Form):
    """Simple provider selector form backed by plugin registry."""

    provider = forms.ChoiceField(choices=[])

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        provider_field = cast(forms.ChoiceField, self.fields["provider"])
        provider_field.choices = registry.get_choices()
