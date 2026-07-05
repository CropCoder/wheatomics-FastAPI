# WheatOmics FastAPI 后端运维记录

> 本文件记录项目迭代中积累的操作经验与常见问题，每次迭代后更新。

---

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

```bash
pkill -f 'uvicorn main:app'
sleep 1
nohup /home/fei/mambaforge/envs/zjw/bin/uvicorn main:app --host 0.0.0.0 --port 8000 > api.log 2>&1 &
```

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

---

## 四、配置与路径速查

### 数据库配置（`app/core/config.py`）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DB_HOST` | `localhost` | MySQL 主机 |
| `DB_PORT` | `3306` | MySQL 端口 |
| `DB_USER` | `wheatomics_user` | MySQL 用户 |
| `DB_PASSWORD` | `wheatomics115599` | MySQL 密码 |
| `DB_GENEFUNC` | `Genefuncdb` | 基因功能数据库 |
| `DB_ORTHOFINDER` | `orthofinder_n` | OrthoFinder 数据库 |
| `DB_PPI` | `wheatPPIdb` | 蛋白质互作数据库 |
| `BLAST_DB_PATH` | `/var/www/html/getfasta/blastdb` | BLAST 数据库路径 |
| `ORTHOFINDER_BASE_DIR` | `/var/www/html/orthefind/Results_Jun24` | OrthoFinder 结果根目录 |
| `PRIMERSERVER2_CONFIG_PATH` | `/var/www/html/PrimerServer2/config.ini` | PrimerServer2 配置文件 |

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
pkill -f 'uvicorn main:app'
sleep 1
nohup /home/fei/mambaforge/envs/zjw/bin/uvicorn main:app --host 0.0.0.0 --port 8000 > api.log 2>&1 &
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

第三步：重启 uvicorn（**关键**：webhook 只 git pull，不重启进程，`main.py` 改动不会自动生效）：

```bash
pkill -f 'uvicorn main:app'
sleep 1
nohup /home/fei/mambaforge/envs/zjw/bin/uvicorn main:app --host 0.0.0.0 --port 8000 >> api.log 2>&1 &
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
```

**全部 ✓ 才算这个迭代完成**。
