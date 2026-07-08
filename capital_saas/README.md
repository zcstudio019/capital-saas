# AI企业资本战略诊断SaaS系统

这是一个面向中小企业主的本地可运行企业融资 SaaS，品牌名为“沪上银”。系统提供企业融资规划、财商诊断、商业战略分析、分层产品销售、Mock 支付解锁和销售线索跟进。

当前版本使用确定性规则评分和 Mock AI Agent，不调用外部模型；支付同样为 Mock，不会产生真实扣款。

## 功能说明

- 企业测评：采集经营、财务、负债、融资条件和财商认知信息。
- 自动评分：按六个维度计算 100 分制评分并生成 S/A/B/C/D 等级。
- 免费结果：展示总分、等级、银行风险、核心风险和财商短板。
- 付费漏斗：299 元 Mock 支付后解锁完整报告。
- 完整报告：包含商业模式、财务、SWOT、融资、资金投放、贷后管理等 10 章。
- CRM 线索：测评后自动创建线索并推荐后续产品。
- 管理后台：查看测评统计、线索、报告、订单和收入。
- 销售线索评分：按融资需求、企业评分、征信纳税、抵押物和现金流计算 100 分制销售评分。
- AI 销售话术：针对 S/A/B/C/D 线索自动生成开场、痛点、方案、跟进和升级话术。
- CRM 跟进：筛选线索、查看详情、分配销售、设置下次跟进时间并记录跟进状态。
- 产品分层：支持 299 元诊断报告、699 元银行匹配报告和 1999 元融资结构优化方案。
- 自动升级转化：完整报告根据已购最高产品动态展示下一档升级入口。
- 旧库迁移：应用启动和数据库初始化时自动检查并补齐 Phase 2 字段。
- 顾问式报告：每章包含结论、关键问题、银行判断、老板动作和下一步建议。
- 银行模拟审批：输出通过概率、额度区间、拒贷原因、银行偏好、申请顺序和改善动作。
- 跟进任务：按线索等级自动创建电话、微信、报告发送、付款跟进、升单和回访任务。
- 成交漏斗：统计测评、线索、付费企业、订单结构、收入及等级转化率。
- 事件埋点：记录测评、结果查看、结算、支付、报告、升级、线索更新和任务完成事件。
- 打印报告：提供独立打印页面，可通过浏览器保存为 PDF。
- JSON API：提供测评、报告和订单查询接口。

## 目录结构

```text
capital_saas/
├── main.py                 # FastAPI 应用入口
├── requirements.txt
├── .env.example
├── api/                    # 页面路由和 JSON API
├── core/                   # 评分、漏斗、定价、转化引擎
│   ├── lead_scoring_engine.py
│   ├── sales_script_engine.py
│   ├── bank_approval_engine.py
│   └── funnel_analytics.py
├── ai/                     # Mock AI Client 与三类 Agent
├── services/               # 业务服务层
├── db/                     # SQLAlchemy 模型、连接和初始化
│   └── migrations.py       # SQLite 兼容迁移
├── templates/              # Jinja2 页面模板
├── static/                 # CSS 与 JavaScript
└── prompts/                # 后续真实 AI 提示词
```

## 启动方式

建议使用 Python 3.10 或更高版本。

```bash
cd capital_saas
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m db.init_db
uvicorn main:app --reload
```

