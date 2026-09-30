"""质量监察业务规则：时间轴、逾期退回、同日去重与下达校验都收在这里。

四个阶段固定按顺序排列：待监察 → 监察中 → 待整改 → 已闭合。
- 任何读取入口都会先跑一次逾期扫描：已过整改期限且未闭合的记录标红并
  自动退回待整改，退回动作写进该记录的时间轴；
- 同一监察区域、同一监察日期只允许存在一条记录，重复登记会被拦下；
- 下达整改必须带齐整改要求、整改期限以及对应的违章条款；
- 已闭合记录只读，任何动作与修改都不接受。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "qualitycheck"
REQUIRED_FIELDS = ["监察编号", "监察日期", "监察区域", "监察事项"]
ISSUANCE_FIELDS = ["发现违章", "违章条款", "整改要求", "整改期限"]
STATUS_ORDER = ["待监察", "监察中", "待整改", "已闭合"]
CLOSED = "已闭合"
PENDING_RECTIFY = "待整改"
ACTION_RULES = {"开展监察": "监察中", "下达整改": "待整改", "确认闭合": "已闭合"}
# 哪些阶段允许执行哪个动作，防止跳着点
ACTION_GUARDS = {
    "开展监察": ["待监察"],
    "下达整改": ["监察中", "待整改"],  # 逾期退回后允许再次下达
    "确认闭合": ["待整改"],
}

# 违章条款库：登记/下达时从这里选条款，页面上点条款能看到全文。
# 条款命名沿用民航地面安全常用规章口径（示例库）。
CLAUSES: list[dict[str, str]] = [
    {
        "code": "CCAR-140-2022-12-03",
        "title": "民用机场运行安全管理规定 第12.3条",
        "category": "航油加注",
        "content": "航油加注作业前必须完成静电接地连接并确认接地良好，未接地或接地报警未消除时，严禁实施加油作业。",
    },
    {
        "code": "CCAR-140-2022-17-02",
        "title": "民用机场运行安全管理规定 第17.2条",
        "category": "机坪车辆",
        "content": "机坪内行驶的各类作业车辆严禁货叉、托盘载人；车辆靠近航空器时应按规定路线低速行驶并设专人观察。",
    },
    {
        "code": "CCAR-140-2022-22-04",
        "title": "民用机场运行安全管理规定 第22.4条",
        "category": "货物运输",
        "content": "行李、货物在拖斗或传送设备上的码放不得超过限高、限重标识，码放不稳固的不得拖行。",
    },
    {
        "code": "MH/T-3010-2024-05-01",
        "title": "民用航空器地面维修安全规则 第5.1条",
        "category": "廊桥对接",
        "content": "廊桥对接航空器前必须完成轮挡放置与周边净空确认，确认未完成不得移动廊桥。",
    },
    {
        "code": "MH/T-3010-2024-08-02",
        "title": "民用航空器地面维修安全规则 第8.2条",
        "category": "除防冰",
        "content": "除冰作业期间作业人员必须穿戴防化服与护目镜，除冰液废液应集中回收，不得直接排入机坪排水系统。",
    },
    {
        "code": "AC-140-CA-2023-06-01",
        "title": "机坪运行管理咨询通告 第6.1条",
        "category": "人员行为",
        "content": "进入机坪作业区域的人员必须按规定穿戴反光背心并沿指定路线行走，严禁从机翼下方及发动机尾喷口区域穿行。",
    },
]
CLAUSE_INDEX = {item["code"]: item for item in CLAUSES}


def _today() -> date:
    """单独抽出来，方便测试里把"今天"换掉。"""
    return date.today()


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


class QualitycheckService:
    # ---------- 逾期 ----------
    def sweep_overdue(self) -> list[dict[str, Any]]:
        """逾期扫描：过了整改期限还没闭合的记录标红并退回待整改。

        只做一次幂等处理：同一条记录不会重复追加退回节点。
        """
        today = _today()
        overdue_rows: list[dict[str, Any]] = []
        for row in store.rows(MODULE):
            due = _parse_date(row.get("整改期限"))
            if row.get("status") == CLOSED or due is None:
                row["overdue"] = False
                continue
            is_overdue = due < today
            row["overdue"] = is_overdue
            if is_overdue:
                row["abnormal"] = True
                overdue_rows.append(row)
                already = any(node.get("auto") for node in row.get("timeline", []))
                if row.get("status") != PENDING_RECTIFY and not already:
                    row["status"] = PENDING_RECTIFY
                    row["pending"] = True
                    row.setdefault("timeline", []).append({
                        "stage": PENDING_RECTIFY,
                        "action": "逾期自动退回",
                        "operator": "系统",
                        "time": _now_text(),
                        "note": f"整改期限 {due.isoformat()} 已过，自动退回待整改",
                        "auto": True,
                    })
        return overdue_rows

    def overdue_count(self, month: str | None = None) -> int:
        rows = self.sweep_overdue()
        if month:
            rows = [row for row in rows if str(row.get("监察日期", ""))[:7] == month]
        return len(rows)

    # ---------- 查询 ----------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        month: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        self.sweep_overdue()
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("监察编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if month:
            rows = [row for row in rows if str(row.get("监察日期", ""))[:7] == month]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        self.sweep_overdue()
        return store.find(MODULE, entry_id)

    def timeline(self, month: str | None = None) -> dict[str, Any]:
        """时间轴看板：四阶段竖排，附带各阶段计数与当月逾期数。"""
        rows, total = self.list_entries(month=month, page=1, size=10000)
        stages = [
            {"stage": stage, "entries": [row for row in rows if row.get("status") == stage]}
            for stage in STATUS_ORDER
        ]
        return {
            "stages": stages,
            "total": total,
            "month": month,
            "overdue": self.overdue_count(month),
        }

    def clauses(self) -> list[dict[str, str]]:
        return CLAUSES

    def find_clause(self, code: str) -> dict[str, str] | None:
        return CLAUSE_INDEX.get(str(code).strip())

    # ---------- 登记 ----------
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        text_values = {
            key: str(values.get(key) or "").strip()
            for key in REQUIRED_FIELDS + ["发现违章", "违章条款"]
        }
        missing = [field for field in REQUIRED_FIELDS if not text_values[field]]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"

        inspect_date = _parse_date(text_values["监察日期"])
        if inspect_date is None:
            return None, "监察日期格式不正确，应为 YYYY-MM-DD"

        # 同区域同一天重复开单：时间轴按时间去重，只留一条。
        duplicate = self._find_duplicate(text_values["监察区域"], inspect_date.isoformat())
        if duplicate is not None:
            return None, (
                f"{inspect_date.isoformat()} {text_values['监察区域']} 已存在监察记录"
                f"（{duplicate.get('监察编号')}），同区域同一天不允许重复开单"
            )

        clause_code = text_values["违章条款"]
        if clause_code and clause_code not in CLAUSE_INDEX:
            return None, f"违章条款「{clause_code}」不在条款库里，请从条款目录中选择"

        rows = store.rows(MODULE)
        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "status": STATUS_ORDER[0],
            "pending": True,
            "abnormal": False,
            "overdue": False,
            "发现违章": text_values["发现违章"],
            "违章条款": clause_code or None,
            "整改要求": "",
            "整改期限": None,
            "整改人": None,
            "整改时间": None,
            "timeline": [{
                "stage": STATUS_ORDER[0],
                "action": "登记监察",
                "operator": str(values.get("operator") or "值班管理员").strip(),
                "time": _now_text(),
                "note": "",
            }],
        }
        for field in REQUIRED_FIELDS:
            entry[field] = text_values[field]
        rows.append(entry)
        return entry, ""

    def _find_duplicate(self, area: str, day_text: str, exclude_id: int | None = None) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if exclude_id is not None and int(row.get("id", 0)) == exclude_id:
                continue
            if str(row.get("监察区域", "")).strip() == area and str(row.get("监察日期", ""))[:10] == day_text:
                return row
        return None

    # ---------- 流转 ----------
    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        self.sweep_overdue()
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"监察记录 {entry_id} 不存在或已归档"
        if entry.get("status") == CLOSED:
            return None, f"监察记录 {entry_id} 已闭合，闭合记录不接受任何修改"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于质量监察可执行范围"
        target = ACTION_RULES[action]
        if entry.get("status") not in ACTION_GUARDS.get(action, []):
            return None, f"当前状态为「{entry.get('status')}」，不能执行「{action}」"

        operator = str(values.get("operator") or "值班管理员").strip()

        # 下达整改：整改要求、整改期限、违章条款缺一不可。
        if action == "下达整改":
            issue = {
                "发现违章": str(values.get("发现违章") or entry.get("发现违章") or "").strip(),
                "违章条款": str(values.get("违章条款") or entry.get("违章条款") or "").strip(),
                "整改要求": str(values.get("整改要求") or "").strip(),
                "整改期限": str(values.get("整改期限") or "").strip(),
            }
            missing = [field for field in ISSUANCE_FIELDS if not issue[field]]
            if missing:
                return None, f"下达整改前必须填写：{'、'.join(missing)}"
            if issue["违章条款"] not in CLAUSE_INDEX:
                return None, "违章条款不在条款库里，请从条款目录中选择"
            due = _parse_date(issue["整改期限"])
            if due is None:
                return None, "整改期限格式不正确，应为 YYYY-MM-DD"
            if due < _today():
                return None, "整改期限不能早于今天，请重新约定期限"
            entry["发现违章"] = issue["发现违章"]
            entry["违章条款"] = issue["违章条款"]
            entry["整改要求"] = issue["整改要求"]
            entry["整改期限"] = due.isoformat()

        # 确认闭合：记录谁在什么时间完成整改，写在时间轴节点上。
        if action == "确认闭合":
            rectifier = str(values.get("整改人") or operator).strip()
            if not rectifier:
                return None, "确认闭合需要填写整改责任人"
            rectify_time = _now_text()
            entry["整改人"] = rectifier
            entry["整改时间"] = rectify_time
            entry["overdue"] = False
            entry["abnormal"] = False

        entry["status"] = target
        entry["pending"] = target != CLOSED
        entry.setdefault("timeline", []).append({
            "stage": target,
            "action": action,
            "operator": operator,
            "time": _now_text(),
            "note": str(values.get("note") or "").strip(),
        })
        return entry, f"监察记录已{action}"
