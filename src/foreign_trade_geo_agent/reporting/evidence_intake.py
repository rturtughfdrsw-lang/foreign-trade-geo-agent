"""Local customer request rendering; creates no message or remote side effect."""
from dataclasses import asdict
from datetime import UTC, datetime
import json

from foreign_trade_geo_agent.core.evidence_intake import CustomerEvidenceRequest, PlanningReviewCandidate, require


def customer_request_json(request: CustomerEvidenceRequest) -> str:
    require(type(request) is CustomerEvidenceRequest)
    return json.dumps(asdict(request), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)


def render_customer_request(request: CustomerEvidenceRequest) -> str:
    require(type(request) is CustomerEvidenceRequest)
    lines = [f"任务：{request.goal}", f"客户：{request.customer_id}；任务：{request.task_id}",
        f"版本：task={request.task_version}, Plan={request.plan_version}, evidence={request.evidence_version}",
        f"提交绑定：{request.snapshot_sha256}", "", "以下列出具体资料缺口与待审核事项；材料提交不等于事实已审核。"]
    if not request.gaps:
        lines.append("当前没有客户补充缺口。")
    for gap in request.gaps:
        r = gap.requirement
        lines.extend(["", f"{r.requirement_id} / {gap.change_ref} / EXPLAIN {gap.point_subject}",
            f"所需事实：{r.required_fact}", f"具体用途：{r.intended_use}",
            f"现有材料不足：{r.existing_material_insufficiency}", f"当前缺口：{gap.reason_code}"])
        if gap.review_reason:
            lines.append(f"审核说明：{gap.review_reason}")
        if gap.reason_code in {"HUMAN_SEMANTIC_REVIEW_REQUIRED", "UNREVIEWED"}:
            lines.append("资料已提交，等待人工语义判断；无需为此重复提交。")
        else:
            lines.extend(["允许补充方式：" + "、".join(m.value for m in r.allowed_methods),
                          "请保留来源名称、具体位置和归属；文档方式只接受保留原字节的 UTF-8 文本。"])
    lines.extend(["", "调整目标或删减内容义务需客户对具体新目标和保留义务明确同意。",
                  "证据审核通过后仍只进入后续审核候选；本请求不授予 Draft 或发布权限。"])
    if request.staff_action:
        lines.append(f"工作人员待办：{request.staff_action}")
    return "\n".join(lines) + "\n"


def planning_review_json(candidate: PlanningReviewCandidate) -> str:
    """Exact native context and per-obligation evidence for HUMAN semantic review.

    Includes full P/S/A context and all evidence history, even conflicting or
    superseded material. A locator remains a customer declaration. This local
    report is neither a review receipt nor a Draft authorization credential.
    """
    require(type(candidate) is PlanningReviewCandidate)
    def encode(value):
        if isinstance(value, datetime):
            return value.astimezone(UTC).isoformat()
        raise TypeError("INTAKE_REVIEW_RENDER_REJECTED")
    payload = asdict(candidate)
    payload["draft_authorized"] = False
    payload["staff_action"] = "RETURN_TO_EVIDENCE_INTAKE" if candidate.return_to_intake else "HUMAN_SEMANTIC_REVIEW_REQUIRED"
    payload["claim_verdicts"] = {c.requirement.requirement_id: c.verdict.value for c in candidate.claims}
    payload["review_instructions"] = (
        "Review each fact obligation, source authority, exact spans, applicability, contradictions and explanation depth.",
        "Support/CONFLICT/MISSING/IRRELEVANT/UNREVIEWED come only from explicit human decisions or material absence.",
        "Customer locators are attributed declarations; no PDF page, source authority or semantic sufficiency is verified automatically.",
        "Reauthenticate human decisions against the current snapshot; this report authorizes no Draft or CMS action.",
    )
    return json.dumps(payload, default=encode, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
