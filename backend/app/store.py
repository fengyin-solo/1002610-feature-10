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
        # 质量监察模块单独回传逾期条数，供概览待办区报警。
        # 延迟导入：service 层反过来 import store，模块加载期引用会形成环。
        from app.services.qualitycheck import MODULE as QC_MODULE, QualitycheckService

        qualitycheck_overdue = QualitycheckService().sweep_and_count_overdue()
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            item: dict[str, object] = {
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            }
            if name == QC_MODULE:
                item["overdue"] = qualitycheck_overdue
            modules.append(item)
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        todos = [
            {
                "label": "监察整改逾期",
                "value": qualitycheck_overdue,
                "tone": "danger" if qualitycheck_overdue else "normal",
                "link": "/qualitycheck",
            }
        ] if qualitycheck_overdue else []
        return {"cards": cards, "todos": todos, "modules": modules}


store = Store()
