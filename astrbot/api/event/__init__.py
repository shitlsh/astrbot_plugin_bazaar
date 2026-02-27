class AstrMessageEvent:
    def __init__(self, message_str="", sender_name="TestUser"):
        self.message_str = message_str
        self._sender_name = sender_name

    def get_sender_name(self):
        return self._sender_name

    def get_messages(self):
        return [{"type": "text", "text": self.message_str}]

    def plain_result(self, text):
        return text

    def image_result(self, url=None, path=None, bytes_data=None):
        return {"type": "image", "url": url, "path": path, "bytes": bytes_data}

    def chain_result(self, chain):
        return chain


class MessageEventResult:
    pass


class filter:
    @staticmethod
    def command(name):
        def decorator(func):
            func._command_name = name
            return func
        return decorator
