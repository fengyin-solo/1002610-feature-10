"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        # 逾期回写：先跑质量监察逾期扫描，再把逾期条数作为待办放进概览，
        # 延迟导入避免和 service 层形成循环引用。
        from app.services.qualitycheck import MODULE as QC_MODULE
        from app.services.qualitycheck import QualitycheckService

        overdue_total = QualitycheckService().overdue_count()

        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            if name == QC_MODULE:
                # 先触发扫描，保证 pending/abnormal 与时间轴口径一致
                QualitycheckService().sweep_overdue()
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
            {"label": "逾期整改待办", "value": overdue_total},
        ]
        todos = [
            {
                "name": "质量监察逾期未整改",
                "module": QC_MODULE,
                "count": overdue_total,
                "detail": "已过整改期限的监察记录已自动标红并退回待整改，请尽快处理",
            }
        ]
        return {"cards": cards, "modules": modules, "todos": todos}


store = Store()
