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
