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


class MessageEventResult:
    pass


class filter:
    @staticmethod
    def command(name):
        def decorator(func):
            func._command_name = name
            return func
        return decorator
