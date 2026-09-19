from src.agent.model_trace import ModelTraceCallbacks


def test_model_trace_callback_is_langchain_compatible():
    """Tracing must not break LangChain's callback error dispatch."""
    errors = []
    callback = ModelTraceCallbacks(on_error=errors.append)

    # LangChain's callback manager reads this standard handler property. A
    # plain callback object raised AttributeError here during /agent requests.
    assert callback.raise_error is False
    callback.on_chat_model_start(
        {}, [[{"role": "user", "content": "hello"}]], run_id="model-1"
    )
    callback.on_llm_error(RuntimeError("provider unavailable"), run_id="model-1")

    assert errors[0]["llm_call_id"] == "model-1"
    assert errors[0]["error"] == "provider unavailable"
