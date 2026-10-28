# WheatOmics FastAPI 后端运维记录

> 本文件记录项目迭代中积累的操作经验与常见问题，每次迭代后更新。

---

服务器地址：https://wheatomics.sdau.edu.cn

## 一、新增前端页面的标准流程

以新增 `orthofinder`、`wheatPPI` 等前端模块为例：

### 1. 创建静态文件

```bash
mkdir -p app/static/yourmodule/
```

在 `app/static/yourmodule/` 下放置 `index.html`，**必须使用硬编码的导航菜单**（参考 `app/static/interval/index.html`），不要通过 JS 动态加载 `/header.html`——服务器上不存在该路径。

### 2. 注册 FastAPI 静态挂载

在 `main.py` 中添加一行 `app.mount()`：

```python
app.mount("/yourmodule", StaticFiles(
    directory=Path(__file__).parent / "app" / "static" / "yourmodule",
    html=True
), name="yourmodule")
```

⚠️ **目录名必须与实际文件夹一致**。路径写错会导致 RuntimeError: Directory does not exist。

### 3. 添加 Apache 转发（SSL 和非 SSL）

分别在 `/etc/apache2/sites-enabled/000-default-ssl.conf` 和 `000-default.conf` 中添加：

```apache
ProxyPass /yourmodule http://127.0.0.1:8000/yourmodule
ProxyPassReverse /yourmodule http://127.0.0.1:8000/yourmodule
```

推荐使用 sed 插到已有行后面：

```bash
# SSL
sudo sed -i '/ProxyPassReverse \/interval/a\    ProxyPass /yourmodule http://127.0.0.1:8000/yourmodule\n    ProxyPassReverse /yourmodule http://127.0.0.1:8000/yourmodule' /etc/apache2/sites-enabled/000-default-ssl.conf

# 非 SSL
sudo sed -i '/ProxyPassReverse \/interval/a\    ProxyPass /yourmodule http://127.0.0.1:8000/yourmodule\n    ProxyPassReverse /yourmodule http://127.0.0.1:8000/yourmodule' /etc/apache2/sites-enabled/000-default.conf

sudo apachectl restart
```

### 4. 重启 FastAPI

生产环境由 systemd 管理（单元 `wheatomics-api`，见 §四「生产推荐：gunicorn 8 workers」章节）：

```bash
sudo systemctl restart wheatomics-api
sudo systemctl status wheatomics-api
sudo journalctl -u wheatomics-api -f    # 看启动日志
```

> ⚠️ **改动任何 `.py` 文件都必须手动跑这步**。
>
> Webhook（`/api/webhook/gitee`）**只跑 `git pull`，不会自动重启 API 服务**。
> 即使新代码已经拉到 `/var/www/FastAPI_backend_Port8000/`，正在跑的进程仍然加载旧版本，
> 表现为：路由 404（新增端点没注册）、接口行为错乱（旧逻辑）。
>
> **典型症状**：curl 返回 404 但 OpenAPI 里有路由 → 服务没重启加载新代码。
>
> **判断方法**（服务器上）：
> ```bash
> cd /var/www/FastAPI_backend_Port8000 && git log --oneline -1
> systemctl show wheatomics-api -p ActiveEnterTimestamp   # 服务启动时间
> ```
> 如果 git 最新 commit 比服务启动时间晚 → 必须 `sudo systemctl restart wheatomics-api`。

### 5. 预构建 SPA（Vite / Vue / React）

上面 1–4 步假设前端是手写的静态 HTML。如果前端是**独立仓库里的构建型项目**（Vite + Vue/React），
流程多一步「构建」，但**产物仍然提交进本仓库**——服务器上没有 Node，不装 npm，部署只靠 `git pull`。

目前只有一个这样的模块：**PrimerServer2**（`/PrimerServer2/`）。

| 项 | 值 |
|----|----|
| 源码仓库 | `git@gitee.com:shengwei-ma/PrimerServer-wheatomics.git`（私有，SSH） |
| 构建目录 | 仓库内 `frontend/`（Vue 3 + Vite + Element Plus + D3） |
| 产物落点 | `app/static/primerserver2/` |
| 挂载路径 | `/PrimerServer2`（**大小写敏感**） |

⚠️ **挂载路径必须和 `frontend/vite.config.js` 里的 `base` 一致**。构建时 vite 会把 `base`
写死进 `index.html` 的资源 URL（`/PrimerServer2/assets/xxx.js`），两边对不上就是整页白屏 +
一堆 404。改路径要同时改 vite config 和后端 `app.mount()`，然后重新构建。

重建步骤：

```bash
# 1) 拉源码 + 构建（本地做，服务器上没有 Node）
git clone git@gitee.com:shengwei-ma/PrimerServer-wheatomics.git /tmp/ps2-fe
cd /tmp/ps2-fe/frontend && npm install && npm run build

# 2) 产物拷进本仓库（assets 带 hash，先清旧文件避免堆积）
rm -rf app/static/primerserver2/assets
mkdir -p app/static/primerserver2/assets
cp /tmp/ps2-fe/frontend/dist/index.html app/static/primerserver2/
cp /tmp/ps2-fe/frontend/dist/assets/* app/static/primerserver2/assets/

# 3) 提交 + 部署（服务器侧只需 pull + 重启）
git add app/static/primerserver2 && git commit -m "chore(primerserver2): rebuild frontend"
```

> ⚠️ **别手改 `app/static/primerserver2/index.html`**。下次重建会被覆盖。要改 title、favicon
> 之类，改前端仓库的 `frontend/index.html` 再构建。

这个 SPA 用的接口全部在 `/api/PrimerServer2/*`（见 §二、main.py 的 `PS2_PREFIX`），
和静态挂载 `/PrimerServer2` 是两个不同的前缀，不会互相拦截。

**配置**：这个模块**没有配置文件**。工具路径和限额全部走 Pydantic Settings ——
`app/core/config.py` 里的 `PRIMERSERVER2_*`（见 §四）。原版 PrimerServer 的 `config.ini`
已在 2026-09-21 废弃：那个文件一半是代码早就不再解析的 legacy FASTA 库清单，而且线上那份
有重复键，Python 的 configparser 一读就抛 `DuplicateOptionError`，会把整组
`/api/PrimerServer2/*` 端点变成 500。

**部署自检**：`GET /api/PrimerServer2/health` 逐项检查 samtools / primer3 / blastn /
makeblastdb 四个可执行文件、`BLAST_DB_PATH` 目录、job workdir 是否就位，全通过才返回
`status=healthy`，否则 `degraded` 并列出哪一项是 false。缺工具时首发症状是"任务跑失败"，
这个端点能直接定位。它和 `main.py` 里那个只回一句静态文本的 `/api/health` 不是一回事。

**站点外壳（§七.2 / §七.3）**：菜单栏、页脚、访问统计都按规范接好了，但它们的**源码在前端仓库的
`frontend/index.html`**（`#app` 之外的静态 HTML，Vue 只替换 `#app` 内部，所以重建不丢）。
改菜单要去那边改再重新构建，不要动本仓库的产物。

**菜单是全站同一份，共 22 个副本**（21 个 `app/static/*/index.html`、`stats.html`、`detail.html`，
外加前端仓库那份）。改任何一条菜单项都要**同时改 22 处**，否则立刻漂移——2026-09-21 就是因为
逐份复制粘贴，导致 `CAPS/dCAPS` 只在 5 个页面存在、`SynTenyView` 只在它自己页面里。

2026-09-21 统一时定的三条口径：

- **scRNA / wheatPSP / eQTL 用内链**（`/scRNA/` 等）。原来写的是 `http://wheatomics.sdau.edu.cn/scRNA`，
  实测要 301 三次才落地，最终 URL 还带双重斜杠（`https://...//scRNA/`）；内链一次 200。
- **补上 `CAPS/dCAPS` 和 `SynTenyView`**（原来前者只有 5 个页面有，后者只有自己页面有）。
- **`Neighborhood` 不加**——`/neighborhood/` 线上 404（Apache 规则缺失），加了等于全站散死链。
  见 §三「某个 SPA 在本地正常，线上 404」。

**与 §七 的两点已知差异**（有意为之）：