macOS / Linux：

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m db.init_db
uvicorn main:app --reload
```

访问地址：

- 网站首页：<http://127.0.0.1:8001>
- 管理后台：<http://127.0.0.1:8001/admin>
- 产品中心：<http://127.0.0.1:8001/products>
- 跟进任务：<http://127.0.0.1:8001/admin/follow-tasks>
- 健康检查：<http://127.0.0.1:8001/health>
- API 文档：<http://127.0.0.1:8001/docs>

应用启动时也会自动创建数据库表。`python -m db.init_db` 可用于显式初始化。

## 测试流程

1. 打开首页，点击“开始免费测评”。
2. 填写全部企业信息并提交。
3. 检查免费结果页是否展示评分、等级和风险提示。
4. 点击“解锁完整AI诊断报告 299元”。
5. 在支付页点击“模拟支付并解锁报告”。
6. 检查完整报告是否显示全部 10 个章节。
7. 打开 `/admin`、`/admin/leads`、`/admin/reports`、`/admin/orders` 检查后台数据。
8. 在线索详情页修改跟进状态、下次跟进时间、销售人员和备注。
9. 分别测试以下产品结算地址：
   - `/checkout/{assessment_id}?product=299_report`
   - `/checkout/{assessment_id}?product=699_bank_match`
   - `/checkout/{assessment_id}?product=1999_structure_plan`
10. 可访问以下 JSON API 验证数据：
   - `/api/assessment/{assessment_id}`
   - `/api/report/{assessment_id}`
   - `/api/order/{assessment_id}`

也可以直接运行自动冒烟测试：

```bash
python smoke_test.py
```

验证旧数据库自动迁移：

```bash
python migration_smoke_test.py
```

## Phase 12：安全合规与生产运维加固

Phase 12 增加账号锁定、会话版本、用户管理、操作审计、数据脱敏、上传安全、客户协议授权、公共入口限流、自动备份、健康检查、Worker运行记录、生产检查清单、软删除和合规数据包。

### 账号安全与用户管理

- 默认管理员仍可用 `admin/admin123` 登录，但页面持续提示修改密码；生产环境应在开放访问前完成修改。
- 连续登录失败5次锁定15分钟；成功登录清空失败次数并记录时间和IP。
- `/admin/account/security`：账号安全状态、改密和退出全部会话。
- `/admin/users`：创建、分配角色/组织、启停和重置密码。重置后用户必须修改初始密码。
- 密码变更和退出全部会话会递增 `session_version`，使旧会话失效。

### 审计、脱敏和文件安全

`/admin/audit-logs` 支持按操作人、动作、风险、目标和日期筛选。登录、用户管理、改密、支付、报告审核、上传、备份、法律授权、软删除和合规导出均写入审计日志。

viewer、partner 等非业务负责人在主要列表看到脱敏联系方式；管理员及负责销售可查看授权范围内完整信息。脱敏工具位于 `core/data_masking.py`。

`utils/file_security.py` 同时检查扩展名、MIME、路径字符、单文件大小和单线索总容量。服务器只使用 UUID 保存文件，原文件名仅作为数据库元数据。禁止脚本、网页和可执行文件。

### 隐私协议与客户授权

- `/admin/legal-documents`：维护隐私政策、用户协议、融资免责声明、数据授权和资料提交授权。
- `/client/legal`：客户查看和确认当前有效版本，记录IP、User-Agent和版本。
- 生产环境首次进入门户必须完成用户协议、隐私政策和数据授权；上传资料前必须完成资料提交授权。开发环境显示入口但不阻断旧测试流程。

### 限流、健康检查与运维

生产环境默认启用内存级IP限流，保护登录、测评提交、Token登录、支付、客户上传和公开报告入口。多实例部署时应改用 Redis 或网关限流。

```text
GET /health
GET /healthz
GET /ready
GET /admin/system-health
GET /admin/production-checklist
```

健康接口返回应用版本、数据库、存储、通知Worker和时间戳。生产检查清单提示默认密码、SECRET_KEY、环境、限流、人工审核、法律协议和最近备份风险。

### 备份、恢复和Worker状态

`/admin/backups` 支持创建、校验、下载和删除 SQLite 一致性备份，文件保存在 `data/backups/`。网页不提供恢复按钮；恢复必须停机并由运维人员校验 SHA-256 后执行。

```bash
python scripts/run_notification_worker.py
python scripts/run_reminder_scan.py
python scripts/run_daily_backup.py
```

三个脚本都会写入 `worker_runs`。备份默认保留30天。

### 合规导出与软删除

管理员可访问 `/admin/leads/{lead_id}/compliance-export.zip`，导出线索、测评、报告、订单、资料清单、项目、确认和审计摘要，不包含上传文件本体。客户资料删除采用软删除并要求原因。

### 生产上线前必做

1. 修改管理员密码和 `SECRET_KEY`。
2. 设置 `APP_ENV=production` 并配置 HTTPS 反向代理。
3. 启用报告人工审核、限流和每日备份。
4. 检查隐私协议及授权文本是否符合实际业务与属地法规。
5. 配置日志轮转、监控告警和备份异地保存。
6. 真实支付、邮件、短信或企业微信接入前完成验签、供应商合规和密钥管理。

### Phase 12 验证

```bash
python phase12_smoke_test.py
python migration_smoke_test.py
python scripts/run_daily_backup.py
```

## Phase 10：客户门户与交付协同

Phase 10 为企业客户提供独立于内部后台的服务门户：

- `/admin/client-portals`：按组织权限管理客户门户、任务、消息和确认事项。
- `/client/login-token/{token}`：使用后台生成的专属 Token 登录，默认有效期 7 天。
- `/client/dashboard`：查看已购服务、报告状态、资料完整度、项目阶段、顾问和下一步动作。
- `/client/reports`：仅展示本客户已付款、已解锁且审核通过的报告及打印版。
- `/client/documents`：客户上传资料，自动进入现有文件解析任务和顾问资料中心。
- `/client/tasks`、`/client/messages`、`/client/confirmations`：客户待办、站内消息和带 IP/UA 的服务回执。
- `/client/projects`：以客户友好状态展示融资项目与资金方申请进度，不暴露联系人电话、内部评分、提成或失败原因库。
- `/client/orders`、`/client/upgrade`：查看订单并进入现有 299/699/1999 升级支付流程。

### 客户登录 Token 与安全

后台在线索详情、顾问案件或客户门户详情中开通门户并生成登录链接。后台列表不展示 Token 明文，生成链接只在跳转后的详情页本次展示。Token 过期、客户被停用或客户会话不存在时拒绝访问。

客户会话使用独立 `customer_id`，不会获得后台 `user_id`。报告、资料、任务、消息、确认事项、订单和项目接口均再次校验关联的 `lead_id/assessment_id/customer_id`，防止通过修改 URL 访问其他企业数据。客户页面使用独立 `client_base.html`，不加载后台导航。

### 资料、任务和顾问协同

客户上传沿用后台文件类型和大小限制，保存到 `data/uploads/{lead_id}/`，并记录 `uploaded_source=customer` 和 `customer_id`。上传后自动创建解析任务、刷新资料完整度，并按资料分类完成对应补资料任务。已核验资料客户侧不提供删除入口。

资料完整度不足时系统生成补资料任务；顾问也可手动创建任务、消息和“资料提交授权”等确认事项。报告审核通过、项目状态更新时自动发送客户消息。顾问信息默认只显示用户名、所属组织和平台统一联系方式，个人联系方式需案件显式开启。

### Phase 10 验证

```bash
python phase10_smoke_test.py
python migration_smoke_test.py
```

完整回归需继续运行 `smoke_test.py`、`phase3_smoke_test.py` 至 `phase9_smoke_test.py`。

## Phase 11：客户触达与服务通知自动化

Phase 11 使用数据库任务队列将业务动作与通知发送解耦。报告审核、客户上传资料、资料缺失、项目/资金方状态、待支付订单、升级推荐、任务到期、还款和续贷节点均可创建通知任务；通道失败不会回滚支付、报告或项目主流程。

### 通知中台与模板

- `/admin/notification-templates`：维护受众、通道、服务/营销分类、标题和正文模板，可启停及发送测试。
- `/admin/notification-jobs`：筛选通知任务，立即发送、重试或取消。
- `/admin/notification-dashboard`：查看成功、失败、排队、通道和模板统计。
- `/admin/notifications`：内部用户站内通知及未读状态。
- `/client/preferences`：客户设置站内信、邮件/短信 Mock、勿扰时间和营销退订。

初始化自动预置 15 个服务通知和营销通知模板。模板支持 `{{company_name}}`、`{{task_title}}`、`{{project_name}}` 等变量。模板保存会拦截“包过、保证放款、绝对通过、无视征信、包装资料、伪造流水”等违规表达。

### 通知通道

- `in_app`：客户写入 `customer_messages`，内部用户写入 `internal_notifications`。
- `mock`：只写通知日志，不产生真实外部请求。
- `email`、`sms`、`wecom_webhook`：当前为安全 Mock 适配器，预留合规 SMTP、短信供应商和企业微信群机器人接口；不包含个人微信自动化。

外部邮件/短信内容带退订提示占位。营销通知遵守客户退订设置；项目状态、补资料和确认回执等必要服务通知仍保留站内通知。勿扰时间内任务会顺延到勿扰结束。

### Worker 与提醒扫描

执行到期通知任务：

```bash
python scripts/run_notification_worker.py
```

扫描客户任务、销售跟进、项目贷后还款及续贷任务：

```bash
python scripts/run_reminder_scan.py
```

Linux cron 示例：

```cron
*/5 * * * * cd /opt/capital-saas && /opt/venv/bin/python scripts/run_notification_worker.py
0 * * * * cd /opt/capital-saas && /opt/venv/bin/python scripts/run_reminder_scan.py
```

systemd 可分别创建 oneshot service，并配套 `OnUnitActiveSec=5min` 和 `OnUnitActiveSec=1h` 的 timer。生产环境应避免多个 Worker 重复扫描同一 SQLite 文件；规模扩大后建议迁移 PostgreSQL 和专用队列。

### Phase 11 配置与验证

`.env.example` 已加入 `NOTIFICATION_MODE`、SMTP、短信、企业微信、重试次数和提醒延迟配置。默认全部 Mock，无需外部账号即可运行。

```bash
python phase11_smoke_test.py
python migration_smoke_test.py
```

## Phase 8：融资项目交付与银行对接管理

Phase 8 将尽调和材料包延伸为真实融资项目交付流程：

- `/admin/financing-projects`：融资项目列表、负责人、金额、状态和结果管理。
- `/admin/financing-projects/{id}`：客户、尽调、材料包、资金方申请、审批节点、SOP任务、成本和方案比选。
- `/admin/delivery`：项目状态、批复/放款金额、审批周期、通过率、机构效果和负责人业绩。
- `/admin/success-cases`：默认匿名、内部可见的成功案例库。
- `/admin/rejection-reasons`：从被拒申请自动沉淀的失败原因与改善建议。

### 融资项目管理

可从线索详情、顾问案件或申请材料包一键立项。项目关联线索和测评，可选关联顾问案件和材料包。状态覆盖资料准备、提交、银行审核、补资料、批复、拒绝、放款和归档。

sales 默认只能查看和更新自己负责的项目；viewer 只读；归档及成功案例生成仅 admin 可操作。

### 银行/资金方申请

一个项目可并行维护多个银行、担保、保理、租赁、小贷或其他资金方申请。每个申请独立记录：

- 申请、批复和实际放款金额
- 预计及批复利率
- 期限和还款方式
- 审批状态及关键时间
- 补资料要求、机构联系人、拒绝原因和顾问备注

所有状态变化同时写入项目时间线和全局 `events`。

### 项目SOP与贷后任务

`core/project_sop_engine.py` 根据项目状态生成去重任务。放款后自动生成首月还款、月度计划、贷后资料、续贷前90天、资金用途和现金流复查任务，并在后台首页和交付看板展示。

### 多方案比选与融资成本

`core/financing_offer_compare_engine.py` 按额度、利率、期限、审批稳定性、附加条件和续贷可能性排序已批复方案。

`core/loan_cost_calculator.py` 支持：

- 等额本息
- 等额本金
- 先息后本
- 到期还本付息

结果包含月均还款、总利息、总还款、现金流压力和逐月计划。所有测算仅用于规划，不替代正式合同。

### 项目复盘、成功案例与失败原因

项目关闭后可生成复盘，沉淀审批周期、金额、利率、成功因素、失败原因和可复用案例摘要。成功或部分成功项目可生成默认匿名且不公开的成功案例；被拒申请可自动写入失败原因库。

### Phase 8 验证

```bash
python smoke_test.py
python phase3_smoke_test.py
python phase4_smoke_test.py
python phase5_smoke_test.py
python phase6_smoke_test.py
python phase7_smoke_test.py
python phase8_smoke_test.py
python migration_smoke_test.py
```

## Phase 9：组织复制与多城市运营

Phase 9 将单城市交付流程扩展为总部、分公司、团队和渠道伙伴共同运营的组织体系：

- `/admin/organizations`：维护总部、分公司、团队和渠道伙伴组织树。
- `/admin/channel-partners`：维护伙伴档案、结算方式和专属推广链接。
- `/admin/institution-contacts`：维护银行/资金方联系人、合作等级与历史成功率。
- `/admin/commissions`、`/admin/commission-rules`：提成规则和待确认、已结算记录。
- `/admin/city-dashboard`：城市测评、线索、订单、收入、项目、批复与放款表现。
- `/admin/team-performance`：销售、顾问和渠道贡献及提成预估。
- `/admin/hq-dashboard`：总部跨城市经营总览，仅超级管理员可访问。

### 组织架构与旧数据迁移

初始化时自动创建“沪上银总部”。旧 `admin` 账号继续使用原账号密码登录，并在权限层映射为 `super_admin`。旧用户、线索、订单、顾问案件、融资项目和资金方申请会自动归属总部；迁移只补字段和归属，不删除历史数据。

组织类型支持 `headquarters/branch/team/partner`。分公司可创建销售或顾问团队，用户通过 `org_id` 归属组织；主要业务对象同时保存负责人、归属组织和渠道伙伴，便于跨城市统计。

### 用户角色与数据隔离

支持 `super_admin`、`city_manager`、`sales_manager`、`sales`、`consultant_manager`、`consultant`、`finance`、`viewer`、`partner`。`core/access_scope.py` 根据角色计算组织、用户和伙伴可见范围，并应用于线索、订单、顾问案件、融资项目、任务、销售工作台、交付和增长看板。

- 总部超级管理员可查看全部组织。
- 城市负责人及主管查看本组织和下级团队。
- 销售、顾问查看自己负责的业务。
- 渠道伙伴只查看自己推荐的线索和成交结果。
- 财务聚焦订单、收入、提成和结算；viewer 只读。

组织级 CSV 导出路径为 `/admin/export/organization/{org_id}/{leads|orders|projects|commissions}.csv`，输出 UTF-8-SIG，并在导出前校验组织范围。

### 渠道、联系人和提成

伙伴专属链接示例：`/lp/rongzi?partner=PARTNER001`。系统会将伙伴代码写入会话，并在测评提交时绑定线索；订单、顾问案件和融资项目继续继承归属。支付成功和项目放款会依据启用的规则生成提成记录；伙伴配置为 `per_paid_order` 或 `per_disbursed_amount` 时，也会按伙伴费率生成独立待结算记录。

资金方申请可绑定 `institution_contact_id`。申请批复、拒绝和放款后，联系人成功/拒绝次数随状态沉淀，用于后续资源效果分析。

### Phase 9 验证

```bash
python phase9_smoke_test.py
python migration_smoke_test.py
```

完整回归可依次运行 `smoke_test.py` 与 `phase3_smoke_test.py` 至 `phase9_smoke_test.py`。

Phase 3 专项测试：

```bash
python phase3_smoke_test.py
```

## Phase 2 商业化增强

Phase 2 将原有“测评报告工具”升级为销售与转化系统：

- 测评新增联系人姓名、手机号、微信号和所在城市。
- 提交测评时同步生成企业评分、免费报告、线索评分和销售话术。
- 线索等级分为 S/A/B/C/D，并自动推荐高客单顾问、1999、699、299 或免费培育路径。
- 后台支持按线索等级、跟进状态、推荐产品筛选。
- 订单增加 `product_code`，同一企业可逐级购买不同产品。
- Mock 支付按“企业 + 产品编码”保证幂等，不会重复创建同产品已支付订单。
- 报告页识别已购最高产品，动态展示下一档升级按钮。
- 后台看板展示线索等级、产品订单结构、待联系线索和高价值线索。

### 旧数据库兼容

启动应用或执行 `python -m db.init_db` 时，系统会先通过 SQLAlchemy 创建 Phase 3 新表 `follow_tasks`、`events`，再由 `db/migrations.py` 检查旧表并使用 `ALTER TABLE` 补充历史缺失字段。已有 299 元订单会自动回填为 `299_report`，原有数据不会被删除。

## Phase 3 真实成交增强

- 报告升级为融资顾问口径，年营收、利润、现金流、总负债、短债、应收周期、融资需求、抵押物、征信和纳税都会影响结论。
- `core/bank_approval_engine.py` 以确定性规则模拟银行审批，不构成真实银行授信承诺。
- 创建线索后，根据 S/A/B/C/D 等级自动生成不同节奏和优先级的跟进任务。
- 后台可筛选任务、标记完成或取消，也可在线索详情页新增手动任务。
- `events` 表记录关键行为，用于后续分析转化路径。
- 后台成交漏斗当前按“测评 → 线索 → 付费企业 → 支付订单”统计。
- 完整报告提供 `/report/{assessment_id}/print` 打印页，可使用浏览器“打印 → 保存为PDF”。

### 启用真实 OpenAI

默认无需 API Key，系统使用 Mock 和确定性规则引擎：

```env
AI_MODE=mock
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
```

如需启用真实模型，在本地 `.env` 中配置：

```env
AI_MODE=openai
OPENAI_API_KEY=你的本地API密钥
OPENAI_MODEL=gpt-4.1-mini
```

`ai/ai_client.py` 使用 OpenAI Responses API，并要求返回 JSON。密钥缺失、网络错误、模型错误或 JSON 解析失败时会自动回退 Mock，不影响测评、支付和报告主流程。不要将 `.env` 提交到版本库。

## Phase 4 生产上线与真实收款准备

Phase 4 增加了：

- Session Cookie 后台登录和 PBKDF2 密码哈希。
- `admin`、`sales`、`viewer` 三类角色权限。
- 系统配置中心，可动态调整产品价格、AI模式、模型和支付模式。
- `mock`、`manual_transfer`、`wechat_pay`、`alipay` 四种支付模式。
- pending、paid、failed、cancelled、refunded 订单状态。
- 后台订单详情、人工确认支付、退款和取消。
- 完整报告、打印报告和 JSON 报告的支付访问控制。
- 7天有效的客户公开报告链接。
- 线索、订单、跟进任务 CSV 导出。
- 最近7天趋势、产品收入、任务和事件运营看板。
- Docker、Gunicorn、Nginx 和 systemd 部署示例。
- 启动、支付、AI降级、报告拒绝访问和后台操作日志。

### 登录说明

首次初始化会自动创建默认管理员：

```text
用户名：admin
密码：admin123
```

打开 <http://127.0.0.1:8001/login> 登录。

**生产上线后必须立即进入 `/admin/settings` 修改默认密码，同时修改 `.env` 中的 `ADMIN_DEFAULT_PASSWORD`，防止数据库被重建时再次生成弱密码。**

角色权限：

- `admin`：查看和修改全部数据、订单、任务、配置及导出。
- `sales`：查看后台、线索、任务和报告，可更新线索和任务。
- `viewer`：只读查看后台、线索、任务、报告和订单。

### 本地启动

```powershell
Copy-Item .env.example .env
pip install -r requirements.txt
python -m db.init_db
uvicorn main:app --reload
```

至少修改以下生产配置：

```env
APP_ENV=production
SECRET_KEY=请替换为足够长的随机字符串
ADMIN_DEFAULT_PASSWORD=请替换为强密码
SITE_BASE_URL=https://你的域名
```

如果 `SECRET_KEY` 仍为默认值，启动日志会输出安全警告。

### Docker 启动

先创建生产 `.env`：

```bash
cp .env.example .env
```

修改密钥、管理员密码和域名后启动：

```bash
docker compose up -d --build
```

SQLite 数据保存在 Docker 卷的 `/app/data/capital_saas.db`，日志保存在 `/app/logs`。

查看日志：

```bash
docker compose logs -f capital-saas
```

### 支付模式

可通过 `.env` 的 `PAYMENT_MODE` 设置初始模式，也可以登录 `/admin/settings` 动态修改：

```env
PAYMENT_MODE=mock
```

- `mock`：立即模拟支付成功并解锁报告。
- `manual_transfer`：生成待支付订单，展示转账说明，由管理员在订单详情手动确认。
- `wechat_pay`：预留微信支付下单和 webhook，尚未实现签名与真实扣款。
- `alipay`：预留支付宝下单和 webhook，尚未实现签名与真实扣款。

真实支付上线前必须完成 webhook 验签、金额校验、商户校验、幂等处理和退款接口，不应直接使用当前预留回调确认付款。

### 配置真实 AI

```env
AI_MODE=openai
OPENAI_API_KEY=你的API密钥
OPENAI_MODEL=gpt-4.1-mini
```

也可以在配置中心修改 `ai_mode` 和 `openai_model`。API Key 只从环境变量读取，不保存在数据库。真实AI调用失败会自动回退 Mock。

### 修改默认管理员密码

1. 使用 `admin/admin123` 登录。
2. 进入 `/admin/settings`。
3. 在“修改管理员密码”区域输入当前密码和至少10位的新密码。
4. 更新服务器 `.env` 中的 `ADMIN_DEFAULT_PASSWORD`。

### 生产部署建议

- 使用 Nginx 终止 HTTPS，再反向代理到 Gunicorn。
- 参考 `deploy/capital-saas.conf.example` 和 `deploy/capital-saas-backend.service.example`。
- 生产环境不要直接暴露 Uvicorn reload 服务。
- 定期备份 `/app/data/capital_saas.db`；业务增长后迁移至 PostgreSQL。
- 将支付API密钥、OpenAI密钥和 SECRET_KEY 放入受控的密钥管理系统。
- 配置防火墙、限流、监控、日志轮转和异地备份。

### Phase 4 验证

```bash
python smoke_test.py
python phase3_smoke_test.py
python phase4_smoke_test.py
python migration_smoke_test.py
```

### 常见问题

- 登录后仍回到登录页：检查浏览器是否允许 Cookie；生产环境需要通过 HTTPS 访问安全 Cookie。
- 启动提示默认 SECRET_KEY：修改 `.env` 后重启服务。
- 人工转账后报告未解锁：管理员需在订单详情点击“手动标记已支付”。
- 公开报告链接无法打开：检查订单是否仍为 paid，以及7天有效期是否已过。
- OpenAI调用失败：系统会回退 Mock；检查 API Key、模型权限、网络和额度。
- Docker 中数据库为空：确认 `DATABASE_URL=sqlite:////app/data/capital_saas.db` 且数据卷已正确挂载。

