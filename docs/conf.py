"""Sphinx configuration for django-sendparcel."""

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "django.contrib.admin",
            "sendparcel_django",
        ],
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            },
        },
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    )
    django.setup()

project = "django-sendparcel"
copyright = "2026, Dominik Kozaczko"
author = "Dominik Kozaczko"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "plans"]

html_theme = "furo"
html_static_path = ["_static"]

autodoc_member_order = "bysource"
autodoc_typehints = "description"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "django": (
        "https://docs.djangoproject.com/en/5.2/",
        "https://docs.djangoproject.com/en/5.2/_objects/",
    ),
}

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
