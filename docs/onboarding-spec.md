# 新用户引导（First-run onboarding）

目标：**新用户 15 分钟内拿到第一份真实的 pass/fail 报告**。不是教完所有功能，是把
"部署好了 → 第一条绿/红" 这条主线上的每一个卡点各安排一个出口。

## 0. 两类新用户

| 类型 | 起点 | 需要的引导 |
|------|------|-----------|
| **A. 建项目的人**（admin / 第一个用的人） | 空库，什么都没有 | 全流程：项目 → 登录态 → 用例 → 跑 → 读报告 |
| **B. 被邀请的成员** | 项目已经有用例和历史 run | 只需要：这页是什么 + 怎么跑 + 怎么读报告 |

B 走的是 A 的子集，所以只设计一条线，靠"状态派生"自动跳过已完成的步骤——B 进来时清单
已经全绿，卡片自己就不显示了。

## 1. 主线（happy path）

```
登录/接受邀请
  └─ 建项目（名称 + Base URL）
       └─ 抓登录态（用户名/密码 → storage_state，healthy ✅）   ← 内网系统必过
            └─ 有第一条用例（样例 / 手写 / xlsx 导入）
                 └─ 跑第一次（单条用例，不是整套）
                      └─ 读报告（视频 + 步骤 + judge 判定理由）
                           └─ 失败 → 一键转 Issue ／ 全绿 → 建套件 + 定时
```

七步里真正的卡点只有三个：**登录态**（内网系统不登录寸步难行）、**用例怎么写**
（judge 证据不足默认判 failed，是最容易踩的坑）、**首跑很慢**（真实浏览器 + 录像，
用户会以为卡死）。引导的全部预算都花在这三处。

## 2. 实现（五个部件，不引入 tour 库）

明确不做 driver.js / shepherd 那种高亮遮罩导览：UI 一改选择器就断，维护成本长期存在，
换来的只是一次性的观感。改用下面这些一直有用的东西。

### A. 状态派生的 Setup checklist（Overview 顶部）

五项，**全部从已有数据算出来**，不存任何"用户已完成引导"的标记——所以没有 dismiss、
没有重置、没有和真实状态不一致的 bug。五项全绿时卡片自动消失。

| 项 | 判据 | CTA |
|----|------|-----|
| 1. 设置 Base URL | `project.base_url` 非空 | → Settings |
| 2. 配置一个可用账号 | 存在 `healthy === true` 的 credential | → Settings › Credentials |
| 3. 添加第一条用例 | `stats.case_count > 0` | → Cases（新建 / 导入） |
| 4. 跑第一次 | `stats.run_count > 0` | → Cases，选中一条 → Run |
| 5. 处理第一个失败 | 最近一次 run 全绿 **或** 项目下有 issue | → Runs › 最近报告 |

后端：`GET /projects/{pid}/stats`（`app/api.py:885`）加两个布尔
`has_credential` / `has_healthy_credential`（一条 count 查询），前端一个请求就够，
不新增端点。

第 5 项刻意不是"看过报告"——那需要存浏览记录。改成"这个项目已经产生过结论"，
既可算又更有意义。

### B. 建项目向导（3 步，替换现在的两字段 Modal）

`pages/Projects.tsx` 现在是 name + base_url 一个 Modal 就建完，用户建完项目落在一个
全空的 Overview 上，不知道下一步。改成三步：

1. **项目** — 名称、Base URL
2. **登录账号** — 用户名 / 密码 → 复用 `api.captureCredential` + `CaptureProgressModal`；
   显式的"公开站点，跳过"按钮（不要藏起来）
3. **起步用例** — 三选一，默认第一个：
   - ☑ 生成 1 条冒烟用例（prompt: `打开 {base_url}，确认首页加载完成`；
     expected: `页面主要内容渲染出来，没有报错页/空白页`）— 让用户第一次 Run 有东西可跑
   - 导入 xlsx（`api.templateUrl` 下模板 → `api.importCasesXlsx`）
   - 稍后自己写

