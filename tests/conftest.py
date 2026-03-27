def pytest_ignore_collect(collection_path, config):
    return "sync-conflict" in collection_path.name
