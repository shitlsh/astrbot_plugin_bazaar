class Context:
    def get_config(self):
        return {}


class Star:
    def __init__(self, context):
        self.context = context

    async def initialize(self):
        pass

    async def terminate(self):
        pass


def register(name, author, desc, version):
    def decorator(cls):
        cls._plugin_name = name
        cls._plugin_author = author
        cls._plugin_desc = desc
        cls._plugin_version = version
        return cls
    return decorator
