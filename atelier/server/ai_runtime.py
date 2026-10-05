"""provider adapter境界。権限・revision・Coco保護の検査は保存時にも行う。"""
from .openai_driver import OpenAIDriver, ProviderUnavailable

class AIRuntime:
    def __init__(self, workspace):
        self.workspace = workspace
        self.provider = OpenAIDriver()

    def execute(self, key, candidate, employee, expected_revision, expected_candidate_revision):
        # 本番接続は意図的に未実装。素材・投稿本文をproviderへ送らない。
        error = None
        with self.workspace.transaction() as db:
            try:
                state = self.workspace._load(db, key)
                self.workspace.check_revision(state, expected_revision)
                self.workspace.check_candidate_revision(state, candidate, expected_candidate_revision)
                person = self.workspace.employee(employee)
                if person['media'] and state['platform'] not in person['media']:
                    from .server import WorkspaceError
                    raise WorkspaceError('PERMISSION', '担当媒体の権限がありません')
                self.workspace.log(db, key, employee, 'blocked', 'AI_DISABLED', candidate)
            except Exception as exc:
                from .server import WorkspaceError
                if not isinstance(exc, WorkspaceError):
                    raise
                error = exc
                self.workspace.log(db, key, employee, 'blocked', exc.code, candidate)
        if error:
            raise error
        raise ProviderUnavailable('AI未接続：AI実行は有効化されていません')

    def save_result(self, key, candidate, employee, expected_revision,
                    expected_candidate_revision, result):
        """外部結果の保存境界。現在のUIから生成結果は渡されない。"""
        return self.workspace.save_ai_result(key, candidate, employee,
                    expected_revision, expected_candidate_revision, result)
