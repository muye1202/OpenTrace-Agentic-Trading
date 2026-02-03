import os


def test_glm_flash_serial_class_importable():
    # Keep this test resilient in minimal environments.
    try:
        import langchain_openai  # noqa: F401
    except Exception:
        return

    from tradingagents.graph.trading_graph import GLMFlashSerialChatOpenAI

    os.environ.setdefault("ZHIPUAI_API_KEY", "test")
    llm = GLMFlashSerialChatOpenAI(model="glm-4.7-flash", base_url="https://open.bigmodel.cn/api/paas/v4")
    llm._ta_llm_concurrency_key = "llm:glm:https://open.bigmodel.cn/api/paas/v4:glm-4.7-flash"

