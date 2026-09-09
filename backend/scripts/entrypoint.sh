#!/bin/sh
# 后端服务启动脚本
# 功能：1. 等待数据库就绪  2. 运行数据初始化  3. 启动 uvicorn

set -e

DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-fire}"
DB_PASS="${DB_PASS:-fire}"
DB_NAME="${DB_NAME:-fire_alarm_sys}"

REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

PYTHON="/opt/venv/bin/python3"

echo "[*] 等待 PostgreSQL ($DB_HOST:$DB_PORT) 就绪..."

# 使用虚拟环境 Python 检查数据库连接
$PYTHON -c "
import sys, asyncio, asyncpg

async def wait():
    for i in range(30):
        try:
            conn = await asyncpg.connect(
                host='$DB_HOST', port=$DB_PORT,
                user='$DB_USER', password='$DB_PASS', database='$DB_NAME'
            )
            await conn.close()
            print('[✓] PostgreSQL 已就绪')
            return
        except Exception:
            print(f'[*] 等待数据库... ({i+1}/30)')
            await asyncio.sleep(1)
    print('[❌] 数据库连接超时')
    sys.exit(1)

asyncio.run(wait())
"

echo "[*] 等待 Redis ($REDIS_HOST:$REDIS_PORT) 就绪..."
$PYTHON -c "
import sys, asyncio, redis.asyncio as redis

async def wait():
    for i in range(30):
        try:
            r = redis.from_url('redis://$REDIS_HOST:$REDIS_PORT')
            await r.ping()
            await r.close()
            print('[✓] Redis 已就绪')
            return
        except Exception:
            print(f'[*] 等待 Redis... ({i+1}/30)')
            await asyncio.sleep(1)
    print('[❌] Redis 连接超时')
    sys.exit(1)

asyncio.run(wait())
"

echo "[*] 运行数据库初始化..."
$PYTHON scripts/init_data.py

echo "[*] 启动 uvicorn..."
WORKERS="${WORKERS:-1}"
if [ "$WORKERS" -gt 1 ]; then
    echo "[*] 多 worker 模式: WORKERS=$WORKERS"
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "$WORKERS"
else
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
fi