## Phase 5 真实运营增长

Phase 5 将获客来源、销售动作和付费结果串成完整增长链路：

- 自动采集 UTM、渠道、活动、关键词和落地页来源。
- 四套独立投放落地页。
- 免费结果页 A/B 转化实验。
- 按销售人员分配的销售工作台。
- 线索跟进时间线与下一步最佳动作。
- 可管理、可匹配、可一键复制的微信销售话术库。
- 渠道、落地页、产品、线索等级和 A/B 实验增长分析。
- 自动客户标签与标签筛选。
- SQLite 原始备份及不含密码哈希/密钥的业务数据 ZIP。
- 开发环境测试数据清理。

### 渠道追踪

支持以下参数：

```text
utm_source
utm_medium
utm_campaign
utm_content
utm_term
channel
campaign
keyword
```

示例：

```text
http://127.0.0.1:8001/?utm_source=douyin&utm_medium=cpc&utm_campaign=rongzi_test
```

参数会写入 Session，并在提交测评后保存到 `assessments`、`leads`，支付后保存到 `orders`，相关事件也会携带来源字段。

### 投放落地页

- `/lp/rongzi`：企业融资测评
- `/lp/cashflow`：现金流风险测评
- `/lp/bank`：银行贷款通过率测评
- `/lp/boss`：老板财商诊断