完成后直接跳 Cases 页，样例用例在列表里，"运行"按钮是这页的主行动。

### C. 空态即教学

`components/feedback.tsx` 的 `Empty` 已经支持 title / sub / action，把每个空态写成
"一句话说明这页是什么 + 一个主 CTA"（现在只有 Compare 和 Overview 写了）：

- **Cases 空** — "用例 = 一段自然语言任务 + 一条判定标准。Agent 会照着在真实浏览器里做。"
  → 新建用例 · 下载 xlsx 模板
- **Runs 空** — "一次 run 批量执行用例，产出视频、步骤轨迹和 pass/fail。" → 去 Cases 跑一条
- **Suites 空** — "套件 = 一组用例 + 负责人 + 定时，用来做回归。" → 新建套件
- **Issues 空** — "报告里的失败可以一键转成 Issue，配置了 GitLab 会同步过去。" → 去看最近报告

### D. 用例写作提示（最关键的一处教学）

`judge.py` 在证据不足时**默认判 failed**，所以 expected 写得糊 = 无脑挂。这不是文档能
解决的，得在写用例的地方顶着说。

`CaseDrawer.tsx` 在该项目 `case_count === 0` 时，顶部常驻一条三行提示（不可关闭，
第二条用例起不再出现）：

- **Agent task**：像给新同事交代任务一样，一步一步写（"登录后进采购 › 询价，新建一条询价单"）
- **Expected outcome**：写"看到什么才算过"。judge 只看证据，说不清就判失败
- **Runs as**：选角色 = 选用哪个账号执行

两个字段的 placeholder 一并给成真实例子，而不是 `https://…` 这种占位。

### E. 首跑体验

`RunReport` 已有 SSE 流式，补两处：

- 运行中顶部一条 hint：**"首次运行较慢：要拉起真实浏览器并录像，单条用例约 30–90 秒。"**
  （不加这句，用户会以为卡死然后刷新）
- 结束态分岔：
  - 全绿 → 成功卡片 + 下一步："把这些用例存成套件，设个每日定时"
  - 有失败 → 指向"看录像回放"和"转成 Issue"两个动作，而不是让用户自己找

## 3. 验收

不接分析平台，两个指标就够，都能从库里直接查：

- 项目创建 → 第一次 `completed` run 的中位耗时 **< 15 分钟**
- 存在 ≥1 条用例的项目里，checklist 五项全绿的占比

## 4. 明确不做（YAGNI）

- 产品导览 / 高亮遮罩库 —— UI 一改就断，维护成本 > 收益
- 帮助中心、视频教程 —— 等真的有人问同一个问题三次再说
- `onboarding_progress` 之类的表字段 —— 状态派生已经够，加了就得维护一致性
- 交互式 sandbox / demo 项目 —— 样例冒烟用例已经覆盖"有东西可跑"这个需求

## 5. 落地情况（全部已实现）

| 部件 | 代码 |
|------|------|
| A 清单卡 | `web/src/components/SetupChecklist.tsx`，挂在 `OverviewPage`；字段来自 `app/api.py` `project_stats` |
| B 建项目向导 | `web/src/components/NewProjectWizard.tsx`，`Projects.tsx` 的「新建项目」入口全部指向它（旧 Modal 只留给编辑） |
| C 空态教学 | `Projects`（无项目时的欢迎屏）·`CasesPage`·`RunsPage`·`SuitesPage` |
| D 用例写作提示 | `CaseDrawer` 的 `firstCase` 分支 + prompt/expected 的真实示例 placeholder |
| E 首跑体验 | `RunReport`：运行中「还没结果是正常的」提示 + 结束后按全绿/有失败分岔的下一步卡 |

回归检查：`tests/test_stats_checklist.py`（清单字段的三态 + 向导 happy path 的 HTTP 序列）。

Issues 看板没有加页面级说明——它的分列空态本身就自解释，清单第 5 项也已经指向它。
