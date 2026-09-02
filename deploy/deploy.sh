#!/usr/bin/env bash
# 畅学社区 MVP 部署脚本（S12 交付文档任务④；目标：Linux + MySQL + Uvicorn + Nginx）
# 用法：在服务器上 bash deploy.sh 首次部署；之后 git pull && bash deploy.sh 更新
set -euo pipefail

APP_DIR=/opt/changxue
BACKEND=$APP_DIR/backend

echo "==> 1/6 系统依赖（MySQL 客户端开发库为 pymysql 编译依赖非必需，此处装常用包）"
command -v nginx >/dev/null || { apt-get update && apt-get install -y nginx; }

echo "==> 2/6 后端 venv + 依赖"
cd "$BACKEND"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt 2>/dev/null || .venv/bin/pip install fastapi uvicorn sqlalchemy alembic pymysql pydantic-settings python-jose passlib bcrypt pillow python-multipart apscheduler httpx

echo "==> 3/6 生产配置（复制 .env.prod 并按需修改数据库口令/JWT 密钥）"
if [ ! -f .env ]; then
  cat > .env <<'EOF'
APP_ENV=prod
DATABASE_URL=mysql+pymysql://changxue:CHANGE_ME@127.0.0.1:3306/changxue?charset=utf8mb4
JWT_SECRET=CHANGE_ME_32BYTES_MINIMUM_SECRET
UPLOAD_DIR=./uploads
EOF
  echo "!! 已生成 .env 模板，请修改 CHANGE_ME 后重新执行"
  exit 1
fi

echo "==> 4/6 MySQL 建库 + Alembic 迁移（SQLite→MySQL 结构一致，数据迁移见 PROJECT_STATE S12 记录）"
mysql -e "CREATE DATABASE IF NOT EXISTS changxue CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed.py   # 12 标签 seed 幂等

echo "==> 5/6 前端构建"
cd "$APP_DIR/frontend"
command -v npm >/dev/null || { curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs; }
npm ci --legacy-peer-deps
npm run build

echo "==> 6/6 systemd + nginx"
cp "$APP_DIR/deploy/changxue.service" /etc/systemd/system/
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/conf.d/changxue.conf
systemctl daemon-reload
systemctl enable --now changxue
nginx -t && systemctl reload nginx

echo "部署完成：curl http://127.0.0.1/api/health 验证"