可以直接添加 UTM 参数：

```text
/lp/bank?utm_source=baidu&utm_medium=cpc&utm_campaign=bank_approval
```

### A/B测试

默认实验为 `free_result_conversion`：

- `variant_a`：风险提示型
- `variant_b`：机会收益型

系统按访客 Session 随机分配，并关联测评和线索。后台 `/admin/ab-tests` 展示分配人数、支付人数、转化率和收入。

### 销售工作台

访问 `/sales/workbench`：

- admin 查看全部线索。
- sales 只查看 `assigned_sales_id` 分配给自己的线索和任务。
- 展示今日任务、逾期任务、高价值线索、最近付款客户和最佳联系建议。

在线索详情页可以分配销售、更新状态、添加备注、管理标签、查看跟进时间线和复制话术。

### 下一步最佳动作

`core/next_best_action_engine.py` 会结合：

- 线索等级
- 跟进状态
- 已购产品
- 任务状态
- 最后活动时间

推荐立即电话、推299、推699、推1999、顾问服务或7天重新激活。

### 微信话术模板

后台 `/admin/script-templates` 提供预置场景：

- 初次加微信
- 免费测评后未支付
- 推299/699/1999
- 高客单顾问
- 24小时未回复
- 7天重新激活
- 已支付感谢
- 升级服务推荐

