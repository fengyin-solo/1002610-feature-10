"""质量监察接口：时间轴看板、登记去重、下达整改校验、当月清单导出。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.qualitycheck import STATUS_ORDER, QualitycheckService

router = APIRouter(prefix="/api/qualitycheck", tags=["质量监察"])

service = QualitycheckService()

LIST_FIELDS = ["监察编号", "监察日期", "监察区域", "监察事项", "发现违章", "整改要求", "整改期限", "监察状态"]


@router.get("/timeline")
def timeline(
    month: str | None = Query(default=None, description="按监察月份过滤，格式 YYYY-MM；不传为全部"),
) -> dict[str, Any]:
    """四阶段时间轴：待监察、监察中、待整改、已闭合竖着排，逾期记录带标红标记。"""
    return service.timeline(month=month)


@router.get("/clauses")
def list_clauses() -> dict[str, Any]:
    """违章条款目录：登记与下达整改时从这里选条款。"""
    return {"items": service.clauses()}


@router.get("/clauses/{code}")
def get_clause(code: str) -> dict[str, Any]:
    """条款全文：页面上点违章内容时弹出。"""
    clause = service.find_clause(code)
    if clause is None:
        raise HTTPException(status_code=404, detail=f"条款 {code} 不在条款库中")
    return clause


@router.get("/export")
def export_entries(
    month: str | None = Query(default=None, description="导出指定月份监察清单，格式 YYYY-MM；默认当月"),
) -> dict[str, Any]:
    """导出当月监察清单：逾期数与时间轴页面同口径，保证对得上。"""
    month = month or _current_month()
    items, total = service.list_entries(month=month, page=1, size=10000)
    overdue = service.overdue_count(month)
    return {"module": "qualitycheck", "month": month, "total": total, "overdue": overdue, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按监察编号检索"),
    status: str | None = Query(default=None, description="待监察、监察中、待整改、已闭合"),
    month: str | None = Query(default=None, description="按监察月份过滤，格式 YYYY-MM"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按监察编号、状态与月份过滤质量监察列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUS_ORDER:
        raise HTTPException(status_code=400, detail=f"状态仅支持：{'、'.join(STATUS_ORDER)}")
    items, total = service.list_entries(keyword=keyword, status=status, month=month, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条监察记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"监察记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条监察记录；同区域同日重复开单或缺字段会被拦下并说明原因。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="监察记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """开展监察、下达整改、确认闭合；逾期自动退回与闭合只读都在此拦截。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


def _current_month() -> str:
    from app.services.qualitycheck import _today

    return _today().strftime("%Y-%m")
