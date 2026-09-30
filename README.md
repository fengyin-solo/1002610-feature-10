# 机场地面保障管理平台

面向机场地面保障的航空器引导、客梯对接、行李装卸、航油加注、除冰作业与廊桥调度的一体化管理后台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 机位分配 | `flightstand` | 机位 | 机位编号、机位类型、可停机型 |
| 引导入位 | `marshalling` | 引导任务 | 引导编号、对应航班、机位编号 |
| 廊桥对接 | `bridge` | 廊桥 | 廊桥编号、对应机位、适用机型 |
| 行李装卸 | `baggage` | 行李任务 | 任务编号、对应航班、行李类型 |
| 航食配餐 | `catering` | 配餐任务 | 配餐编号、对应航班、餐食类型 |
| 航油加注 | `fueling` | 加油任务 | 加油编号、对应航班、油料类型 |
| 除冰作业 | `deicing` | 除冰任务 | 除冰编号、对应航班、除冰液类型 |
| 清水排污 | `lavatory` | 排污任务 | 排污编号、对应航班、清水加注量 |
| 推出开车 | `pushback` | 推出任务 | 推出编号、对应航班、推出方向 |
| 地面设备 | `gse` | 地面设备 | 设备编号、设备类型、所属区域 |
| 货物装卸 | `cargo` | 货邮任务 | 货邮编号、对应航班、货物类型 |
| 放行签派 | `clearance` | 放行记录 | 放行编号、对应航班、签派员 |
| 过站保障 | `turnaround` | 过站任务 | 过站编号、对应航班、计划过站时间 |
| 机坪巡查 | `ramp` | 巡查记录 | 巡查编号、巡查区域、巡查日期 |
| 航空气象 | `weather2` | 气象观测 | 观测编号、观测时刻、能见度 |
| 特种车辆 | `vehicle` | 特种车辆 | 车辆编号、车辆类型、所属车队 |
| 人员排班 | `staffshift` | 排班记录 | 排班编号、岗位名称、值班人员 |
| 跑道灯光 | `runway` | 助航灯光 | 灯光编号、灯光类型、所在位置 |
| 应急处置 | `emergencyplan` | 应急预案 | 预案编号、预案名称、适用场景 |
| 质量监察 | `qualitycheck` | 监察记录 | 监察编号、监察日期、监察区域、违章条款、整改期限 |

### 质量监察时间轴

质量监察模块不再用纸质台账盯期限，记录按四个阶段竖排在时间轴看板上：
`待监察 → 监察中 → 待整改 → 已闭合`（`GET /api/qualitycheck/timeline`，支持 `month=YYYY-MM`）。

- **逾期自动退回**：任何查询都会先跑逾期扫描；已过整改期限且未闭合的记录在时间轴上标红，
  并自动退回「待整改」，退回动作（系统、时间）写入该记录的时间轴节点，且幂等不重复记。
- **节点留痕**：登记、开展监察、下达整改、确认闭合每个节点都记录操作人、操作时间和备注；
  确认闭合时记录整改责任人与整改时间。
- **同日去重**：同一监察区域、同一监察日期只允许一条记录，重复登记会被拦下并提示已存在的监察编号。
- **下达校验**：整改要求、整改期限、发现违章、违章条款任一为空都不允许下达；
  期限不得早于当天。违章条款从条款库选择（`GET /api/qualitycheck/clauses`），
  违章内容可点开查看具体条款全文。
- **闭合锁定**：已闭合记录不接受任何动作或修改。
- **逾期回写**：逾期条数回写到运营概览待办（`GET /api/overview` 的 `todos` 与「逾期整改待办」卡片）。
- **导出对账**：`GET /api/qualitycheck/export?month=YYYY-MM` 默认导出当月清单，
  返回的 `overdue` 与时间轴页面当月逾期数同口径计算，保证对得上。

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。