- **不引 Bootstrap 4.5.3 和 jQuery**。菜单栏和页脚的样式全部来自 `/css/style.css`
  （`#home_header` / `#header-tabs` / `#home_footer` 都是 ID 作用域的），不依赖 Bootstrap；
  页面主体是 Element Plus，再挂一份 Bootstrap CSS 只会互相抢样式。
- **`#app p` 被覆盖回 14px / margin:0**。`/css/style.css` 里有一条全局 `p { font-size:1.15em;
  line-height:130%; margin:0.83em }`，那是给站点散文页用的，套在 Element Plus 表单和结果表格的
  `<p>` 上会全变大变松。前端仓库的 `index.html` 里有一条 `#app p` 把它压回来。

---

## 二、后端路由注册模式

### 创建一个新路由模块

1. 在 `app/api/routers/` 下新建 `yourmodule.py`
2. 定义 `router = APIRouter(prefix="...", tags=["..."])`
3. 在 `app/api/routers/__init__.py` 中导入并暴露：
   ```python
   from .yourmodule import router as yourmodule
   ```
4. 在 `main.py` 中导入并加入 `app.include_router()`

### OpenAPI 分组说明

模块说明表格在 `main.py` 的 `FastAPI(description=...)` 参数里维护，格式为字符串隐式连接：

```python
"<tr><td><b>模块名</b></td><td><code>/api/path</code></td>"
"<td>中文描述</td></tr>"
```

每行开头必须保留缩进，否则 Python 字符串隐式连接会失败。修改后需 `ast.parse()` 确认语法正确。

---

## 三、常见问题

### Q: StaticFiles 挂载报 "Directory does not exist"
**原因**: `main.py` 中的路径与实际文件夹名不匹配（如目录改名后没改代码）。
**解决**: 检查 `app.mount()` 的 `directory=` 参数与 `app/static/` 下的实际文件夹名一致。

### Q: 某个 SPA 在本地正常，线上 404
**原因**: `main.py` 里注册了 mount，但 Apache 没有对应的 `ProxyPass`。uvicorn 直接访问没问题，
经 443 进来就打不到——**两类注册都要做**，少一个就是 404。

**症状**：`curl -I https://wheatomics.sdau.edu.cn/<module>/` 返回 404，
但服务器上 `curl -I http://127.0.0.1:8000/<module>/` 返回 200。

**解决**: 按 §一.3 补 ProxyPass（SSL 和非 SSL 两个文件都要），`sudo apachectl restart`。

**2026-09-21 状态**：

| 路径 | 状态 |
|------|------|
| `/PrimerServer2/` | 规则待补（见 §一.5） |
| `/neighborhood/` | ⚠️ **404，规则一直没加，该 SPA 在线上打不开**。因此**没有**把 `Neighborhood` 加进全站菜单——补上 ProxyPass 之后再把它加进菜单并重新统一 |

### Q: 浏览器报 ERR_CERT_DATE_INVALID
**原因**: 服务器 SSL 证书过期。HTTP 可访问，HTTPS 被浏览器拒绝。
**解决**: 在服务器上续签证书：

```bash
sudo certbot renew
sudo apachectl restart
```

### Q: 前端导航菜单显示不出来
**原因**: `index.html` 使用 JS 动态 fetch `/header.html` / `/footer.html`，但这两个文件服务器上不存在。
**解决**: 改为**硬编码**菜单栏 HTML（参考 `app/static/interval/index.html` 的 `#home_header` + `#header-tabs` + `#home_footer` 结构）。

### Q: API 请求报 Connection Refused (Errno 111)
**原因**: MySQL 服务未启动。
**解决**: 在服务器上执行 `sudo systemctl start mysql`。

### Q: /expression/ 引用的 JS 文件加载失败
**原因**: 之前从 CDN 切换为本地文件后，若引用路径不正确会产生 404。
**现状**: `highcharts*.js` 等文件已放在 `app/static/` 下，前端引用 `/expression/highcharts.js`（注意不是 `/expression/static/highcharts/`）。确保 Apache 对应路径已配置 ProxyPass。

### Q: git push 被拒绝（rejected）
**原因**: 服务端有 webhook 自动 pull 产生的提交，本地落后于远端。
**解决**:
```bash
git pull --rebase origin main
git push origin main
```

### Q: Router 路径变成 `/api/{prefix}/{endpoint}`（双前缀）
**症状**: 重命名 router 的 `prefix=` 后，`curl /api/openapi.json` 显示路径是
`/api/papers/papers` 而不是 `/api/papers`。

**原因**: `main.py` 的 `include_router()` 已经把 `settings.API_PREFIX`（`/api`）拼到所有路由前面。如果 router 自身又写 `prefix="/papers"`，然后 `@router.get("/papers")`，最终路径变成 `/api` + `/papers` + `/papers`。

**正确写法**（推荐）：router prefix 留空，由每个 `@router.get` 写完整路径：
```python
router = APIRouter(prefix="", tags=["..."])

@router.get("/papers")                  # → /api/papers
@router.get("/papers/{pmid}/annotation") # → /api/papers/{pmid}/annotation
@router.get("/stats")                    # → /api/stats
```

**反例**（会出现双前缀）：
```python
router = APIRouter(prefix="/papers")
@router.get("/papers")  # → /api/papers/papers ❌
```

**诊断**：先看 OpenAPI，确认实际注册的路径：
```bash
curl -s https://wheatomics.sdau.edu.cn/api/openapi.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
for p in sorted(d['paths']):
    print(' ', p)
"
```

---

### Q: 改了 Python 后端代码，访问接口还是老逻辑
**症状**: 提交了 Python 文件改动，`git pull` 也跑了，但 `curl /api/xxx` 仍然返回老逻辑（404 / 老 SQL / 老参数）。

**原因**: webhook 只 `git pull`，**不重启 API 服务**。见第一节 4 的 ⚠️ 警告。

**修法**:
```bash
sudo systemctl restart wheatomics-api
```

**判断**: `git log -1` vs `systemctl show wheatomics-api -p ActiveEnterTimestamp` 看是不是老进程。

---

## 四、配置与路径速查

### 数据库配置（`app/core/config.py`）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DB_HOST` | `localhost` | MySQL 主机 |
| `DB_PORT` | `3306` | MySQL 端口 |
| `DB_USER` | `wheatomics_user` | MySQL 用户 |
| `DB_PASSWORD` | *(secret — real value lives only in the server-side `.env`; never commit)* | MySQL 密码 |
| `DB_GENEFUNC` | `Genefuncdb` | 基因功能数据库 |
| `DB_ORTHOFINDER` | `orthofinder_n` | OrthoFinder 数据库 |
| `DB_PPI` | `wheatPPIdb` | 蛋白质互作数据库 |
| `BLAST_DB_PATH` | `/var/www/html/getfasta/blastdb` | BLAST 数据库路径 |
| `ORTHOFINDER_BASE_DIR` | `/var/www/html/orthefind/Results_Jul23` | OrthoFinder 结果根目录 |
| `PRIMERSERVER2_SAMTOOLS` `_PRIMER3` `_BLASTN` `_MAKEBLASTDB` | `/usr/bin/samtools`、`/usr/bin/primer3_core`、`/var/www/html/blast/blast+/bin/blastn`、`.../makeblastdb` | PrimerServer2 外部工具路径（原 config.ini 的 `[Path]`）；`/health` 逐项检查可执行性 |
| `PRIMERSERVER2_LIMIT_SITE` `_LIMIT_PRIMER` `_LIMIT_DATABASE` | `100` / `1000` / `4` | PrimerServer2 单次任务输入上限，超出返回 422 |

### Apache 站点配置（`/etc/apache2/sites-enabled/`）

两个文件需要同步修改：
- `000-default-ssl.conf` — HTTPS（443）
- `000-default.conf` — HTTP（80）

当前已注册的前端转发路径：

| 路径 | 说明 |
|---|---|
| `/api` | FastAPI 核心 API |
| `/expression/` | 基因表达谱查询 |
| `/interval/` | 基因区间查询工具 |
| `/orthofinder/` | OrthoFinder 直系同源群浏览器 |
| `/wheatPPI/` | 小麦蛋白互作查询 |
| `/preblast/` | 预计算 BLAST 查询 |
| `/HomologFinder/` | 小麦-水稻-拟南芥同源查找 |
| `/PfamSearch/` | 基因结构域搜索 |
| `/coexpression/` | 共表达基因查询 |
| `/getfasta/` | FASTA 序列提取 |
| `/assets` | FastAPI 静态资源 |

