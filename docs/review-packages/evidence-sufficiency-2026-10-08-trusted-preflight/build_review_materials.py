"""Local read-only source inspection; creates new UNSIGNED owner materials once."""
import hashlib
import json
from pathlib import Path

from foreign_trade_geo_agent.core.content_draft import ContentDraftInput
from foreign_trade_geo_agent.core.evidence_sufficiency import (
    ExcerptObligation, ExcerptReviewTarget, REQUIRED_REVIEW_DECISIONS, excerpt_target_error,
)
from foreign_trade_geo_agent.core.first_party_planning import FirstPartyExcerpt, FirstPartyPlanningScope
from foreign_trade_geo_agent.core.history import ArtifactType
from foreign_trade_geo_agent.adapters.evidence_review import (
    canonical_bytes, draft_input_digest, freeze_excerpt_target,
)
from foreign_trade_geo_agent.storage.serialization import decode_artifact

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "evidence-sufficiency-2026-10-08-excerpt-v2"


def read(name):
    return json.loads((OLD / name).read_bytes())


def build():
    outputs = ("README.md", "owner-obligations.md", "frozen-target.json", "review-record.UNSIGNED.template.json", "lineage.json")
    if any((HERE/name).exists() for name in outputs):
        raise ValueError("Refuse to replace prepared review materials")
    binding = read("binding.json")
    old_binding_digest = hashlib.sha256(canonical_bytes(binding)).hexdigest()
    assert old_binding_digest == read("manifest.json")["binding_canonical_sha256"]
    for name, digest in binding["files_sha256"].items():
        assert hashlib.sha256((OLD/name).read_bytes()).hexdigest() == digest, name
    def artifact(kind, name):
        return decode_artifact(kind, 1, (OLD/name).read_bytes().decode("utf-8"))
    packet = artifact(ArtifactType.SITE_CONTENT, "snapshots/site_content.json")
    inp = ContentDraftInput(packet, artifact(ArtifactType.CONTENT_OPPORTUNITY, "content_opportunity.json"),
                            artifact(ArtifactType.CHANGE_PLAN, "change_plan.json"))
    task, coverage, raw_scope = read("task.json"), read("coverage.json"), read("planning-scope.json")
    scope = FirstPartyPlanningScope(raw_scope["task_id"], packet, raw_scope["page_ref"], raw_scope["heading"],
                                    tuple(FirstPartyExcerpt(**e) for e in raw_scope["excerpts"]))
    obligations = tuple(ExcerptObligation(o["obligation_id"], o["artifact_span"]["quote"],
        tuple(scope.excerpts.index(FirstPartyExcerpt(**e)) for e in o["excerpt_spans"])) for o in coverage["obligations"])
    assert [o.obligation_id for o in obligations] == task["required_obligation_ids"]
    target = ExcerptReviewTarget(
        "foreign-trade-geo-agent", task["task_id"], task["task_version"], 2, 1, task["question"],
        "NovaCNC controlled demonstration solutions page: " + task["source_page_url"],
        "NovaCNC is a fictional brand. This website does not represent an operating manufacturer and cannot accept orders.",
        scope, inp, obligations,
    )
    assert excerpt_target_error(target) is None
    frozen = freeze_excerpt_target(target)
    target_digest = hashlib.sha256(frozen).hexdigest()
    input_digest = draft_input_digest(inp)
    assert input_digest == read("draft-visible-input.json")["actual_DraftInput_canonical_sha256"]
    source = (OLD/"snapshots/solutions.astro").read_bytes().decode("utf-8")
    field = packet.pages[2].structured_content[0].text
    content = ["# O1–O6 人工核验：全部 NOT_REVIEWED", "",
        "本材料仅供项目所有者核验，不构成签核、工程事实、SEO 效果或 EXPLAIN 认可。",
        "", f"任务：`{target.task_id}` / task_version=2；Plan候选版本=2；证据快照版本=1；既有 artifact codec=V1。",
        f"Plan：R1 → C1 / EXPAND_SECTION / P3 / `{scope.heading}`；S/A 均为空。",
        f"原包 binding canonical SHA-256：`{old_binding_digest}`。",
        f"新 frozen-target SHA-256：`{target_digest}`。",
        f"实际 DraftInput canonical SHA-256：`{input_digest}`。",
        "", "坐标均为原始 UTF-8 解码后的 Unicode code points，零基、半开区间，无空白规范化。",
        "source URL 是 locator，仅读取本地 snapshots；未访问网站。", "",
        "虚构声明原文（snapshots/DemoDisclosure.astro [163,276)，不在 P3 Draft material 中）：",
        f"> {target.context}", "", "该声明及逐字/全部义务限制现已在新 frozen-target 单独绑定；没有 writer 消费成功的主张。", ""]
    for o, obligation in zip(coverage["obligations"], obligations):
        assert o["task_id"] == task["task_id"] and o["task_version"] == 2
        assert o["human_support_verdict"] == "NOT_REVIEWED" and o["human_reason"] is None
        a, s = o["artifact_span"], o["corroborating_source_span"]
        assert field[a["start"]:a["end"]] == source[s["start"]:s["end"]] == obligation.statement
        assert hashlib.sha256(field.encode()).hexdigest() == a["field_sha256"]
        assert hashlib.sha256(source.encode()).hexdigest() == s["field_sha256"]
        parts = ", ".join(f'[{e["start"]},{e["end"]})' for e in o["excerpt_spans"])
        content.extend([f'## {obligation.obligation_id}：{o["group_label"]}', "", o["question"], "",
            f"> {obligation.statement}", "",
            f'- evidence：P3 / {task["source_page_url"]} / heading `{scope.heading}`。',
            f'- 原 artifact locator：`{o["field_path"]}` [{a["start"]},{a["end"]})。',
            f'- Draft serializer preview：`{o["draft_visible_span"]["field_path"]}` [{a["start"]},{a["end"]})；仅预览。',
            f'- 本地源文件：旧包 `snapshots/solutions.astro` 对应 `{o["corroborating_source_path"]}` [{s["start"]},{s["end"]})。',
            f'- 原文 field SHA-256：`{a["field_sha256"]}`；quote SHA-256：`{a["quote_sha256"]}`。',
            f'- 原源码 SHA-256：`{s["field_sha256"]}`。',
            f'- scope fragments：{parts}；完整覆盖索引 `{obligation.excerpt_indexes}`。',
            f'- C1 点位：`{"`, `".join(o["content_point_paths"])}`。',
            f'- 允许范围：{o["allowed_output"]}',
            f'- 核验要点：{o["reviewer_checks"]}',
            '- 待人工填写：verdict、reason；不得由准备者填 APPROVED。', "",
            f'前文：{o["context_before"]}', "", f'后文：{o["context_after"]}', ""])
    template = {
        "schema_version": 1, "record_id": None, "reviewer_id": None,
        "purpose": target.purpose, "project_id": target.project_id, "task_id": target.task_id,
        "task_version": 2, "plan_version": 2, "evidence_version": 1,
        "frozen_target_sha256": target_digest, "draft_input_sha256": input_digest,
        "reviewed_at": None, "expires_at": None, "signoff": "NOT_REVIEWED",
        "obligations": [{"obligation_id": o.obligation_id, "verdict": "NOT_REVIEWED", "reason": None} for o in obligations],
        "decisions": [{"decision_id": d, "verdict": "NOT_REVIEWED", "reason": None} for d in REQUIRED_REVIEW_DECISIONS],
    }
    lineage = {
        "status": "UNSIGNED_NOT_REVIEWED", "old_binding_canonical_sha256": old_binding_digest,
        "old_coverage_root_task_id": coverage["task_id"], "old_coverage_root_task_version": coverage["task_version"],
        "correction": "Old root retained v1; six rows and task/scope/Plan binding are v2. New target explicitly uses v2; old bytes retained.",
        "frozen_target_sha256": target_digest, "draft_input_sha256": input_digest,
        "plan_version_meaning": "Native excerpt candidate v2, not codec or invented HistoryStore artifact id",
        "evidence_version_meaning": "Unchanged frozen SITE_CONTENT snapshot, artifact codec V1",
        "O1_to_O6": "NOT_REVIEWED", "production_review_source": "UNAVAILABLE",
    }
    readme = f'''# 真实六项材料：待人工签核包

全部 O1–O6 / D01–D07 均 NOT_REVIEWED，unsigned；真实 Gate NO-GO。旧的有限离线用途授权不等于本完整任务签核。D08 商业验收仍待另行真实审核。

- [逐项核验材料](owner-obligations.md)：六项原文、上下文、精确 locator/spans、七个 content points、义务覆盖及 Plan 绑定。
- [冻结目标](frozen-target.json)：独立 task v2、Plan candidate v2、证据快照 v1、完整原生 DraftInput，及额外绑定的归属/虚构语境/输出范围。
- [未签核模板](review-record.UNSIGNED.template.json)：没有 reviewer、时间或 proof；编辑此文件不能取得权限。
- [lineage](lineage.json)：旧 coverage 顶层 v1 的显式更正记录，原包字节保持。

frozen-target SHA-256：`{target_digest}`；DraftInput：`{input_digest}`。

人工需逐项确认 SOURCE_USE（仅原有项目离线用途）、TASK_AND_DEPTH（完整逐字六项任务）、OFFLINE_PLACEMENT（测试展示，非商业改版）、P_ONLY_CANDIDATE（仅本 R1/C1）、FROZEN_CONSUMPTION（将来必须消费同一冻结对象，本轮未写作）、REVIEW_AUTHORITY（真实身份与任务权限）、VALIDITY_AND_STORAGE（最长24小时、撤销和可信保存），并填写六项 verdict/reason。商业 D08 不属于这份离线授权，也没有被排除后默认为批准。

可信来源尚缺：受保护身份/权限/密钥与撤销服务、可信签核存储及 append-only lineage。生产运行没有 authenticator，默认拒绝。只有 tests 中的随机内存 HMAC synthetic fixture 可取得 SYNTHETIC_GREEN；它与真实 NovaCNC 六项签核分开。

preflight 没有 writer，结果不构成 Draft/CMS capability。原生 Draft builder/workflow 仍拒绝 P-only 输入。没有生成正式 Draft，没有外部调用或签名。
'''
    for name, raw in (("README.md", readme.encode()), ("owner-obligations.md", "\n".join(content).encode()),
                      ("frozen-target.json", frozen), ("review-record.UNSIGNED.template.json", canonical_bytes(template)),
                      ("lineage.json", canonical_bytes(lineage))):
        (HERE/name).write_bytes(raw)
    print(json.dumps({"status": "UNSIGNED_NOT_REVIEWED", "frozen_target_sha256": target_digest,
                      "draft_input_sha256": input_digest, "obligations": 6, "spans": 7}))


if __name__ == "__main__":
    build()