管理员可新增、编辑、启用或停用；销售在线索详情页和工作台一键复制。

### 运营增长看板

访问 `/admin/growth` 查看：

- 渠道测评、线索、订单、收入、转化率和客单价
- 四套落地页效果
- 产品收入
- S/A/B/C/D 转化
- A/B实验
- 最近7天趋势

### 数据备份

仅 admin 可访问 `/admin/backup`：

- `/admin/backup/database`：下载完整 SQLite 数据库。
- `/admin/backup/business-zip`：下载 leads、orders、reports、follow_tasks、events CSV。

业务 ZIP 不包含 `users` 表、密码哈希和环境变量密钥。

### development / production

```env
APP_ENV=development
```

开发环境会在 `/admin/backup` 显示“清理测试数据”按钮。

生产环境：

```env
APP_ENV=production
```

生产环境禁止调用测试数据清理接口。

### Phase 5 验证

```bash
python smoke_test.py
python phase3_smoke_test.py
python phase4_smoke_test.py
python phase5_smoke_test.py
python migration_smoke_test.py
```

## Phase 6：真实 AI 顾问能力

Phase 6 将完整报告升级为可审核、可追溯、可分层交付的顾问报告系统：

- `ai/pipelines/` 按10个章节分别生成，执行上下文整理、章节生成、质量检查、最多两次重写和 Mock 降级。
- `prompts/report_sections/` 为每章维护独立 Prompt，统一要求严格 JSON、银行视角、老板动作、风险提示与合规边界。
- `core/report_quality_engine.py` 从数据引用、银行专业度、可执行性、风险、个性化和合规性六维评分；低于70分自动补强。
- 每次完整报告生成都会保存到 `report_versions`，后台支持查看、切换当前版本和重新生成，旧版本不会丢失。
- 可通过 `REPORT_REVIEW_REQUIRED` 或系统配置开启人工审核；生产环境建议开启。admin 可通过或驳回，sales/viewer 只读。
- 银行产品规则库位于 `/admin/bank-products`，预置6类模拟产品，不代表任何真实银行承诺。
- 699版本提供完整银行匹配和申请顺序；1999版本增加三阶段融资结构、完整资料清单与30/90/180天执行计划。
- 购买1999或在线索中标记“高客单意向”会自动创建顾问交付案件，入口为 `/admin/consulting-cases`。
- 客户资料入口为 `/admin/leads/{lead_id}/documents`，默认保存在 `data/uploads/`，仅允许 PDF、Office 文档和图片，默认单文件20MB。
- 每个章节生成均写入 `ai_generation_logs`；Mock、真实AI成功、失败降级都会留痕。