#### ⚠️ 长响应端点必须给 `ProxyPass` 加 `timeout=` 参数

**症状**：`POST /api/blast/search`（以及任何跑 BLAST、外部工具、超过几十秒的端点）在客户端表现为：
- curl / urllib 报告 `HTTP 000`（TCP 半开连接）
- `URLError: timed out` 或 `Remote end closed connection without response`
- `/api/health` 等 GET 端点**仍正常**，只有长 POST 触发

**根因**：Apache `ProxyTimeout`（多数发行版默认 60~75s）会把超过该阈值的反代响应在客户端一侧掐断。服务端 BLAST 仍在跑、跑完也没人接收，连接僵死。

**修复**：把 `ProxyPass /api http://127.0.0.1:8000/` 这一行的 `timeout` 调大，与 Python 端最长 timeout 对齐（`subprocess.run(..., timeout=600)` → `timeout=600`）。**两文件都要改**：

```apache
ProxyPass        /api http://127.0.0.1:8000/ timeout=600
ProxyPassReverse /api http://127.0.0.1:8000/ timeout=600
```

或全局设（在 `/etc/apache2/conf-enabled/proxy.conf` 加一行；该文件默认不存在则新建）：

```apache
ProxyTimeout 600
```

**应用**：`sudo apachectl graceful`（无需重启 uvicorn，Apache 平滑重载生效）。

**诊断命令**（快速定位是不是这个原因）：
```bash
# 客户端看 timeout 是不是卡在某个固定秒数
time curl -sX POST https://wheatomics.sdau.edu.cn/api/blast/search \
  -d "program=blastn" -d "database=CS-IAAS_T2T.genome_Chr4A" \
  -d "query=>test
GAATTC" --max-time 30 -o /dev/null -w "%{http_code} %{time_total}\n"
# 若 TIME=30.000 整 → curl 自己超时；若 TIME 接近 ProxyTimeout 默认值（60/75/300）→ 是 Apache 掐的
```

#### ✅ 生产推荐：gunicorn 8 workers（替代单 uvicorn）

**为什么**：单 uvicorn worker 跑 `/api/blast/search` 聚合库（`AABBDD.all.denovo` 等）能跑 10~18 分钟，峰值内存 2GB+。两个长 BLAST 接连跑会触发 Linux OOM Killer，把整个 uvicorn 进程杀掉——**整个 API 站都死**。

gunicorn 8 workers 把长查询的影响限制到 1/8：
- 1 个 worker 卡死，其他 7 个继续服务 health / databases / 其他查询
- worker 崩溃（OOM、segfault）gunicorn 自动重启它
- `max_requests` 让 worker 跑 100 个请求后自循环，避免内存累积

**部署步骤**（一次性）：

```bash
# 1) 装 gunicorn（如果还没）
/home/fei/mambaforge/envs/zjw/bin/pip install gunicorn

# 2) 停掉旧的 uvicorn/gunicorn（如果还在跑）
pkill -f 'uvicorn main:app' || true
pkill -f 'gunicorn main:app' || true
sleep 2

# 3) 部署为 systemd 服务（单元文件见下方，生产推荐方式）
sudo cp scripts/wheatomics-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart wheatomics-api

# 4) 验证：1 master + 8 workers
sudo systemctl status wheatomics-api
ps -ef | grep -E 'gunicorn' | grep -v grep
# 期望: 1 个 "gunicorn: master" + 8 个 "gunicorn: worker"
ss -tlnp | grep ':8000'
curl -s http://127.0.0.1:8000/api/health -w " HTTP=%{http_code}\n"
```

**systemd 单元**（推荐，比 nohup 可靠，OOM 杀掉自动重启）：

```ini
# /etc/systemd/system/wheatomics-api.service
[Unit]
Description=WheatOmics FastAPI backend (gunicorn 8 workers)
After=network.target

[Service]
Type=simple
User=fei
Group=fei
WorkingDirectory=/var/www/FastAPI_backend_Port8000
Environment="PATH=/home/fei/mambaforge/envs/zjw/bin:/usr/bin:/bin"
ExecStart=/home/fei/mambaforge/envs/zjw/bin/gunicorn main:app -c gunicorn.conf.py
Restart=always
RestartSec=3
MemoryMax=3G
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable wheatomics-api    # 开机自启
sudo systemctl start wheatomics-api
sudo systemctl status wheatomics-api
```

**确认 Apache 仍反代 `127.0.0.1:8000`**（如果之前是 `0.0.0.0:8000` 也行，但建议改回 127.0.0.1 限制本地）。Apache 配置不动。

**worker 数选择**：8 worker 是 16 核物理机的默认值。如果服务器内存 < 16GB，把 `workers` 调到 `(可用内存 GB) - 4`（如 12GB 内存 → 8 个 worker，每个峰值 1GB 是上限）。

---

## 五、部署快速参考

### 完整上线流程（新增模块时）

```bash
# 本地：开发、测试、提交推送
git add -A
git commit -m "feat: ..."
git push origin main

# 服务器：拉取 + 重启
ssh fei@wheatomics
cd /var/www/FastAPI_backend_Port8000
git pull origin main
sudo systemctl restart wheatomics-api
sudo systemctl status wheatomics-api
# 如果涉及前端路径，还需加 Apache ProxyPass + sudo apachectl restart
```

### MySQL 重启

```bash
sudo systemctl start mysql     # 启动
sudo systemctl status mysql    # 检查状态
sudo systemctl restart mysql   # 重启
```

### SSL 证书续签

```bash
sudo certbot renew
sudo apachectl restart
```

---

## 六、案例：把 `/coexpression` 从 CGI 老页迁到 FastAPI（2026-07）

`/coexpression` 是最后一个仍由 Apache 直接服务老 CGI 页面的前端。这次迭代把它对齐到 8 个已 mount 的 SPA（同 `expression`、`getfasta`、`HomologFinder`、`PfamSearch` 等）。

### 背景

- `app/static/coexpression/index.html` 已经写好（新版 Bootstrap 4.5 + `/api/coexpression/*` 调用）
- 但浏览器访问 `https://wheatomics.sdau.edu.cn/coexpression/index.html` 仍是 5874 字节的 CGI 老页
- 排查三件套：
  1. `grep coexpression main.py` → 没有 `app.mount()`
  2. `grep coexpression /etc/apache2/sites-enabled/*.conf` → 没有 `ProxyPass`
  3. `curl -sI https://.../coexpression/` 看 `Server:` 头 → `Apache`

  → 三件事全缺。`auto_pull.sh` 拉下来的新 HTML **没人服务**。

### 落地（按第一节标准 4 步走）

第一步：在 `main.py` 第 117 行（PfamSearch mount 之后）插入一行（同第一节第 2 步模板，目录名换为 `coexpression`）：

```python
app.mount("/coexpression", StaticFiles(
    directory=Path(__file__).parent / "app" / "static" / "coexpression",
    html=True
), name="coexpression")
```

如果坚持用 sed 改 main.py，锚点选 `/app.moun.*\/PfamSearch/`，注意 Python 字符串里的 `/` 和双引号都要转义：

```bash
sudo sed -i '/app.moun.*\/PfamSearch/a\app.mount("/coexpression", StaticFiles(directory=Path(__file__).parent / "app" / "static" / "coexpression", html=True), name="coexpression")' /var/www/FastAPI_backend_Port8000/main.py
```

第二步：Apache 两文件加 ProxyPass（锚点选最后一个 mount = `/PfamSearch`，最稳）：

```bash
sudo sed -i '/ProxyPassReverse \/PfamSearch/a\    ProxyPass /coexpression http://127.0.0.1:8000/coexpression\n    ProxyPassReverse /coexpression http://127.0.0.1:8000/coexpression' /etc/apache2/sites-enabled/000-default-ssl.conf
sudo sed -i '/ProxyPassReverse \/PfamSearch/a\    ProxyPass /coexpression http://127.0.0.1:8000/coexpression\n    ProxyPassReverse /coexpression http://127.0.0.1:8000/coexpression' /etc/apache2/sites-enabled/000-default.conf
sudo apachectl restart
```

