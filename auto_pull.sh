#!/bin/bash
# WheatOmics FastAPI backend — auto-pull from Gitee on webhook.
#
# Hardened version: GIT_TERMINAL_PROMPT=0 disables the interactive password
# prompt so any auth failure surfaces immediately rather than hanging the
# webhook. All output (stdout + stderr) is captured to git_update.log so
# silent failures are diagnosable. The script never embeds credentials —
# configure SSH deploy key (preferred) or use a credential helper for HTTPS.

# 配置路径与分支
PROJECT_DIR="/var/www/FastAPI_backend_Port8000"
LOG_FILE="$PROJECT_DIR/git_update.log"
BRANCH="main"  # 如果默认分支是 master，请修改此处

# 进入项目目录
cd "$PROJECT_DIR" || { echo "[$(date '+%F %T')] FATAL: cannot cd to $PROJECT_DIR" >> "$LOG_FILE"; exit 1; }

# 禁用交互式凭据询问——凭据失效必须快速失败，不能 hang webhook
export GIT_TERMINAL_PROMPT=0

TIMESTAMP() { date "+%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(TIMESTAMP)] $*" >> "$LOG_FILE"; }

# 入口分隔符
echo "--------------------------------------------------" >> "$LOG_FILE"
log "auto_pull.sh invoked (origin=$(git remote get-url origin 2>/dev/null || echo 'unset'), branch=$BRANCH)"

# 1) 探测远程（捕获错误到 log）
if ! git fetch origin "$BRANCH" >> "$LOG_FILE" 2>&1; then
    log "FETCH FAILED (exit=$?). Check SSH key / HTTPS credentials."
    exit 1
fi

# 2) 比较 hash
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ]; then
    log "no update (HEAD already at $LOCAL)"
    exit 0
fi

# 3) 拉取
log "detected update: $LOCAL -> $REMOTE"
if ! git reset --hard "origin/$BRANCH" >> "$LOG_FILE" 2>&1; then
    log "RESET FAILED (exit=$?)"
    exit 1
fi
log "pull complete: HEAD is now at $REMOTE"
echo "--------------------------------------------------" >> "$LOG_FILE"

# 注意: webhook 不会重启 uvicorn — Python 改动需要手动重启:
#   pkill -f 'uvicorn main:app'; sleep 1
#   setsid nohup /home/fei/mambaforge/envs/zjw/bin/uvicorn main:app \
#     --host 0.0.0.0 --port 8000 > /var/www/FastAPI_backend_Port8000/api.log 2>&1 < /dev/null &
#   disown
# 静态文件改动 (app/static/**) 不需要重启即可生效。