### 启用真实 AI

默认无需 API Key，系统使用稳定的规则报告：

```env
AI_MODE=mock
```

启用 OpenAI 时：

```env
AI_MODE=openai
OPENAI_API_KEY=你的密钥
OPENAI_MODEL=gpt-4.1-mini
```

真实调用失败、JSON结构不完整或质量不足时会自动回退/补强，不影响支付与报告主流程。不要把真实密钥提交到代码仓库。

### 人工审核与上传配置

```env
REPORT_REVIEW_REQUIRED=false
UPLOAD_MAX_MB=20
```

开发环境默认关闭强制审核；生产环境建议设置为 `true`。公开报告链接始终要求报告状态为 `approved`。

### 合规声明

支付页、完整报告、打印版和公开报告均展示：报告仅用于企业融资规划参考，不构成贷款、授信、投资或法律承诺，实际结果以金融机构审批为准。系统 Prompt 明确禁止伪造材料、违规融资、保证额度、保证利率或“包过”承诺。

### Phase 6 验证

```bash
python smoke_test.py
python phase3_smoke_test.py
python phase4_smoke_test.py
python phase5_smoke_test.py
python phase6_smoke_test.py
python migration_smoke_test.py
```

## 配置

如需覆盖默认配置，将 `.env.example` 复制为 `.env`：

```powershell
Copy-Item .env.example .env
```

默认数据库为项目目录下的 `capital_saas.db`，报告价格为 299 元。

## 后续接入真实 AI

1. 在 `ai/ai_client.py` 中将 `generate_json()` 替换为真实模型调用。
2. 从 `prompts/` 加载对应提示词，并要求模型返回结构化 JSON。
3. 保留 `core/scoring_engine.py` 作为确定性评分来源，避免模型随机改变核心分数。
4. 在 `.env` 配置 `OPENAI_API_KEY` 和模型名。
5. 为模型输出增加 JSON Schema 校验、超时、重试、内容安全和降级逻辑。

## 后续接入真实支付

1. 新增支付平台下单接口，订单初始状态设为 `pending`。
2. 跳转支付前保存平台订单号。
3. 使用支付平台的服务端异步回调确认支付结果。
4. 验证签名、金额、商户号和订单状态后，再将订单更新为 `paid`。
5. 支付成功后的报告生成应使用任务队列，并保证幂等。
6. 生产环境不得以前端跳转结果作为支付成功依据。

## 上线前建议

- 为管理后台增加登录、角色和权限控制。
- 从 SQLite 升级到 PostgreSQL。
- 增加 CSRF、防刷、限流、日志、监控和数据备份。
- 对企业敏感数据进行加密与隐私合规处理。
- 对融资相关结论增加人工复核和合规免责声明。

## Phase 7：企业资料智能解析与融资尽调

Phase 7 将客户资料从单纯文件存储升级为可解析、可核验、可追踪的融资尽调链路：

- 企业资料中心：`/admin/leads/{lead_id}/document-center`
- 融资尽调底稿：`/admin/leads/{lead_id}/due-diligence`
- 测评补全审核：`/admin/leads/{lead_id}/autofill-review`
- 融资申请材料包：`/admin/leads/{lead_id}/application-package`

### 企业资料中心

支持批量上传、自动分类、人工分类、备注、SHA-256重复文件提示、解析状态和核验状态。文件按线索保存到：

```text
data/uploads/{lead_id}/
```

重复文件只提示、不强制禁止。admin 可核验、驳回和删除；sales 可查看、上传和重新解析；viewer 只读。

### 文件解析范围