第三步：重启 API 服务（**关键**：webhook 只 git pull，不重启进程，`main.py` 改动不会自动生效）：

```bash
sudo systemctl restart wheatomics-api
```

### 验证

```bash
# 1. uvicorn 是否认识新 mount
curl -sI http://127.0.0.1:8000/coexpression/
# 期望：Server: uvicorn, Content-Length: 20915+

# 2. 经 Apache 443 走 uvicorn
curl -sI https://wheatomics.sdau.edu.cn/coexpression/index.html
# 期望：Server: uvicorn（不是 Apache），新页面大小

# 3. API 仍然通
curl -s https://wheatomics.sdau.edu.cn/api/coexpression/databases
# 期望：{"success":true,"data":[{"id":"CO_result2",...}]}
```

可选清理（老的 CGI 页现在不被 Apache 命中，留着只是脏数据）：

```bash
sudo mv /var/www/html/coexpression/index.html /var/www/html/coexpression/index.html.bak.$(date +%Y%m%d)
```

### 这次迭代踩到的额外坑（前端样式）

| 坑 | 教训 |
|---|---|
| 引用文献块写在 `#results-card` 里 | 用户看不到（卡片默认 `display:none`，点击 Search 才显示）。**引用块必须独立卡片，与结果卡片同级**，始终可见。 |
| 给 `.card-title` 加自定义 `background/padding/font-weight` | 用户要求"标题风格按 HomologFinder 来"，但 HomologFinder **根本没有 `.card-title` 自定义 CSS** —— 完全用 Bootstrap 4.5 的默认渲染。结论：不要给 Bootstrap 内置组件类添加自定义样式，要么纯 Bootstrap，要么用新的工具类。 |
| 三个标题都用 `class="card-title"` | `Retrieve co-expressed genes for your query genes`（页面顶级 h5）和 `Results`（结果卡片内 h6）该用 `class="card-title"`；但 `References & data sources`（引用卡片内的小节标题）应该**纯 `<h6>`**，不要 `card-title`，否则会跟上面两个重样式冲突。 |
| GitHub push 偶发 `cannot lock ref 'refs/heads/main'` | 瞬时锁冲突，先 `git fetch github main && git push github main` 重试即可，**不是真冲突**。 |

### 涉及提交

```
910daeb feat(coexpression): modern Bootstrap 4.5 frontend backed by /api/coexpression
0d9a66e feat(main): mount /coexpression StaticFiles to serve coexpression frontend
b8a5a15 style(coexpression): align citation wording with legacy CGI page
c7c2a5e fix(coexpression): move citations out of results-card so they're always visible
fea7584 style(coexpression): center .card-title text
13f94bb style(coexpression): make .card-title a proper full-width section heading
6db0660 style(coexpression): left-align .card-title
f60806f style(coexpression): revert .card-title to match other pages (HomologFinder etc.)
e364e06 style(coexpression): remove custom .card-title to match HomologFinder exactly
4ecd541 style(coexpression): remove card-title class from References heading
```

---

## 七、前端 HTML 风格规范（所有 SPA 必须遵守）

**新增或修改任何 `app/static/<module>/index.html` 前先读这一节**。9 个 SPA（HomologFinder / PfamSearch / coexpression / expression / getfasta / interval / preblast / wheatPPI / orthofinder）目前共用的约定如下，每条都有踩坑记录。

### 1. 头部 meta 与静态资源（必带）

```html
<!DOCTYPE html>
<html lang="en">                   <!-- 中文页面用 lang="zh-CN" -->
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">  <!-- preblast 漏了，已补 -->
  <title><ModuleName> - WheatOmics</title>
  <link rel="shortcut icon" href="/favicon.ico" type="image/x-icon" />
  <link rel="stylesheet" href="/css/bootstrap-4.5.3-dist/css/bootstrap.css">
  <script src="/js/jquery/1.9.1/jquery.min.js"></script>
```

**约定**：
- `lang` 二选一：英文 `en`、中文 `zh-CN`。**不要写 `lang=""`** 或不写。
- `<title>` 统一格式：`<模块名> - WheatOmics`。
- **Bootstrap 锁版本 4.5.3 + jQuery 锁版本 1.9.1**。不要混用其他版本，CDN 也不要（部分路径必须本地化）。
- `viewport` meta **必须**有，否则移动端布局错乱。

### 2. 顶部菜单与底部页脚：硬编码，不动态加载

```html
<div id="home_header">...</div>      <!-- 顶部硬编码导航 -->
<div id="header-tabs">...</div>      <!-- 二级 tab（可选） -->
```

**约定**：菜单必须**硬编码 HTML**复制到每个 `index.html` 里。**不要**写：

```js
fetch('/header.html').then(r => r.text()).then(html => document.getElementById('home_header').innerHTML = html);
```

—— 线上 `/header.html` 不存在，会导致菜单空白。参考 `app/static/interval/index.html` 的 `#home_header` + `#header-tabs` + `#home_footer` 结构。

> **构建型 SPA 例外**：PrimerServer2（`/PrimerServer2/`）的菜单和页脚不在本仓库，在前端仓库的
> `frontend/index.html` 里。改它的导航要去那边改，其余约定相同。见 §一.5。

### 3. 访问统计：每个页面都自带

```html
<script>
// ===== Visit tracking =====
(function() {
  var page = location.pathname || 'unknown';
  try {
    fetch('/api/track/visit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page: page })
    }).catch(function(){});
  } catch (e) {}
  ...
})();
</script>
```

页脚显示累计访问量（用 `GET /api/track/stats`）。**每个 SPA 都要接**，不要漏。

> ⚠️ **`/api/track/stats` 真实响应是嵌套结构**：
> ```json
> {"today":{"pv":293,"uv":72}, "total":{"pv":7000569,"uv":184}, "online":0}
> ```
> 前端必须读 `data.today.pv` / `data.total.pv` / `data.online`，**不要**直接读 `data.today` / `data.total` 当数字。
>
> 错误写法：`fmt(data.today)` → 永远显示 NaN / 0（triticeae 这次踩坑，`11b5ec4` 修了）
> 正确写法：`fmt(data.today.pv)` / `fmt(data.total.pv)`

### 4. 标题层级（card-title 三种角色）

| 角色 | 用法 | 标签 | class | 例子 |
|---|---|---|---|---|
| **页面顶级标题** | 一个 SPA 一个 | `<h5>` | `class="card-title"` | `HomologFinder — Wheat / Rice / Arabidopsis` |
| **卡片内小节标题** | 大卡片里再分块 | `<h6>` | `class="card-title"` | `Results`（结果卡内） |
| **卡片内安静的小节标题** | 引用块、说明块 | `<h6>` | **不加** `card-title` | `References & data sources` |

**关键规则**：
- 引用 / 文献块必须**纯 `<h6>`**，**不要** `class="card-title"`。否则会和上面的卡片标题样式撞车（coexpression 这次踩坑，`4ecd541` 修了）。
- **不要**给 `.card-title` 加自定义 `background / padding / font-weight / border`。HomologFinder / PfamSearch / 等所有现有 SPA **都没有自定义 `.card-title` 样式**，完全用 Bootstrap 4.5 默认渲染。新增样式请用新工具类（如 `text-muted small`），不要碰 Bootstrap 内置类。

### 5. 卡片（card）布局约定

- 整页通常 3 张卡：**输入卡** → **结果卡**（默认隐藏，点击 Search 后显示） → **引用 / 说明卡**（**始终可见**，与结果卡**同级**，不要嵌进结果卡内）
- 引用 / 说明块 **不要**塞进结果卡内部，否则结果卡隐藏时引用也跟着消失，用户看不到（coexpression 这次踩坑，`c7c2a5e` 修了）。

### 6. 引用 / References（如果有）

引用统一放最底部一张独立卡片内：

```html
<div class="card mb-4" id="references-card">
  <div class="card-body">
    <h6>References &amp; data sources</h6>     <!-- 纯 h6，不加 card-title -->
    <ol>
      <li>... doi:10.xxx/xxx</li>
      <li>... doi:10.yyy/yyy</li>
    </ol>
  </div>
</div>
```

**约定**：没有外部数据源 / 没有文献要引用时**不要硬加**这一块。

### 7. 自定义 CSS（`<style>`）

每个 SPA 都有少量自定义样式，**允许但要节制**：

