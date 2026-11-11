"""The semantic index borrows the business pool and never closes it."""

from unittest.mock import Mock

import pytest
from argus.api.personalization_memory_index import import_mem0_memory

from tests.memory.test_mem0_configuration import _config


@pytest.mark.parametrize("construction_fails", [False, True])
def test_vector_adapter_cleanup_keeps_the_shared_pool_open(monkeypatch, construction_fails):
    memory_class = import_mem0_memory()
    from mem0.memory.main import LlmFactory, VectorStoreFactory

    pool = Mock()
    adapters = []
    create_vector_store = VectorStoreFactory.create

    def capture_vector_store(*args, **kwargs):
        adapter = create_vector_store(*args, **kwargs)
        adapters.append(adapter)
        return adapter

    monkeypatch.setattr(VectorStoreFactory, "create", capture_vector_store)
    if construction_fails:
        monkeypatch.setattr(LlmFactory, "create", Mock(side_effect=RuntimeError("setup failed")))
        with pytest.raises(RuntimeError, match="setup failed"):
            memory_class.from_config(_config(pool))
    else:
        memory = memory_class.from_config(_config(pool))
        assert memory.vector_store is adapters[0]
    assert len(adapters) == 1
    adapter = adapters[0]
    adapter.__del__()
    adapter.__del__()
    pool.close.assert_not_called()
    pool.connection.return_value = sentinel = object()
    assert adapter.connection_pool.connection(timeout=0.5) is sentinel
    pool.connection.assert_called_once_with(timeout=0.5)
