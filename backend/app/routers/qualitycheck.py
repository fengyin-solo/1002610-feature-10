"""质量监察接口：四阶段时间轴、逾期自动退回、按时间去重与当月清单导出。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Response

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.qualitycheck import (
    STATUS_ORDER,
    QualitycheckService,
)

router = APIRouter(prefix="/api/qualitycheck", tags=["质量监察"])

service = QualitycheckService()

LIST_FIELDS = [
    "监察编号", "监察日期", "监察区域", "监察事项", "发现违章", "违章条款",
    "整改要求", "整改期限", "监察状态",
]


def current_month() -> str:
    return date.today().strftime("%Y-%m")


@router.get("/timeline")
def timeline(
    month: str | None = Query(default=None, description="月份 YYYY-MM，默认当月"),
    keyword: str | None = Query(default=None, description="按监察编号或区域检索"),
) -> dict[str, object]:
    """把监察记录摊到四个阶段的时间轴上，逾期标红并带上本月逾期条数。"""
    target_month = month or current_month()
    return service.timeline_bundle(target_month, keyword=keyword)


@router.get("/clauses")
def list_clauses() -> dict[str, object]:
    """违章条款库：发现违章时必须点到其中某一条具体条款。"""
    return {"items": service.clause_list()}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按监察编号检索"),
    status: str | None = Query(default=None, description="待监察、监察中、待整改、已闭合"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按监察编号与状态过滤质量监察列表；没有数据时返回空页，不报错。"""
    if status and status not in STATUS_ORDER:
        raise HTTPException(status_code=400, detail=f"未知监察状态：{status}")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    month: str | None = Query(default=None, description="导出月份 YYYY-MM，默认当月"),
) -> Response:
    """导出当月监察清单 CSV；逾期合计与时间轴页面用同一套统计口径。

    X-Export-Total / X-Export-Overdue 两个自定义响应头给前端做对账，
    保证「清单上的逾期数」和「页面上看到的逾期数」是同一次计算的结果。
    """
    target_month = month or current_month()
    content, total, overdue_count = service.export_month(target_month)
    response = Response(content="﻿" + content, media_type="text/csv; charset=utf-8")
    filename = f"qualitycheck-{target_month}.csv"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["X-Export-Month"] = target_month
    response.headers["X-Export-Total"] = str(total)
    response.headers["X-Export-Overdue"] = str(overdue_count)
    response.headers["Access-Control-Expose-Headers"] = (
        "X-Export-Month, X-Export-Total, X-Export-Overdue"
    )
    return response


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条监察记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"监察记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记监察记录；同区域同天重复开单、违章未关联条款都会被拦下。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="监察记录已登记", entry=entry)


@router.patch("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """修改未闭合记录的业务字段；闭合记录一律拒绝。"""
    entry, message = service.update_entry(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="监察记录已更新", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """开展监察、下达整改、提交整改、确认闭合；时间轴节点记录操作人与时间。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