- **不要**覆盖 Bootstrap 内置类（`.card-title` / `.btn-primary` / `.form-control` 等），改用新类或工具类
- 自定义类名加模块前缀防冲突：`.coexpr-` / `.pfam-` / `.homolog-` / 等等
- 颜色 / 字体用现有 Bootstrap 变量（`var(--primary)` / `var(--info)`），不要写死 `#3a86ff`

### 8. API 调用约定

```js
fetch('/api/<module>/<action>', { ... })
  .then(r => r.json())
  .then(({ success, data, error }) => {
    if (!success) throw new Error(error);
    // 用 data
  })
  .catch(err => showError(err.message));
```

- 所有响应都是 `{success, data, error}` 结构（见 `main.py` 的全局异常处理）
- 错误用统一的 toast / alert，不要每页发明自己的弹窗样式

### 9. JS 库引用

- Highcharts 等大型库**本地化**到 `app/static/js/` 或 `app/static/` 根，**不要**走 CDN
- `<script>` 顺序：`jquery` → `bootstrap` → 业务脚本
- 模块化代码用 IIFE 包裹，避免污染 `window`

### 10. 与后端契约

新增 SPA 时**先**写 `app/api/routers/<module>.py`，在 `main.py` 的 `app.include_router()` 列表里加一行；前端 `index.html` 之前先把 `app.mount()` 加上（按第一节 4 步走）。**不要**先写前端再补后端，否则会上线一半。

---

## 八、自检清单（提交前必跑）

新增/改动 SPA 后，本地或服务器上自检：

```bash
# 1. 语法 / 渲染
curl -sI http://127.0.0.1:8000/<module>/
# 期望：200，Content-Length > 5 KB（<5 KB 多半是老 CGI 漏改）

# 2. 头信息
curl -sI http://127.0.0.1:8000/<module>/ | head
# 期望：Server: uvicorn, Content-Type: text/html

# 3. 经 Apache 443
curl -sI https://wheatomics.sdau.edu.cn/<module>/index.html | head
# 期望：Server: uvicorn

# 4. API 通
curl -s https://wheatomics.sdau.edu.cn/api/<module>/<action> | head -c 200
# 期望：{"success":true,...

# 5. HTML 头部 6 件事齐
curl -s http://127.0.0.1:8000/<module>/index.html | head -10
# 期望：charset / viewport / title / favicon / bootstrap.css / jquery 都齐

# 6. 多宽度渲染（见第九节；需要本机 ego-browser，无需 npm 安装任何东西）
bash scripts/spa_visual_check.sh http://127.0.0.1:8000/<module>/
# 期望：Result: PASS；再逐张看一下 w360 / w768 / w1440 截图
```

**全部 ✓ 才算这个迭代完成**。

---

## 九、多宽度渲染检查（SPA 改造必跑）

借鉴 Hallmark（`sloplint`）的"8 种宽度真实浏览器审查"思路，用本机已有的 `ego-browser`
实现，**不安装任何 npm 依赖、不改生产环境**。目的不是替代人工 review，而是把
"移动端/平板破版、对比度不足、异步加载没等到就截图"这类问题在 commit 前自动化掉。

### 什么时候跑

- 新增或改造 `app/static/<module>/index.html`（尤其像 wheatPTM 那样整页改版）之后、commit 之前；
- 把截图贴到 PR / 聊天里一起 review；
- 排查"线上某个宽度下有横向滚动条"之类的问题时，先跑一遍定位元素。

### 用法

```bash
# 1) 纯落地页（本地 dev server 或线上 URL 都行）
bash scripts/spa_visual_check.sh http://127.0.0.1:8000/wheatPTM/

# 2) 需要交互的页面：填表 → 点搜索 → 等结果区，并额外截结果区
bash scripts/spa_visual_check.sh https://wheatomics.sdau.edu.cn/wheatPTM/ \
  --label wheatptm-result \
  --fill '#protein-input=TraesCS1A02G000100LC.1' \
  --click '#search-btn' \
  --wait '#result-area' \
  --scroll-to '#result-area'

# 3) 存量页面巡检（老 Bootstrap SPA 也能跑）
bash scripts/spa_visual_check.sh https://wheatomics.sdau.edu.cn/wheatPSP/ --label legacy-wheatpsp
```

默认宽度：`360,390,414,768,1024,1280,1440,1920`（≤480 用 844 高 + 触屏模拟）。
常用参数：`--widths 390,768,1440`（只跑几档更快）、`--settle 1200`（慢接口页面）、
`--out <dir>`（保存位置）、`--label <name>`（报告名/目录前缀）。

### 判什么

| 级别 | 检查项 | 说明 |
|---|---|---|
| **Floor（退出码 1）** | 横向溢出 | `scrollWidth > viewport`，并给出越界元素 selector + 坐标 |
| | 图片加载失败 | `img.complete && naturalWidth === 0` |
| | 页面 JS 错误 | 通过 CDP `Page.addScriptToEvaluateOnNewDocument` 注入捕获 |
| | 缺 `meta viewport` | 移动端直接失效，老页面常见 |
| | 文字对比度 < 3:1 | WCAG 可读性底线（跳过背景图/渐变上的文字） |
| | `--wait` 选择器没出现 | 说明交互/异步状态没达到预期 |
| **Warn（不失败）** | 对比度 3–4.5:1 | 逐条列出文字、颜色、背景、selector |
| | 图片缺 alt、`<html lang>` 缺失 | 无障碍 |
| | 小点击目标 | ≤480 宽下控件 <24px（正文内联链接按 WCAG 2.5.8 豁免，不报） |

### 产出

- 输出目录（默认 `$TMPDIR/spa-check/<label>-<时间戳>/`）：
  `report.md`（人看）、`report.json`（机读/后续 CI）、`w360.png` … `w1920.png`
  （每个宽度首屏截图；给了 `--scroll-to` 再加 `w*-section.png`）；
- 终端直接打印 markdown 摘要：宽度 × 溢出/破图/JS 错误/对比度/小目标 的表格。

### 依赖与边界

- **需要 `ego-browser`**（本机已装，Agent 验收也在用）；服务端不装 Node，所以这是**本地开发期工具**，
  不进生产链路、不进服务器；
- 只检查"渲染与可访问性"，不检查数据/接口正确性（那仍按第八节 curl 自检）；
- 检查时通过 CDP 禁用浏览器 HTTP 缓存，刚部署完直接跑也能看到新页面；
- 对比度会跳过背景图/渐变上的文字（无法可靠计算），这类地方仍靠人眼；
- 主题自带的问题（如 V2.0/outsitelink 的 "Back to top ↑" 在手机上是 72×15px）会作为
  Warn 报出来，属于**仓库外主题**的问题，改主题时要一并修，不要在单个工具页里私改。

---

## 十、BLAST SPA（新版搜索页 + 结果页）

ViroBlast 老页面（`/blast/blast.html` + `blastresult2.php`，Apache docroot，不在本仓库）的替代实现，
V2.0 设计语言、纯静态单页、复用现有 `/api/blast` 异步任务后端。**源码在本仓库**：

- 页面：`app/static/blast2/index.html`（单文件，内联 CSS/JS；主题与 header/footer 取自
  `/outsitelink.html`，与 wheatPTM 页一致）
- 部署脚本：`scripts/deploy_blast2_preview.py`（docroot 拷贝 + 时间戳备份，幂等）
- 线上地址：**https://wheatomics.sdau.edu.cn/blast/blast.html**（canonical，替换原 ViroBlast 表单页）
  · 别名/预览：https://wheatomics.sdau.edu.cn/blast/blast2.html（同一文件）
- 结果深链接：`/blast/blast2.html#/job/<job-id>`（job 结果保留 7 天，过期由 API 返回 404）

### 页面能力

**搜索视图**
- 5 个 program（blastn/blastp/blastx/tblastn/tblastx），切换 program 自动重载对应类型的数据库；
- 数据库选择器：按分类折叠（`/api/blast/databases?program=...`）、名称过滤、分类全选、快捷
  “All proteins/All genes (combined)”、已选 chips、上限 20 个（与 API 限制一致）；
