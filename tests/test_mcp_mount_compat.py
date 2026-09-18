from unittest.mock import patch


def test_web_still_starts_when_http_mcp_adapter_is_incompatible():
    from src.api.app import create_app

    with patch(
        "fastapi_mcp.FastApiMCP",
        side_effect=TypeError("Server.__init__() takes 2 positional arguments but 3 were given"),
    ):
        app = create_app()

    assert app.state.mcp is None
    assert "takes 2 positional arguments" in app.state.mcp_error
