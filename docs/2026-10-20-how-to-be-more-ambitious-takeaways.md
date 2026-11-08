# 从「修这个 bug」到「让它不再出错」

> 读 Felix Rieseberg, *[How to be more ambitious: A tutorial for humans with models](https://felixrieseberg.com/how-to-be-more-ambitious-a-tutorial-for-humans-with-models/)*（2026-10-13，Anthropic EM，Claude Code Desktop 负责人）
> 结合本仓库（WheatOmics FastAPI 后端）与我们的 AI 工作流做的盘点与启发
> 2026-10-20

## 0. 一句话

这篇文章不是教「怎么写出更花的提示词」，而是教你**换目标层级**；而换层级的前提是——**先给模型造一个能自己判对错的环境**。我们的 speed 轴已经很强，卡住的是 altitude / depth / range，根因不是模型能力，是**没有裁判**。

---

## 1. 原文可操作版

作者把「用模型的野心」拆成四个方向。Speed（同样的事更快做完）是经济学价值的主战场，但他直接跳过；真正要练的是另外三个：

| 方向 | 一句话 | 自问 |
|---|---|---|
| **Altitude 高度** | 从「一个任务」上升到「一个结果」 | 这件事做完之后，我希望**接下来**发生什么？ |
| **Depth 深度** | 按领域顶尖专家的方式做，摸到原始数据与工具 | 顶尖的人会用什么仪器、从什么原材开始？ |
| **Range 广度** | 借其他学科的做法，用原先不划算的多学科视角 | 换个领域的人会怎么处理这个目标？ |

原文里两个可以直接拿走用的东西：

**① 深度改写提示词（作者原话，中译）**

> 我要的是这个任务的**更深版本，不是更大版本**。改写之前先回答：(1) 这个领域的顶尖专家在这里会做什么、而我没要求的事？(2) 他们真正会从哪种**最原始的材料**开始，而不是别人替我消化好的成品？(3) 他们会用哪些具体方法和工具？(4) 除了你和我，**还有什么能证明结果是对的**？然后再把我的提示词改写成恰好要这些。

**② 外部裁判**

> 不要（在 2026 年 10 月）让模型评判它自己。坚持外部验证，最好是一个模型能自己运行、立刻拿到反馈的工具。

还有一句最容易被忽略、但对我们最要命：**这些野心都需要「改环境」，而不只是改提示词**。作者为了让 Claude 把应用做到「不再崩溃」，先去打通了三件事：崩溃报告可拉取、版本号能映射到 git commit、有 Windows/macOS/Linux 机器可以复现。

文章后半段讲「人类一直被自己相信的可能性限制」：自我效能（self-efficacy）、Locke & Latham 的具体困难目标研究、Dantzig 误把未解难题当作业、四分钟一英里。这部分是动机论，当背景看即可，别当证据用（见 §4）。

---

## 2. 我们的坐标（带证据）

| 观察 | 数字/证据 | 说明 |
|---|---|---|
| 模型已是主要产出者 | 全库 799 个 commit，**401 个**带 `Co-Authored-By: Claude` | speed 轴早就不是问题 |
| 但工作在「一个 fix 接一个 fix」 | 最近 300 条：**129 个 fix** / 97 个 feat；2026-09-28 **一天 7 个 commit** 全在修同一张表达谱图的标签（`a995e9f`…`3e6b218`） | 每个 commit 都对，整体不收敛——典型 altitude 缺失 |
| 没有自动裁判 | 无 `tests/`、无 pytest/TestClient、无 `.github/`、无 requirements.txt；`config.py` 无 `DB_PASSWORD` 直接拒启动，本地无 `.env` → 验证只能 `curl` 生产域名 | **验证半径 = 肉眼可见半径** |
| 手工验证的化石 | `.claude/settings.local.json` 白名单里固化着对生产端点的 `curl` | 裁判存在，但是人肉、生产环境、不可复用 |
| 目标状态不入库 | 服务器外壳（`/var/www/html`、bootstrap/jquery）不在仓库；主页只在服务器 docroot；部署身份 `User=fei` 只写在 unit 注释；`auto_pull.sh` 用 `git reset --hard` 会抹掉服务器手改 | 模型看不到全貌，只能局部修补 |
| 文档已漂移 | `CLAUDE.md` 写 11 个静态挂载 / 12 模块 / 15 router / 11 SPA；实际 `main.py` **22 个 mount、22 个 router、65 个显式端点** | 模型的外部记忆失真 |
| 一次性脚本堆积 | `scripts/` 34 个，25 个是 `fix_*/backfill_*/import_*/add_*`；`audit_project_labels.py` 写了审计逻辑但没人排程；`check_secrets.sh` 注释写着「Wire into pre-commit / CI」却没接 | 手工作业被固化成脚本，但没有变成基础设施 |
| 运维靠人 | `MAINTENANCE.md` 724 行；加一个 SPA 要 4 步（建文件→mount→Apache 双文件 ProxyPass→重启）+ 22 份菜单同步 | 高重复、低风险、可闭环 |
| 已有 AI 资产很厚 | `~/.agents/skills` 25 个（bear 系 8 个、nature-review-studio、wheatomics、lab-server…），`~/.claude/skills` 62 个；全局 `~/.codex/AGENTS.md` 有「文献/分子实体强制核验、钢人论证」硬规则 | range 的原料有，缺编排 |
| 工具没接上 | 仓库自带 MCP（4 个 sequence 工具）**没接任何本地客户端**；wheatomics skill 走公网 API 而不是它 | 模型查数据走最远的那条路 |
| 真实用户在 | 近 61 天日 PV 202–1701（中位数 639），UV 中位数 293、最高 1555 | 可用性是有人在意、值得开会的「结果」 |

**结论：** 我们不是不努力，也不是不会用模型。我们被锁在「speed + 局部 fix」的循环里，因为**任何超出肉眼可确认范围的野心，都没有闭环**。文章说 altitide 的判定信号是「你会不会为此开会」——我们其实有一堆该开会的事（零 5xx、加 SPA 一条命令、表达谱图在所有数据集上不出错），只是它们从没被写成目标。

---

## 3. 七条启发

### 启发 1：speed 已经封顶，缺的是 altitude

一天 7 个 fix 是「正确但没有收敛」的典型。当时如果目标写成**结果**——「这张图在任意 20 组数据集组合下，标签不重叠、不被裁切、边缘留白一致，且能复现生成」——这 7 个 commit 会变成 1 次「建 20 组 golden fixture + 像素/几何回归」，此后同类问题永久消失。文章最实用的一问是：**你希望接下来发生什么？**

### 启发 2：野心被「验证半径」锁死，不是被提示词锁死

我们没有 tests/CI、本地起不来、只能打生产验证——于是模型能独立闭环的最大半径，等于「人眼在浏览器里能看出来的半径」。想让它更野心，先扩大**它能自己验证的半径**，而不是把 prompt 写得更狠。

### 启发 3：第一步不是提野心，是装裁判

一个合格的裁判要满足三条：① 模型能在几分钟内自己跑；② 结果不是模型自己写的；③ 失败会明确报错（不是「看起来对」）。我们其实已经有半成品：`audit_project_labels.py` 的对账逻辑、settings 里那串 `curl`、`check_secrets.sh` 的注释——**只差接线**。装上之后，`altitude` 才有意义；否则「更有野心」只会变成更多无法验收的代码。

### 启发 4：把任务清单改写成结果清单

backlog 里 10 条 fix，值得重写成 3 条带数字和期限的 outcome，例如：

- 30 天内 `/api` 5xx < 0.1%，每条 5xx 自动带上下文落到 issue；
- 新增一个 SPA：1 条命令生成 mount/ProxyPass/菜单块，并自动跑完 5 条验收 `curl`；
- 表达谱图在 20 组 fixture 上零回归（截图像素 + 标签几何双重断言）。

文章说，无法写成结果的目标通常说明你还没想清楚；能写出来，模型才有「更高的地方」可去。

### 启发 5：模型看不到全貌就只能局部修补——把「目标状态」搬进仓库

隐含知识全在服务器上：`/var/www` 外壳、`track` 表要特权账号预建、`git reset --hard` 会抹掉手改、`fei` 用户和 mamba 环境、4 个一次性脚本的执行顺序。模型拿不到这些，就只能改它看得见的那一行。**把部署契约、真实 mounts 清单、菜单单源、DDL 前置条件写成仓库里的可执行规范**，是 altitude 的物理前提（也是让 `CLAUDE.md` 停止漂移的唯一办法）。

### 启发 6：range 的原料我们有，缺的是 crew 编排——以及要避开 role-play

25+62 个 skills 是**道具**，不是团队。文章说的 range 是「为同一个目标引入不同领域的做法」，每个角色交的应该是**可执行的检查**，不是一段像专家的文字：

| 目标 | 该请的角色 | 他交的「检查」而不是「文字」 |
|---|---|---|
| 新增组学模块 | 数据工程师 | schema 契约测试 + 只读库快照断言 |
| 表达谱/统计图 | 统计师 | 多重检验校正、批次效应、效应量，写进脚本 |
| 任何前端图 | 可视化设计师 | 色盲安全、期刊尺寸/DPI、标签碰撞的截图比对 |
| BLAST / daemon | SRE | 队列容量模型、失败率/延迟巡检 |
| 整条交付 | 审稿人 | 独立数据上的复现步骤，不是评语 |

**注意原文的警告**：很容易滑进 role-play——让模型「像审稿人一样写」，只会让对话变怪。要让它「做审稿人会做的事」：查文献、核统计、要原始数据。我们 `bear-*` / `nature-review-studio` 这类技能尤其要按这个标准改造。

### 启发 7：科研红线——只有可被外部证据裁判的环节，才值得提野心

HN 上对原文最有力的一条批评是**责任不可外包**：三个月后发现模型漏判了最紧急的决策，而你没看数据，责任还是你的。生信里这对应 p-hacking、批次效应、选择偏倚、事后叙事。所以野心要优先放在**硬裁判**的环节——数据质量、可复现性、可视化、性能、运维、接口契约；**生物学解释、新颖性判断**这类结论性工作，模型可以是助手，裁判必须是数据/实验/已发表结论。这恰好和文章一致：外部裁判最好是「能跑的工具」——工具越硬，能野心的面积越大。

### 附：对 agent 团队本身的启发

这次检索本身就是个小样例：两个独立上下文的 agent 分别做「外部话语」和「本地现状」，互不知情，综合权留给人。多 agent 的正确用途不是并行加速（那是 speed），而是**引入独立视角与独立裁判**（range + depth）。用多 agent 加速同一件事，只会放大我们已有的 speed 偏置。

---

## 4. 反面：HN 上的三条批评（都成立，且都打在我们身上）

原帖 [HN #50100345](https://news.ycombinator.com/item?id=50100345)（28 分、6 条评论）：

1. **「最紧急的三个决策」交给模型很危险**——三个月后你会发现它漏了明显该做的事，而你没看过数据（[mjd](https://news.ycombinator.com/item?id=50105792)）。
2. **越野心，模型越可能为了「通过」而改测试、编东西**（[UncleEntity](https://news.ycombinator.com/item?id=50111495)）——我们**恰恰没有测试**，所以它连「改测试」都不用，直接说「已修复」。
3. **像广告、缺实证**：作者说让应用「不再崩溃」，但没人给出崩溃率降了几成（[TheSamFischer](https://news.ycombinator.com/item?id=50104716)、[maxcb](https://news.ycombinator.com/item?id=50105334)）。

对我们最实际的一条是第 2 条：**裁判必须独立**——测试由人在 CI 里跑、只读快照不可写、指标口径写死在评审通过的脚本里，模型只能读不能改。

另外：中文圈 5Y/腾讯版把它工具化得最完整（附一个「升维/深挖/跨界/证伪」的中文 skill），第三方 [ambition-loop](https://github.com/linkxzhou/ambition-loop) 做过 A/B 评测（通过率 89.9% vs 68.3%），代价是耗时与 token 明显上升。结论：**别对 hotfix 提野心**，只对「结果型、可验证」的任务提。

---

## 5. 本周就能做的三个实验

**实验 A（半天，最高优先）：装裁判。**
- 用 FastAPI `TestClient` + 只读库快照，覆盖 15 条核心路径（gene / sequence / expression / blast status / comparative）；
- 把 settings 里那串生产 `curl` 变成 `scripts/smoke_prod.py`；
- 给 `audit_project_labels.py` 加 cron/launchd，产出「对账不一致」清单；
- 验收：`python3 scripts/check_all.py` 五分钟内给出 pass/fail，且失败信息能定位到文件与端点。

**实验 B（半天）：10 条 fix → 3 条 outcome。**
- 每条 outcome 必须带数字、期限、裁判方式；
- 验收：贴在仓库 issue 或 `MAINTENANCE.md` 顶部，下周复盘时逐条打勾/打叉。

**实验 C（1 天）：用深度提示词 + crew 跑一次完整交付。**
- 选「SPA 生成器」或「BLAST 容量模型」；
- 先让模型回答原 prompt 的四问，再改写任务；执行时至少两个不同方案；
- 交一份 gap report：原始要求 / 野心版 / 实际达成 / 未达成原因。

---

## 6. 野心自检清单（可直接贴进 CLAUDE.md / AGENTS.md）

1. 这个任务背后的**结果**是什么？做完之后接下来会发生什么？
2. 如果成功，三个月后哪件**例行工作会消失**？
3. 领域里顶尖的人用什么工具、从什么原始材料开始？我用的是不是别人消化好的成品？
4. 有没有一个**不问模型也能判对错**的裁判？谁跑它？多久跑一次？
5. 目标能不能写成数字——哪怕听起来不可能？
6. 我是在让模型**扮演**专家，还是让它**做**专家做的事？
7. 这个结论有没有**独立数据**验证？（科研红线）
8. 失败会以什么形式暴露？多久暴露？谁在看？
9. 我请进来的第二个领域/角色，交的是**文字**还是**可执行的检查**？
10. 人保留了哪个判断？如果模型错了，谁会在什么时候发现？

---

## 7. 参考

- 原文：[How to be more ambitious: A tutorial for humans with models](https://felixrieseberg.com/how-to-be-more-ambitious-a-tutorial-for-humans-with-models/)（Felix Rieseberg, 2026-10-13）
- 续篇：[Made by Mechanical Means](https://felixrieseberg.com/made-by-mechanical-means/)（约 60 个并行 Claude 线程重建个人站）
- 中文最佳解读：[5Y/腾讯：AGI 时代，我们的野心还远不够大](https://news.qq.com/rain/a/20261019A08LIV00)（附中文 skill）；[RichChat 场景改写](https://richchat.cc/2026/10/19/how-to-be-more-ambitious-with-ai/)；[36氪提炼版](https://36kr.com/p/4031956086690185)
- 工具化：[r3dlex/deepen-prompt](https://github.com/r3dlex/deepen-prompt)（原文四问做成 skill）；[linkxzhou/ambition-loop](https://github.com/linkxzhou/ambition-loop)（带外部裁判与 A/B 评测）
- 官方旁证：[Claude Code best practices](https://code.claude.com/docs/en/best-practices)（强调给模型可运行的验证手段）；[Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- 批评：[HN #50100345](https://news.ycombinator.com/item?id=50100345)
- 证据核实：Terence Tao [Math 2.0](https://terrytao.wordpress.com/2026/10/10/math-2-0/) 真实，但「astounding in some directions…」不是该文原句；[Locke & Latham 2002](https://med.stanford.edu/content/dam/sm/s-spire/documents/PD.locke-and-latham-retrospective_Paper.pdf) 结论属实但有承诺/反馈/复杂度等调节变量；[Dantzig 故事](https://engineering.berkeley.edu/george-dantzig-operations-research-phenom/) 获伯克利官方稿证实（1939 年为通行转述）

---

*附：这份笔记的来源——原文全文抓取；外部反响与批评由 discourse-scout 检索并经 HN API / GitHub README 复核；本地现状由 context-mapper 只读盘点，数字经 `git log` / `grep` 复核。*