- 分类内再按**库类型分组**（combined / genome / CDS / protein）；每组的 **Genome** 只列
  整基因组库（库内包含该组装的全部染色体，如 21/14/7 条），并显示 `21 chr` 等 badge；
  **单染色体拆分库不在分类里展示，仅在搜索框中出现**；提供类型筛选 chips 和
  “chromosome-level assemblies only” 开关；
- 组装质量标签以数据库实际内容校准：`app/services/data/blast_db_levels.json` 是对
  `genome_registry` 的覆盖表（由 `scripts/audit_assembly_levels.py` →
  `scripts/make_level_overrides.py` 生成），修正了 scaffold/contig 误标、缺失的染色体级
  组装（如 Jagger/Julius/Mace/Renan/Barley2/rye Lo7/T. urartu 等）；
  每条库显示类型与组装质量 badge。元数据来自 API 的 `database_meta`
  （`kind` / `assembly` / `chromosome` / `assembly_level`，由 `genome_registry` 的
  `blast_*` 基名 + `assembly_level` 关联得到），前端仅作为兜底；
- 仅用于取序列的超大聚合库（`all_genomes` / `all_other_genomes`）以及所有失效的
  legacy alias（`LEGACY_ALIAS_DBS`）和坏库（`BROKEN_DB_BASES`，如 `Foma.pep`）都
  **不在 BLAST 数据库列表中展示**（后端过滤 + 前端防御性隐藏）；`all_genomes` 等仍可
  通过 `/api/sequence/*` 和 getfasta 页面使用；
- 查询输入：粘贴 FASTA 或多序列、上传 FASTA 文件（客户端读取，≤5 MB）、按 program 提供示例序列；
  输入框 placeholder 会随 program 切换显示核酸/蛋白示例预览，避免在 blastn 下误把蛋白序列当核酸；
- 参数：E-value、max target sequences、word size、matrix、输出格式（hits+alignments / 仅 TSV / 仅文本）；
- 提交走 `POST /api/blast/search` 且 `wait=false`，立即进入结果视图并轮询
  `GET /api/blast/status/{job_id}`；
- 最近任务存 localStorage，可一键重开；带浏览器端哈希路由（`#/job/<uuid>`）。

**结果视图**（参考 NCBI BLAST 结果页结构）
- Job summary：program / 库 / 参数 / job id / 提交时间 / 结果过期日期；
- 四个 tab：**Graphic Summary / Descriptions / Alignments / Downloads**；
- Graphic Summary：按 query 画命中示意图，HSP 色块按 identity 着色，悬停看位置/E value，点击跳到对应描述行；
- Descriptions：按 subject 聚合 HSP（跨 HSP 的 Max score、Total score、Query cover、E value、
  Per. ident、Aln length、HSP 数）；支持 Graphic-style 表头排序、Filter Results（Query、identity ≥、
  E value ≤、Query cover ≥）、勾选行并导出 selected TSV、点击行展开每个 HSP 的区间/BTOP/完整标题；
- Alignments：懒加载 `result.txt`（outfmt 0），按 hit 解析成可折叠卡片，Query/中间行/Sbjct 三段
  彩色渲染（相同=绿、positive=橙、错配=粉底）；
- Downloads：直接给出 API 返回的 `download_urls`（tabular/traditional）。
- 多 query 的 job 会按 Query 分组显示，并提供 query 过滤。

### 部署 / 校验

```bash
# 发布/更新（服务器上；canonical + 别名一起，内容相同；会先备份原文件）
python3 scripts/deploy_blast2_preview.py
python3 scripts/deploy_blast2_preview.py --check   # 期望全 [ok]，用于确认 docroot 与仓库一致
python3 scripts/deploy_blast2_preview.py --canonical-only   # 只更新 /blast/blast.html

# 改完页面后本地验收
bash scripts/spa_visual_check.sh https://wheatomics.sdau.edu.cn/blast/blast2.html
```

### 现状与待办（重要）

- **已替换 canonical 表单页**：`/blast/blast.html` 现在就是本 SPA（老 ViroBlast 页在 docroot 留有
  `blast.html.bak-<时间戳>`，回滚只需 cp 回来）；全站导航/书签无需改动。
- 老结果查看器 `/blast/blastresult2.php` **保持原样**，历史结果链接仍可用；新任务的“结果页”是本 SPA 的
  `#/job/<uuid>` 视图。
- 若后续要把老结果页也重定向到新 SPA，需要单独的旧 job 兼容方案（不在本轮范围）。
- 老 ViroBlast 的部分高级参数（soft mask、genetic code、alignment view 等）当前 `/api/blast`
  不提供，新版只暴露后端支持的参数子集。
- 老结果页 `/blast/blastresult2.php` 未重定向到新 SPA（历史链接兼容），未来可做旧 job 的跳转映射。
- Acc. len（subject 全长）当前 TSV 不提供，暂以 Aln length + HSP 数替代；如需 NCBI 同款列，可让
  `/api/blast` 在 outfmt 中增加 `slen` 字段。

---

## 十一、BLAST 数据库体检 / 清理

新增 `scripts/audit_blast_databases.py`（服务器上跑，需要 app 环境的 pymysql）：

```bash
# 只体检（推荐先跑；输出 JSON + Markdown）
/home/fei/mambaforge/envs/zjw/bin/python scripts/audit_blast_databases.py \
    --json /tmp/blast_audit/report.json --md /tmp/blast_audit/report.md

# 快速复检（跳过逐库 blastdbcmd，只查 alias + registry）
... --skip-base-scan

# 备份式清理：把坏掉的 alias 文件（只移动 .nal/.pal，不动成员库）移到
# /var/www/data/masw_data/blastdb_alias_backup_<timestamp>/
... --apply-clean
```

体检项：
1. `blastdbcmd -info` 逐个打开 BLAST_DB_PATH 下所有库（单卷/多卷，3126 个 base）；
2. 解析所有含 `DBLIST` 的 alias 文件，检查成员是否悬空、alias 是否可打开；
3. 四个维护中的 getfasta 聚合库（all_genomes / all_other_genomes / all_genes / all_proteins）；
4. MySQL `genome_registry` 里 319 条 `blast_genome_db` 是否都有可打开的库文件
   （registry 存的库名不带 `.genome`/`.add_Description.*` 后缀，脚本会自动解析）。

### 2026-10-26 首次全量体检结果

- 3,126 个数据库 base，**13 个打不开**：12 个 legacy alias + `Foma.pep`（mdb_env_open）；
- alias 共 204 个，**12 个坏**：`all1_genomes`…`all7_genomes`（每库 305 个成员全部悬空）、
  `all_Allohexaploid`（59 个成员悬空）、`all_Allotetraploid`（8 个）、`all_Diploid`（14 个）、
  `all_OtherTriticeae`（26 个）、`all_tri6`（48 个成员悬空，`.nal`+`.pal`）；
- 4 个维护聚合库全部正常；
- registry 只有 1 条异常：`Triticum_aestivum_JM44` → `primer.Triticum_aestivum_JM44`
  （该 primer 库已删除）；**2026-10-26 已修正**为实际库 `AABBDD_Triticum_aestivum_JM44`
  （三个 `blast_*` 字段统一，旧行备份在
  `/var/www/data/masw_data/genome_registry_jm44_backup_20261026_161514.json`），复检缺失=0；
- **已清理 13 个 alias 文件**（含 all_tri6 的 `.nal` + `.pal`）→
  `/var/www/data/masw_data/blastdb_alias_backup_20261026_155536/`（84K，回滚直接移回即可）；
- `Foma.pep` **已于 2026-10-26 删除**：9 个文件（`.phr/.pin/.pjs/.pog/.pos/.pot/.psq/.ptf/.pto`）
  备份到 `/var/www/data/masw_data/blastdb_removed_20261026_161514/`，`BROKEN_DB_BASES`
  里保留名字仅作为旧备份恢复时的保险；
- 清理后 BLAST 列表：blastn 2,926 → 2,918，blastp 194 → 193（Foma.pep）。

**约定**：以后重命名/重建 BLAST 库后，必须同步重建或删除相关 alias（否则 alias 会指向旧名），
并在发布前跑一次本脚本；`--apply-clean` 只移动 alias 文件，永远不会动成员库。

### 附：重复库清理记录

- `CS21_S1_S2_S3_All_NLR`（2024-08 建，16 卷，13.0 GB）与
  `CS21_S1_S2_S3_All_NLR.fasta`（2026-09 重建，5 卷）索引的是同一套 105 条序列
  （条目清单 md5 一致、总长 55,798,255,760 bp 一致），旧库已确认无引用。
