"""Read retained Web articles without composing a model executor or permit."""
from foreign_trade_geo_agent.web.generation import LocalGeneration, check, read_json


class SavedArticleGeneration(LocalGeneration):
    def selected(self):
        if not (self.root / 'selected.json').exists():
            return None
        key = read_json(self.root / 'selected.json')['binding_sha256']
        check(type(key) is str and len(key) == 64 and all(c in '0123456789abcdef' for c in key),
              'LOCAL_RECORD_INVALID')
        output = self.root / key
        result = read_json(output / 'result.json')
        check(result['state'] == 'SUCCEEDED' and result['mode'] in {'MOCK', 'LIVE'}
              and result['binding_sha256'] == key and result['production_authorized'] is False
              and not (output / 'failed.json').exists(), 'LOCAL_RECORD_INVALID')
        # The service also validates the native run, Draft, project/task and E
        # evidence. Reading LIVE output grants neither model nor CMS capability.
        return output / 'history.sqlite3', result

    def view(self):
        try:
            available = bool(self.selected())
        except Exception:
            available = False
        return dict(generation_state='READ_ONLY', generation_allowed=False,
                    generation_reason='离线交付验收：仅查看已保存文章，模型执行禁用。',
                    attempt=None, binding_sha256='', generation_expires_at='',
                    web_candidate_available=available)

    def start(self, *args, **kwargs):
        from foreign_trade_geo_agent.web.mvp_application import MVPError
        raise MVPError('离线交付工作台不允许模型请求。', 409)
