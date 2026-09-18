def _module():
    from src.api.services import settings
    return settings


def get_settings_view():
    return _module().get_settings_view()


def list_provider_models(provider: str, base_url: str, api_key: str | None = None):
    return _module().list_provider_models(provider, base_url, api_key)


def set_graph_extraction_mode(enabled: bool):
    return _module().set_graph_extraction_mode(enabled)


def set_llm_config(provider: str, model: str, base_url: str, api_key: str | None = None):
    return _module().set_llm_config(provider, model, base_url, api_key)