- All-in-one 分类展示 **21 个六倍体染色体聚合库**：`all_Allohexaploidchr1A` … `chr7D`，
  每个聚合 50 个 AABBDD 组装的对应染色体；整体 `all_Allohexaploid`（52 个整基因组
  alias）因 BLAST 2.12 文件句柄限制无法再嵌套而隐藏。
- 另有重复的 legacy 聚合 alias：`all_gene` / `all_protein` 与维护中的
  `all_genes` / `all_proteins` 序列数、总长、DBLIST 成员完全一致（2026-10-24 重建），
  已从 BLAST 选择器隐藏，只保留复数版本；直接 API 仍可用旧名。
- 2026-10-26 已删除旧库 70 个文件（13.0 GB），备份清单与 6 个小索引文件在
  `/var/www/data/masw_data/cs21_nlr_old_build_20261026_2143/`；新库保留并验证可打开
  （105 sequences / 55.8 Gb）。`DUPLICATE_ALIAS_DBS` 中保留旧名仅作防恢复的保险。

---

## 十二、SPA 统一 V2.0 外壳（按 `/V2.0/` 与 `/blast/blast.html` 风格改造）

全站 SPA 采用同一套 V2.0 chrome：主题变量、固定 header + 大下拉导航、hero 区、深绿 footer（含
访问统计）。样式和 header/footer 标记**只维护一份**，不再逐页复制。

### 资产与来源

| 路径 | 说明 |
|---|---|
| `app/static/_v2/shell.css` | V2.0 主题 + header/footer/hero 样式 + **Bootstrap 4 桥接**（`.card` / `.btn` / `.form-control` / `.table` / `.nav-tabs` / `.badge` / `.alert` / `.modal` / `.dropdown-menu` / `.pagination` / `.progress`、`h1–h4`、`.container`、`.text-muted`） |
| `app/static/_v2/shell.js` | 注入 SVG sprite、header、footer；接管移动端菜单、下拉、Back to top、footer 访问统计；高亮当前模块导航 |
| `app/static/_v2/template.html` | 转换模板（head + hero + main + footer 占位 + 脚本顺序） |
| `app/static/_v2/README.md` | 逐页改造 checklist / 验证命令 / 页面清单 |
| `scripts/extract_v2_shell.py` | 从 canonical BLAST 页（`app/static/blast2/index.html`，即线上 `/blast/blast.html`）重新抽取上述资产 |

- 服务地址：**`/api/v2shell/shell.css|shell.js|template.html`**（`main.py` 里 `app.mount("/api/v2shell", …)`）。
  放 `/api/` 前缀是有意为之：Apache 已把 `/api` 反代到 FastAPI，**新增挂载不需要改 Apache**。
- 修改 chrome：改 canonical BLAST 页 → `python3 scripts/extract_v2_shell.py` → 提交生成物（勿手改 `_v2/shell.*`）。
- docroot 的 Bootstrap 4.5.3 是站点定制版：`.card-body` 有 6px `#1a659e` 顶条、`.card-title` 是
  `#00aadc` 居中。shell.css 的桥接已覆盖，老页面转换后不会串色。

### 单页改造步骤（摘要，完整版见 `app/static/_v2/README.md`）

1. head：保留页面原有本地资源（Bootstrap/jQuery/Plotly/Select2…），补 `viewport`、`title`、
   `favicon`，在原有样式之后加载 `/api/v2shell/shell.css`；
2. 删除旧框架：`#home_header`、`#header-tabs`、`#home_footer`、`#visit-stats`、以及每页各自的
   `/api/track/visit` + `/api/track/stats` 脚本；
3. body 改为 `<div id="v2-shell-header"></div>` + `<main id="main-content">`（`.news-hero` + `.news-body > .container`）
   + `<div id="v2-shell-footer"></div>` + `<script src="/api/v2shell/shell.js"></script>`；
4. 页面自有 CSS 改用 V2.0 token（`--forest/--leaf/--mist/--line/--muted/--page` 等），组件优先用共享 `.card/.btn/.form-control/.table/.nav-tabs`；
5. **保留所有功能 id 与页面 JS**，只替换框架。

### 验证（每页必做）

```bash
# 1) 静态自检
node --check app/static/_v2/shell.js
grep -c "api/v2shell/shell" app/static/<module>/index.html        # 期望 2
grep -cE "home_header|header-tabs|home_footer|visit-stats" app/static/<module>/index.html   # 期望 0

# 2) 本地渲染（/api/v2shell 指向本地副本，绕开 API 依赖）
rm -rf /tmp/v2test && mkdir -p /tmp/v2test/<module> /tmp/v2test/api/v2shell
cp app/static/<module>/index.html /tmp/v2test/<module>/
cp app/static/_v2/shell.css app/static/_v2/shell.js /tmp/v2test/api/v2shell/
(cd /tmp/v2test && python3 -m http.server 8011 >/dev/null 2>&1 &)
bash scripts/spa_visual_check.sh http://127.0.0.1:8011/<module>/ --widths 390,768,1440

# 3) 部署后线上验收（Lead 批量部署后执行）
bash scripts/spa_visual_check.sh https://wheatomics.sdau.edu.cn/<module>/ --widths 390,768,1440 --label v2-<module>
```

期望 `Result: PASS`；唯一可接受的 Warn 是 footer "Back to top ↑" 在 390px 下的小点击目标（主题自带，见第九节）。
除渲染外还要在线上做一次功能冒烟：示例输入 → 提交 → 结果表/图出现。

### 仓库外页面收编（2026-10-27 起）

站点还有一批不是 SPA、也不在任何 ProxyPass 前缀下的 docroot 页面。它们现在由
`app/static/docpages/` + `scripts/deploy_doc_pages.py` 管理（repo 为源，脚本负责带时间戳备份地
发布到 `/var/www/html`；不需要改 Apache、不需要重启服务；支持 `--check/--dry-run/--only`）。
覆盖页面：`/jbrowse.html`、`/download.html`、`/help/contact.html`、`/help/news.html`、
`/outsitelink.html`、`/GeneHub/index.html`，以及 GeneHub 结果 CGI `/cgi-bin/geneDetail.py`
（该 CGI 目标文件属 root：2026-10-27 已通过 docker root 步骤安装并上线，安装/回滚方式见
`app/static/docpages/README.md`；以后更新这个 CGI 仍需一次 root/docker 操作）。

- `/PrimerServer/`（v1）与 `/PrimerServer3/`（裸 Vite 入口副本）已从 docroot 移走，备份在
  `/var/www/data/masw_data/backup_primerserver_20261027/`；导航 Tools、`/V2.0/` 和根首页的
  PrimerServer 链接统一指向 `/PrimerServer2/`。
- 仍在 docroot、暂未收编的运行时依赖：`/V2.0/news.json`（新闻 feed，被 `help_news.html` 运行时读取）、
  `/css/wheat.jpeg`（outsitelink hero）、`/cite.html`（jbrowse 引文块）、`/V2.0/` 图片。
- `/GeneHub/index.html` 的部署目标目录属 fei，可直接发布；`/cgi-bin/*` 属 root/www-data，
  更新时需要 sudo 或 `docker run -u 0`（见 `app/static/docpages/README.md`）。

### 部署注意

- 只改静态文件也要 `sudo -n systemctl restart wheatomics-api`（StaticFiles 目录内容会即时生效，
  但 `/api/v2shell` 是 Python 侧挂载，需重启；重启后端口 8000 通常要 2–3 分钟才恢复监听，期间 Apache 返回 503 属正常）。
- 批量改造时按批次提交/部署，每批部署后跑一遍该批的线上 `spa_visual_check`。

### 进度清单（2026-10-27 全部完成）

- 已 V2.0：`blast2`（`/blast/blast.html` canonical）、`wheatPTM`、`preblast`、`primerserver2`、
  `getfasta`、`interval`、`expression`、`coexpression`、`genes`、`caps`、`papers`、`eqtl`、`GO_KEGG`、
  `HomologFinder`、`idConvert`、`neighborhood`、`orthofinder`、`PfamSearch`、`wheatPPI`、`VariantHub`、
  `syntenyview`、`scRNA`、`wheatPSP`、`sms2`（入口页）。