- Excel：使用 `openpyxl` 读取工作表和前50行，识别营业收入、净利润、总资产、总负债、现金流、应收账款、短期/长期借款和纳税金额。旧版 `.xls` 需另存为 `.xlsx`。
- Word：使用 `python-docx` 提取 `.docx` 段落和表格；旧版 `.doc` 需转换后解析。
- PDF：使用 `pypdf` 提取文本。扫描件或无法提取文本的 PDF 会标记为需要 OCR。
- 图片：当前仅保存并返回 `pending_ocr`，不强制配置 OCR 服务。

上传后会创建 `document_parse_tasks`。解析失败会记录错误、事件并生成“人工核验资料”跟进任务，不影响文件保存和其他业务流程。

### 资料完整性与尽调

`core/document_completeness_engine.py` 根据信用贷、抵押贷、供应链融资及产品等级检查资料完整度。高客单或1999案件低于70分时，会自动生成营业执照、银行流水、纳税资料和抵押物资料收集任务。

尽调底稿汇总：

- 测评数据与企业基础信息
- 上传资料及解析字段
- 资料完整度和缺失清单
- 财务数据冲突
- 现金流、短债、征信、纳税、抵押物和应收风险
- 顾问备注及审核状态

尽调后会自动添加“资料不完整”“需人工尽调”等风险标签。

### 测评数据补全

系统只生成建议，不会直接覆盖测评数据。管理员可逐字段确认应用，并重新计算企业评分；操作会写入 `events` 和线索跟进日志。

### 融资申请材料包

顾问可选择目标银行产品、勾选已有资料、查看缺失清单并生成材料包。材料包支持 `draft/ready/submitted/returned/archived` 状态及 UTF-8-SIG CSV 清单导出。

### 文件限制与安全

- 允许：PDF、DOC/DOCX、XLS/XLSX、PNG、JPG/JPEG。
- 默认单文件上限20MB，可通过 `UPLOAD_MAX_MB` 调整。
- 文件名不会直接作为磁盘文件名，系统使用随机UUID保存。
- 生产环境应增加恶意文件扫描、对象存储、静态文件隔离、传输加密和敏感资料访问审计。
- SQLite 数据备份不应通过公开链接传播，上传目录应单独加密备份。

### Phase 7 验证

```bash
python smoke_test.py
python phase3_smoke_test.py
python phase4_smoke_test.py
python phase5_smoke_test.py
python phase6_smoke_test.py
python phase7_smoke_test.py
python migration_smoke_test.py
```
## Phase 13：生产发布与商用试运营

Phase 13 将系统从“生产准备版”升级为“可灰度试运营、可正式发布”的版本，新增环境配置分层、上线检查脚本、发布/回滚脚本、初始化向导、试运营访问码、上线看板、Nginx/HTTPS/systemd 示例、SQLite 到 MySQL/PostgreSQL 迁移预留、SEO 与公开法律页面。

### 环境配置分层

新增 `config/`：

- `config/development.env.example`：SQLite、Mock 支付、Mock 通知、Mock AI、宽松限流。
- `config/staging.env.example`：可开启报告审核和真实 AI，限流更严格。
- `config/production.env.example`：要求非默认 `SECRET_KEY`、开启限流/审计/备份，建议开启报告审核。

加载顺序：系统先根据 `APP_ENV` 加载 `config/{APP_ENV}.env`，再用根目录 `.env` 覆盖。生产建议从 `config/production.env.example` 复制为 `.env` 后逐项修改。

### 生产发布流程

```bash
pip install -r requirements.txt
python scripts/init_production_data.py
python scripts/preflight_check.py
uvicorn main:app --host 127.0.0.1 --port 8000
```

上线前必须处理 `preflight_check.py` 中的 `FAIL` 项，`WARNING` 项需要确认负责人和风险接受结论。

### Preflight / Release / Rollback

```bash
python scripts/preflight_check.py
python scripts/release_check.py
python scripts/rollback_check.py
```

- `preflight_check.py`：检查密钥、默认管理员、数据库、上传/备份/日志目录、法务文档、组织、通知模板、银行产品、高风险审计等。
- `release_check.py`：发布前阻断 FAIL 项。
- `rollback_check.py`：展示最近备份并提示回滚文档。

### Setup Wizard

后台访问：

```text
/admin/setup-wizard
```

用于逐项完成公司信息、管理员密码、域名、产品价格、支付、AI、通知、法务、组织、渠道、银行产品和备份策略。

### 灰度试运营模式

配置：

```env
TRIAL_MODE=true
TRIAL_ACCESS_CODE=your-code
TRIAL_ALLOWED_IPS=127.0.0.1,1.2.3.4
```

开启后，公开 `/assessment` 需要访问码或白名单 IP。后台和客户门户不受影响。默认关闭。

### Nginx / HTTPS 部署

参考：

- `deploy/capital-saas.conf.example`
- `deploy/ssl_guide.md`

模板包含 HTTP 自动跳转 HTTPS、静态文件缓存、上传大小限制、安全响应头、gzip 和 `/health` 访问日志控制。

### systemd / Worker / Timer

参考：

- `deploy/capital-saas-backend.service.example`
- `deploy/notification_worker.service.example`
- `deploy/reminder_scan.service.example`
- `deploy/reminder_scan.timer.example`
- `deploy/daily_backup.service.example`
- `deploy/daily_backup.timer.example`

启用示例：

```bash
sudo cp deploy/*.example /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now capital_saas
sudo systemctl enable --now notification_worker
sudo systemctl enable --now reminder_scan.timer
sudo systemctl enable --now daily_backup.timer
```

### SQLite 到 MySQL/PostgreSQL 迁移预留

试运营可继续使用 SQLite：

```env
DATABASE_URL=sqlite:///data/app.db
```

正式多城市运营建议切换：

```env
DATABASE_URL=mysql+pymysql://user:password@host:3306/capital_saas?charset=utf8mb4
DATABASE_URL=postgresql+psycopg2://user:password@host:5432/capital_saas
```

基础配置数据导出/导入：

```bash
python scripts/export_sqlite_data.py
python scripts/import_seed_data.py
```

