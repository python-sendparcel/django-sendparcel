#!/usr/bin/env python
"""Django management command entry point for the example project."""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