- 线上验收：每页 `spa_visual_check.sh --widths 390,768,1440` → PASS（仅 footer Back to top 小目标 Warn）；
  另做了一次功能冒烟（示例输入 → 结果表/图/下载出现）。
- 仓库外遗留：`/sms2/*.html` 的第三方工具页（docroot 自带，`.gitignore` 只放行 `app/static/sms2/index.html`）、
  老 CGI 页（`/symap/`、`/tools/*.html` 等）不在本轮「SPA」范围。
- **站点根路径已切换为 V2.0 首页（2026-10-27）**：`/var/www/html/index.html` 现在是 `/V2.0/index.html`
  内容（仅把 `home.png` / `footer-plot.png` / `Logo-small.png` 改成 `/V2.0/…` 绝对路径），旧首页备份在
  `/var/www/html/index.html.bak-20261027_081021`；`/V2.0/` 目录保留兼容旧书签。同步把 shell / BLAST 页的
  Home、brand、`#tools`/`#data`/`#citation` 链接从 `/V2.0/` 改成 `/`。
- ⚠️ `/neighborhood/` 的 Apache vhost **没有** `ProxyPass`，线上用 docroot 符号链接指向仓库目录：
  `ln -s /var/www/FastAPI_backend_Port8000/app/static/neighborhood /var/www/html/neighborhood`
  （`/var/www/html` 开了 `FollowSymLinks`，`git pull` 后自动生效；若以后补 ProxyPass 记得删符号链接）。

---

## 十三、KnownGene 数据更新流程（v2056 起）

KnownGene（`/genes/`，后端 `/api/genes/known/*`，库 `cloned_gene_db.cloned_gene_tbl`）的数据来自人工整理的 Excel 清单。
从 v2056（2026-10-28，1420 行 × 17 列）起，更新流程固定为「Excel → JSONL 校验 → clone_id 映射 → staging 单事务替换」，
**禁止再用 TSV/LOAD DATA 直接灌库**（2026-10 曾发生 1636 行 TSV 引号错位坏导入，残骸 `cloned_gene_bad_import_backup` 仍在库中）。

### 目录与产物

| 文件 | 用途 |
|---|---|
| `scripts/known_genes_v2055/extract.py` | xlsx → `out/known_genes_<ver>.jsonl` + 校验报告 + 前端 fixtures |
| `scripts/known_genes_v2055/migrate_known_genes_v2055.py` | `--phase prepare/data/verify/rollback`（prepare 只读；data 单事务） |
| `scripts/sql/known_genes_v2055_ddl.sql` | root 一次性 DDL：追加 8 列 + 加宽 2 列 + 备份/staging 表 |
| `scripts/known_genes_v2055/README.md` | 完整操作说明与验收口径 |
| `scripts/known_genes_v2055/out/` | 生成产物（gitignore；JSONL 约 8 MB） |

### 标准流程（以 v2056 为例）

```bash
# 1) 提取 + 校验（期望 fatals=0, multi_value_anomalies=0）
python3 scripts/known_genes_v2055/extract.py --xlsx "/path/to/已知基因逐条提取清单_..._v2056_20261028.xlsx"

# 2) 只读映射预演（生产节点，应用账号）：clone_id 继承/孤儿/新号区间
python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase prepare \
  --jsonl /tmp/known_genes_v2056.jsonl --report-dir /tmp/kg_migration

# 3) root DDL（必须先于代码上线：新代码 SELECT 新列）
sudo mysql < scripts/sql/known_genes_v2055_ddl.sql

# 4) 数据替换（应用账号，单事务 DELETE + INSERT...SELECT；禁止 TRUNCATE）
python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase data --dry-run --jsonl /tmp/known_genes_v2056.jsonl --report-dir /tmp/kg_migration
python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase data --commit  --jsonl /tmp/known_genes_v2056.jsonl --report-dir /tmp/kg_migration
python3 scripts/known_genes_v2055/migrate_known_genes_v2055.py --phase verify --jsonl /tmp/known_genes_v2056.jsonl --report-dir /tmp/kg_migration
```

### 口径与坑（重要）

- **多值字段**：`title`/`doi`/`publication_year` 三列以 `; ` 分隔、按位置一一对应；导入后统一存成 `###` 拼接，
  API 用 `split_aligned_multi_value()` 保位拆分 → `references[] {doi,title,year}`。异常行必须先在 Excel 修正（v2055→v2056 修了 16 行）。
- **clone_id 稳定性**：旧行能映射到新数据的保留原 `clone_id`（v2056：321/520）；映射用
  `Genehub_DB.GenePageIWGSCv1_table` 做 v1/v2→v3 ID 转换 + gene_id/同名同染色体规则；未映射旧行删除且 **id 不复用**。
  详情 URL 一律用内部 `clone_id`（`/genes/detail.html?id=<clone_id>`）。
- **`#` 字符**：新数据含 `7S#1`、`lines #1` 等字面 `#`，known 端点按 `reference_genome_id IS NULL` 区分 legacy；
  **不能全局改 `normalize_text()`**（其它 15+ 模块依赖旧的 `#`→`'` 约定）。
- **列类型**：`gene_phenotype`/`gene_species` 已加宽到 varchar(2000)/(1000)；`key_result` 保持 varchar(15000)；
  `publication_year` 保持 YEAR(4)=最早年份，多值原文在 `publication_years`。
- **字符集**：表维持 utf8mb3。直接 CONVERT 到 utf8mb4 会因行大小 73,490 B > 65,535 B 报 ERROR 1118
  （必须先 `key_result` → TEXT，见 `docs/known_genes/backend_investigation.md` §4.3）。
- **前端**：`/genes/` 列表分页 50/页、Stats 走 `/api/genes/known/stats`；改前端后必须跑
  `bash scripts/spa_visual_check.sh <url> --click 'a[href="#tab-stats"]' --wait '#stats-content'`。
- **回滚**：数据 `--phase rollback --commit`（从 `cloned_gene_tbl_backup_<date>` 恢复旧 N 行）；
  代码/前端 `git revert`；DDL 结构回滚见 `scripts/sql/known_genes_v2055_ddl.sql` 末尾注释块。
- 详细上线记录与验收数值：`docs/known_genes/ROLLOUT_v2056.md`、`docs/known_genes/DEPLOYMENT_v2056.md`。

### 13.1 在线更新接口（KnownGene WRITE API，2026-10-28 起）

单个/批量新增或修改已知基因，不再需要改库或跑迁移脚本，走受鉴权保护的 HTTP API：

- **DDL（一次性，root）**：`sudo mysql < scripts/sql/known_gene_write_api.sql`
  （只新增 `known_gene_api_keys` / `known_gene_change_log` 两张表，不动业务表）。
- **建 key（应用账号，无需 root）**：
  `python3 scripts/known_gene_api_key.py create --label <name> --scopes write --expires-days 365 --out-file <600文件>`
  （raw key 只输出一次；DB 只存 sha256；`--scopes admin` 可查审计；`list`/`revoke --id N` 管理）。
- **端点**（`Authorization: Bearer kgw_...`，也兼容 `X-API-Key`）：
  `POST /api/genes/known/write`、`PATCH /api/genes/known/write/{clone_id}`、
  `POST /api/genes/known/write/bulk`、`GET /api/genes/known/write/changes`（admin）、
  `GET /api/genes/known/write/whoami`。支持 `dry_run`、批量 ≤500 行、2MB body、60 req/min/key 软限流。
- **审计**：`known_gene_change_log` 记录 action/before/after/actor/client_ip/reason，与主表写同事务；
  用 `scripts/known_gene_admin.py delete --clone-id N --confirm <gene_id> --reason ...` 可安全删除（会写审计）。
- **批量更新流程**：Excel → `scripts/known_genes_v2055/extract.py`（JSONL）→
  `scripts/known_gene_push.py --jsonl ... --dry-run`（预演）→ 加 `--commit` 批量 upsert。
- **上线顺序**：先 root DDL → 再 `git pull + restart` → 再建 key；完整说明/curl/错误码/密钥轮换见
  `docs/known_genes/WRITE_API.md`。
- **不要**把 raw key 写进代码/前端/URL/日志；泄露立即 `known_gene_api_key.py revoke --id` 并重建。