当前版本不自动迁移历史业务数据到 MySQL/PostgreSQL；建议先导出基础配置，再通过数据库工具迁移业务表并做验收。

### 上线看板与发布说明

后台访问：

- `/admin/launch-dashboard`：上线第一周盯盘，看今日测评、线索、订单、收入、客户登录、上传、通知、错误、限流、Worker 与备份状态。
- `/admin/release-notes`：查看版本、启动时间、路由数量、Git commit 与 CHANGELOG。
- `/admin/production-checklist`：分组上线检查。

### Demo 数据与压测

仅 development/staging 允许：

```bash
python scripts/create_demo_data.py
python scripts/clear_demo_data.py
```

基础压测：

```bash
python scripts/basic_load_test.py --base-url http://127.0.0.1:8001 --concurrency 5 --requests 50
```

### SEO 与公开法律页面

新增：

- `/robots.txt`
- `/sitemap.xml`
- `/legal/privacy`
- `/legal/terms`
- `/legal/disclaimer`
- `/legal/data-authorization`

公开页面底部已加入隐私政策、用户协议、免责声明、数据授权说明入口。

### 上线第一周运营建议

1. 每天检查 `/admin/launch-dashboard` 和 `/admin/system-health`。
2. 每天确认自动备份是否成功。
3. 每天查看 `notification_jobs` 失败原因。
4. 每天复盘渠道来源、落地页转化、报告支付转化。
5. 小流量试运营建议先开启 `TRIAL_MODE`，稳定后逐步放开。

## Phase 14：真实试运营作战台与首批客户验证

Phase 14 面向首批 20-50 个真实客户试运营，核心是看清每个客户卡在哪一步，沉淀客户反馈、Bug、需求和每日/每周复盘。

### 试运营批次

后台入口：

```text
/admin/pilot-batches
/admin/pilot-dashboard
```

支持创建批次、设置目标客户数/付费数/收入/资料上传数/项目数，批次状态包括 planning、running、paused、completed、archived。

### 首批客户管理

线索新增试运营字段：

- `pilot_batch_id`
- `pilot_stage`
- `pilot_note`

阶段包括：

- invited
- assessed
- paid
- report_viewed
- documents_uploaded
- consulting_started
- project_created
- dropped
- completed

线索详情页会显示试运营阶段、SOP建议和客户旅程入口。

### 邀请链接

批次详情页可生成邀请码，示例：

```text
/lp/rongzi?pilot=CODE123
```

用户通过该链接提交测评后，会自动绑定对应试运营批次，并记录 `pilot_invite_used` 事件。

### 客户反馈

客户门户入口：

```text
/client/feedback
```

后台入口：

```text
/admin/feedback
```

反馈类型包括报告质量、支付问题、资料上传、项目进度、顾问服务、使用体验等。后台可处理反馈，并一键转为 issue。

### Bug / 需求池

后台入口：

```text
/admin/issues
```

支持 bug、feature_request、data_issue、payment_issue、report_issue、operation_issue，严重度 low/medium/high/critical。高优先级问题会进入 pilot dashboard 和 launch dashboard。

### 日报 / 周报

后台入口：

```text
/admin/daily-reports
/admin/weekly-reports
```

日报按日期汇总访问、测评、线索、付费、收入、资料上传、项目立项、反馈和问题。

周报汇总一周转化、客户反馈、问题池和最大掉点，并给出下周优化建议。

### 漏斗掉点分析

新增 `core/dropoff_analysis_engine.py`，分析阶段：

1. landing_view
2. assessment_submitted
3. free_result_viewed
4. checkout_viewed
5. payment_success
6. report_viewed
7. document_uploaded
8. consulting_case_created
9. financing_project_created

输出最大掉点、掉点率、可能原因和推荐动作。

### 试运营 SOP

新增 `core/pilot_sop_engine.py`，根据客户阶段生成：

- 下一步动作
- 负责人角色
- 优先级
- 建议话术
- 风险提示

可在线索详情页和试运营作战台使用。

### 客户旅程

入口：

```text
/admin/leads/{lead_id}/journey
```

按时间线查看访问、测评、支付、报告、客户门户、资料上传、反馈、通知和项目事件。

### 试运营导出

入口：

```text
/admin/pilot-batches/{batch_id}/export.csv
```

导出企业名称、联系人、手机号、渠道、当前阶段、已购产品、订单金额、是否上传资料、是否立项、反馈评分、负责人和下一步动作。

### 首批 20-50 个客户试运营建议

1. 建议每个批次 20-50 个客户，不要一开始放太大流量。
2. 每天看 `/admin/pilot-dashboard`，优先处理支付、资料上传、报告查看三个卡点。
3. 每天生成一次日报，每周生成一次周报。
4. 所有客户反馈都要归类，能转 issue 的当天转。
5. 第一周看流程是否跑通，第二周看付费和上传资料转化，第四周看项目立项和复购/升级。

## Markdown 银行产品库导入

如果你的银行产品库是 .md 格式，可以直接上传。

后台进入 `/admin/bank-products`，点击“导入产品库”。系统同时支持 `.csv`、`.xlsx` 和 `.md`，Markdown 可以使用以下两种格式。

1. Markdown 表格

```markdown
| 银行/机构 | 产品名称 | 产品类型 | 城市 | 额度 | 利率 | 期限 |
| --- | --- | --- | --- | --- | --- | --- |
| 建设银行 | 税贷 | 信用贷 | 上海 | 10-300万 | 3.8%-6.0% | 12个月 |
```

2. Markdown 标题和字段

```markdown
## 建设银行 - 税贷
产品类型：信用贷
城市：上海
额度：10万-300万
利率：3.8%-6.0%
期限：12个月
准入条件：纳税正常、征信正常
所需资料：营业执照、纳税记录、银行流水
```

完整模板位于 `data/import_templates/bank_products_template.md`。相同“银行/机构 + 产品名称 + 城市”会更新已有记录；导入记录的 `data_source` 为 `imported`。
