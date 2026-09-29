"""质量监察业务规则：四阶段时间轴、逾期自动退回、按时间去重与违章条款关联。

状态序列：待监察 → 监察中 → 待整改 → 已闭合。
- 待整改记录超过整改期限自动标红；非待整改状态（如监察中）的存量记录一旦
  超过期限，会被系统自动退回待整改，并在时间轴上留下红色的系统节点。
- 同一监察区域、同一天只允许开一条单，重复开单按时间去重直接拦下。
- 整改要求、整改期限为空不允许下达整改；发现违章必须关联到条款库的具体条款。
- 已闭合记录只读，任何动作与字段修改都拒绝。
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "qualitycheck"

STATUS_PENDING_INSPECT = "待监察"
STATUS_INSPECTING = "监察中"
STATUS_PENDING_FIX = "待整改"
STATUS_CLOSED = "已闭合"
STATUS_ORDER = [
    STATUS_PENDING_INSPECT,
    STATUS_INSPECTING,
    STATUS_PENDING_FIX,
    STATUS_CLOSED,
]

CREATE_REQUIRED = ["监察日期", "监察区域", "监察事项"]
EDITABLE_FIELDS = [
    "监察日期",
    "监察区域",
    "监察事项",
    "发现违章",
    "违章条款",
    "整改要求",
    "整改期限",
    "整改人",
    "整改情况",
]

# 违章条款库：监察记录里的违章内容必须能点到这里的某一条。
VIOLATION_CLAUSES: list[dict[str, str]] = [
    {
        "code": "JC-01",
        "name": "机坪车辆超速行驶",
        "basis": "《民用机场机坪运行管理规则》第六章 机坪交通管理",
        "description": "机坪内行驶的各种车辆超过规定限速，或在客机坪、行车通道超速抢行。",
        "guide": "对当事驾驶员停车培训并复考，调取行车记录核查，车队内部通报。",
    },
    {
        "code": "JC-02",
        "name": "未按规定路线行驶",
        "basis": "《民用机场机坪运行管理规则》第六章 机坪交通管理",
        "description": "车辆、设备未按指定服务路线行驶，违规穿越滑行道、跑道或侵入机位作业区。",
        "guide": "立即停止违章行驶，重新核准路线通行证，对责任单位下发整改通知单。",
    },
    {
        "code": "JC-03",
        "name": "加油作业未布置灭火器材",
        "basis": "《民用航空燃油供应安全管理规定》加油作业章节",
        "description": "航空器加油作业期间未在规定位置摆放灭火器材，或现场监护人员脱岗。",
        "guide": "立即停止加油作业，补齐灭火器材与监护人员后方可恢复，班组重新交底。",
    },
    {
        "code": "JC-04",
        "name": "装卸作业未挂安全网",
        "basis": "《民用机场行李和货物装卸运输管理规则》作业安全章节",
        "description": "行李货物装卸过程中未按规定系挂安全网、挡放轮挡，或舱门下方无人监护。",
        "guide": "停止作业并补设防护，对装卸班组开展现场复训并留存影像记录。",
    },
    {
        "code": "JC-05",
        "name": "廊桥对接撤离违规操作",
        "basis": "《旅客廊桥运行维护管理规程》操作流程章节",
        "description": "廊桥靠接、撤离未按确认单流程操作，轮挡撤放与机上联络环节缺失。",
        "guide": "操作员重新跟班考核，核对廊桥对接确认单填写与监控录像。",
    },
    {
        "code": "JC-06",
        "name": "作业区域遗留FOD",
        "basis": "《机场FOD防控管理规定》作业现场章节",
        "description": "作业结束后责任区域遗留外来物（FOD）、包装捆扎物或设备零件，未完成清扫。",
        "guide": "立即清扫并复查，按FOD台账登记来源，责任单位提交书面整改。",
    },
    {
        "code": "JC-07",
        "name": "作业人员未穿戴反光标识",
        "basis": "《机坪运行安全管理手册》个人防护章节",
        "description": "进入机坪作业区域的人员未按规定穿着反光背心或未佩戴准入证件。",
        "guide": "清退出场补全防护用品，准入培训补课后重新进入作业区。",
    },
    {
        "code": "JC-08",
        "name": "除冰作业记录不规范",
        "basis": "《航空器地面防冰除冰管理规定》记录与处置章节",
        "description": "除冰液配制、喷洒量、开始结束时间记录缺失，或废液未按指定渠道回收。",
        "guide": "补全除冰作业单并核对液位记录，规范废液回收交接，作业员重新培训。",
    },
]
CLAUSE_INDEX = {clause["code"]: clause for clause in VIOLATION_CLAUSES}

SYSTEM_ACTOR = "系统"
DEFAULT_ACTOR = "值班监察员"


def now_text() -> str:
    """时间轴节点的时间口径，精确到分钟。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def parse_date(value: Any) -> date | None:
    """容忍 None / 空串 / 非法日期，非法时返回 None 由调用方给错误提示。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def clean(value: Any) -> str:
    return str(value or "").strip()


class QualitycheckService:
    # ------------------------------------------------------------------ 读取

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        self.sweep_overdue()
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("监察编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        rows = sorted(rows, key=lambda row: (str(row.get("监察日期", "")), int(row.get("id", 0))))
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._decorate(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        self.sweep_overdue()
        entry = store.find(MODULE, entry_id)
        return self._decorate(entry) if entry else None

    def clause_list(self) -> list[dict[str, str]]:
        return VIOLATION_CLAUSES

    def month_rows(self, month: str) -> list[dict[str, Any]]:
        """取某月（YYYY-MM）的监察记录，时间轴与导出共用这一份口径。"""
        self.sweep_overdue()
        rows = [
            row
            for row in store.rows(MODULE)
            if str(row.get("监察日期", ""))[:7] == month
        ]
        return sorted(rows, key=lambda row: (str(row.get("监察日期", "")), int(row.get("id", 0))))

    def timeline_bundle(self, month: str, keyword: str | None = None) -> dict[str, Any]:
        """四阶段时间轴数据：每列条目、各列数量、本月逾期条数都在这里算。"""
        rows = self.month_rows(month)
        if keyword:
            key = keyword.strip()
            rows = [
                row
                for row in rows
                if key in str(row.get("监察编号", "")) or key in str(row.get("监察区域", ""))
            ]
        stages: list[dict[str, Any]] = []
        for stage_status in STATUS_ORDER:
            entries = [self._decorate(row) for row in rows if row.get("status") == stage_status]
            stages.append({
                "status": stage_status,
                "count": len(entries),
                "overdue": sum(1 for entry in entries if entry.get("overdue")),
                "entries": entries,
            })
        return {
            "month": month,
            "stages": stages,
            "total": len(rows),
            "overdueCount": sum(1 for row in rows if row.get("overdue")),
        }

    def export_month(self, month: str) -> tuple[str, int, int]:
        """导出当月监察清单，返回 CSV 文本、总条数与逾期条数（与时间轴同口径）。"""
        rows = self.month_rows(month)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "监察编号", "监察日期", "监察区域", "监察事项", "发现违章", "违章条款",
            "整改要求", "整改期限", "整改人", "监察状态", "是否逾期",
        ])
        for row in rows:
            writer.writerow([
                row.get("监察编号", ""),
                row.get("监察日期", ""),
                row.get("监察区域", ""),
                row.get("监察事项", ""),
                row.get("发现违章", ""),
                row.get("违章条款", ""),
                row.get("整改要求", ""),
                row.get("整改期限", ""),
                row.get("整改人", ""),
                row.get("status", ""),
                "逾期" if row.get("overdue") else "",
            ])
        overdue_count = sum(1 for row in rows if row.get("overdue"))
        writer.writerow([])
        writer.writerow(["合计", len(rows)])
        writer.writerow(["逾期条数", overdue_count])
        return buffer.getvalue(), len(rows), overdue_count

    def sweep_and_count_overdue(self) -> int:
        """供运营概览回写待办：先跑逾期引擎，再统计未闭合的逾期条数。"""
        self.sweep_overdue()
        return sum(
            1
            for row in store.rows(MODULE)
            if row.get("overdue") and row.get("status") != STATUS_CLOSED
        )

    def sweep_overdue(self, today: date | None = None) -> int:
        """逾期引擎：超期未闭合的记录标红，非待整改状态的自动退回待整改。

        幂等：已经处于逾期态的记录不重复写时间轴节点。闭合记录永不回退。
        """
        today = today or date.today()
        changed = 0
        for row in store.rows(MODULE):
            if row.get("status") == STATUS_CLOSED or row.get("overdue"):
                continue
            deadline = parse_date(row.get("整改期限"))
            if deadline is None or deadline >= today:
                continue
            row["overdue"] = True
            row["abnormal"] = True
            row["pending"] = True
            previous = row.get("status")
            if previous == STATUS_PENDING_FIX:
                note = f"整改期限 {row.get('整改期限')} 已到，记录仍未闭合，标记逾期"
            else:
                row["status"] = STATUS_PENDING_FIX
                note = f"整改期限 {row.get('整改期限')} 已过，系统自动退回待整改"
            self._add_node(row, "逾期自动退回", SYSTEM_ACTOR, note)
            changed += 1
        return changed

    # ------------------------------------------------------------------ 写入

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        self.sweep_overdue()
        rows = store.rows(MODULE)

        missing = [field for field in CREATE_REQUIRED if not clean(values.get(field))]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        if parse_date(values.get("监察日期")) is None:
            return None, "监察日期格式应为 YYYY-MM-DD"
        message = self._validate_clause(values)
        if message:
            return None, message

        day = clean(values["监察日期"])
        area = clean(values["监察区域"])
        duplicate = self._find_duplicate(day, area)
        if duplicate is not None:
            return None, (
                f"{area}在 {day} 已开监察单 {duplicate.get('监察编号')}，"
                "同一区域同一天按时间去重只保留一条，不再重复开单"
            )

        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "status": STATUS_PENDING_INSPECT,
            "pending": True,
            "abnormal": False,
            "overdue": False,
            "发现违章": "",
            "违章条款": "",
            "整改要求": "",
            "整改期限": "",
            "整改人": "",
            "整改情况": "",
        }
        for field in EDITABLE_FIELDS:
            entry[field] = clean(values.get(field))
        entry["监察编号"] = self._next_code(day)
        entry["timeline"] = [
            self._make_node(
                "登记监察记录",
                clean(values.get("operator")) or DEFAULT_ACTOR,
                f"在{area}登记监察事项：{entry['监察事项']}",
            )
        ]
        rows.append(entry)
        return self._decorate(entry), ""

    def update_entry(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """修改业务字段；闭合记录只读，改期改区域同样要过按时间去重。"""
        self.sweep_overdue()
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"监察记录 {entry_id} 不存在或已归档"
        if entry.get("status") == STATUS_CLOSED:
            return None, f"监察记录 {entry.get('监察编号')} 已闭合，不再接受任何修改"

        merged = {field: entry.get(field, "") for field in EDITABLE_FIELDS}
        for field in EDITABLE_FIELDS:
            if field in values:
                merged[field] = clean(values.get(field))

        missing = [field for field in CREATE_REQUIRED if not merged.get(field)]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        if parse_date(merged.get("监察日期")) is None:
            return None, "监察日期格式应为 YYYY-MM-DD"
        if merged.get("整改期限") and parse_date(merged.get("整改期限")) is None:
            return None, "整改期限格式应为 YYYY-MM-DD"
        message = self._validate_clause(merged)
        if message:
            return None, message

        duplicate = self._find_duplicate(merged["监察日期"], merged["监察区域"], exclude_id=entry_id)
        if duplicate is not None:
            return None, (
                f"{merged['监察区域']}在 {merged['监察日期']} 已开监察单 "
                f"{duplicate.get('监察编号')}，按时间去重不能重复开单"
            )

        actor = clean(values.get("operator")) or DEFAULT_ACTOR
        changed_fields = [
            field for field in EDITABLE_FIELDS
            if clean(merged.get(field)) != clean(entry.get(field))
        ]
        for field in EDITABLE_FIELDS:
            entry[field] = merged[field]
        if changed_fields:
            self._add_node(entry, "编辑记录", actor, f"修改字段：{'、'.join(changed_fields)}")
        return self._decorate(entry), ""

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        self.sweep_overdue()
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"监察记录 {entry_id} 不存在或已归档"
        if entry.get("status") == STATUS_CLOSED:
            return None, f"监察记录 {entry.get('监察编号')} 已闭合，不再接受任何修改"

        actor = clean(values.get("operator")) or DEFAULT_ACTOR
        status = entry.get("status")

        if action == "开展监察":
            if status != STATUS_PENDING_INSPECT:
                return None, "只有待监察的记录才能开展监察"
            entry["status"] = STATUS_INSPECTING
            self._add_node(entry, "开展监察", actor, "监察人员到岗，监察进行中")
            return self._decorate(entry), "监察已开始"

        if action == "下达整改":
            if status != STATUS_INSPECTING:
                return None, "只有监察中的记录才能下达整改"
            # 下达环节允许把整改要求、期限一并填上，但两个都不能为空。
            requirement = clean(values.get("整改要求")) or clean(entry.get("整改要求"))
            deadline_text = clean(values.get("整改期限")) or clean(entry.get("整改期限"))
            if not requirement or not deadline_text:
                empty = "整改要求" if not requirement else "整改期限"
                return None, f"{empty}为空，不允许进入下达环节"
            if parse_date(deadline_text) is None:
                return None, "整改期限格式应为 YYYY-MM-DD"
            entry["整改要求"] = requirement
            entry["整改期限"] = deadline_text
            entry["status"] = STATUS_PENDING_FIX
            entry["pending"] = True
            self._add_node(
                entry, "下达整改", actor,
                f"整改要求：{requirement}；整改期限：{deadline_text}",
            )
            return self._decorate(entry), "整改要求已下达，进入待整改"

        if action == "提交整改":
            if status != STATUS_PENDING_FIX:
                return None, "只有待整改的记录才能提交整改情况"
            fix_note = clean(values.get("整改情况"))
            fixer = clean(values.get("整改人")) or actor
            if not fix_note:
                return None, "整改情况为空，请先填写实际整改措施再提交"
            entry["整改情况"] = fix_note
            entry["整改人"] = fixer
            self._add_node(entry, "提交整改", fixer, f"整改情况：{fix_note}")
            return self._decorate(entry), "整改情况已记录，等待闭合确认"

        if action == "确认闭合":
            if status != STATUS_PENDING_FIX:
                return None, "只有待整改的记录才能确认闭合"
            opinion = clean(values.get("闭合意见")) or "整改结果复核通过"
            entry["status"] = STATUS_CLOSED
            entry["pending"] = False
            entry["abnormal"] = False
            entry["overdue"] = False  # 闭合后退出逾期待办，红色痕迹保留在时间轴节点上
            self._add_node(entry, "确认闭合", actor, opinion)
            return self._decorate(entry), "监察记录已闭合并锁定"

        return None, f"动作「{action}」不属于质量监察可执行范围"

    # ------------------------------------------------------------------ 辅助

    def _validate_clause(self, values: dict[str, Any]) -> str:
        """发现违章非空时，必须关联条款库里存在的条款编号。"""
        violation = clean(values.get("发现违章"))
        clause_code = clean(values.get("违章条款"))
        if violation and not clause_code:
            return "发现违章后必须关联具体违章条款，请选择条款后再提交"
        if clause_code and clause_code not in CLAUSE_INDEX:
            return f"违章条款 {clause_code} 不在条款库中"
        return ""

    def _find_duplicate(
        self, day: str, area: str, *, exclude_id: int | None = None
    ) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if exclude_id is not None and int(row.get("id", 0)) == exclude_id:
                continue
            if str(row.get("监察日期", "")) == day and str(row.get("监察区域", "")) == area:
                return row
        return None

    def _next_code(self, day: str) -> str:
        prefix = f"QUAL-{day.replace('-', '')}"
        sequence = (
            sum(1 for row in store.rows(MODULE) if str(row.get("监察编号", "")).startswith(prefix)) + 1
        )
        return f"{prefix}-{sequence:03d}"

    def _make_node(self, action: str, actor: str, note: str = "") -> dict[str, str]:
        return {"action": action, "actor": actor, "time": now_text(), "note": note}

    def _add_node(self, entry: dict[str, Any], action: str, actor: str, note: str = "") -> None:
        entry.setdefault("timeline", []).append(self._make_node(action, actor, note))

    def _decorate(self, entry: dict[str, Any]) -> dict[str, Any]:
        """给记录补展示字段（逾期天数、条款名称），不改动存储内容。"""
        result = dict(entry)
        result.setdefault("timeline", [])
        deadline = parse_date(entry.get("整改期限"))
        if entry.get("overdue") and deadline:
            result["逾期天数"] = max((date.today() - deadline).days, 0)
        else:
            result["逾期天数"] = 0
        clause = CLAUSE_INDEX.get(str(entry.get("违章条款") or ""))
        result["条款名称"] = clause["name"] if clause else ""
        return result
