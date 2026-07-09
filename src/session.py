class ChatSession:
    """管理对话上下文，支持滑动窗口截断"""

    def __init__(self, max_rounds=5):
        self.max_rounds = max_rounds
        self.history = []

    @staticmethod
    def _clean_surrogates(text):
        return text.encode("utf-8", errors="replace").decode("utf-8")

    def add_message(self, role, content, **kwargs):
        msg = {"role": role, "content": self._clean_surrogates(content)}
        msg.update(kwargs)
        self.history.append(msg)
        self._trim()

    def add_tool_call_message(self, tool_calls):
        self.history.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls
        })
        self._trim()

    def add_tool_result(self, tool_call_id, result):
        self.history.append({
            "role": "tool",
            "content": self._clean_surrogates(str(result)),
            "tool_call_id": tool_call_id
        })
        self._trim()

    def get_messages(self, system_prompt):
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.history)
        return messages

    def _trim(self):
        max_messages = self.max_rounds * 2
        if len(self.history) > max_messages:
            excess = len(self.history) - max_messages
            del self.history[:excess]

    def clear(self):
        self.history = []
