from __future__ import annotations

from contextlib import contextmanager

from langchain_openrouter import ChatOpenRouter as BaseChatOpenRouter

from argus.llm.openrouter_retention import (
    check_retention_response,
    enforce_openrouter_retention,
    raise_for_retention_error,
)


@contextmanager
def _retention_errors(model: str):
    try:
        yield
    except Exception as exc:
        response = getattr(exc, "raw_response", None)
        if response is not None:
            check_retention_response(response, model)
        raise_for_retention_error(model, getattr(exc, "status_code", None), getattr(exc, "body", None))
        raise


class ChatOpenRouter(BaseChatOpenRouter):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        with _retention_errors(self.model_name):
            return super()._generate(messages, stop, run_manager, **enforce_openrouter_retention(kwargs))

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        with _retention_errors(self.model_name):
            return await super()._agenerate(messages, stop, run_manager, **enforce_openrouter_retention(kwargs))

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        with _retention_errors(self.model_name):
            yield from super()._stream(messages, stop, run_manager, **enforce_openrouter_retention(kwargs))

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        with _retention_errors(self.model_name):
            async for chunk in super()._astream(messages, stop, run_manager, **enforce_openrouter_retention(kwargs)):
                yield chunk

    def _create_chat_result(self, response):
        data = response if isinstance(response, dict) else response.model_dump()
        raise_for_retention_error(self.model_name, None, data)
        return super()._create_chat_result(response)
