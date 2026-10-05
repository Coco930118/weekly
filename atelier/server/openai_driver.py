"""未完成・未確定のOpenAI境界。実通信は実装／有効化していない。"""
class ProviderUnavailable(Exception):
    pass

class OpenAIDriver:
    name = 'openai'
    connected = False

    def execute(self, request):
        raise ProviderUnavailable('OpenAI未接続：接続機能は未完成・未確定です')
