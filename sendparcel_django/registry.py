"""Django-specific registry wrapper."""

from sendparcel.registry import PluginRegistry


class DjangoPluginRegistry(PluginRegistry):
    """Plugin registry with Django helper methods."""

    def get_callback_paths(self) -> list[str]:
        return [f"callback/{slug}/" for slug, _ in self.get_choices()]


registry = DjangoPluginRegistry()
