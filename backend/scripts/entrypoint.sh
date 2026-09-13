#!/bin/sh
# 后端服务启动脚本
# 功能：1. 等待数据库就绪  2. 运行数据初始化  3. 启动 uvicorn

set -e

# stdout 接到 docker logs 这类管道时是**块缓冲**，后台任务（巡检调度器、离线监测、
# 升级扫描）用 print() 打的日志会攒在缓冲区里迟迟不出现——而「凌晨到底跑没跑」
# 恰恰是这些任务唯一的外部可观测信号。设为行缓冲后实时可见。
export PYTHONUNBUFFERED=1

DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-fire}"
DB_PASS="${DB_PASS:-fire}"
DB_NAME="${DB_NAME:-fire_alarm_sys}"

REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

PYTHON="/opt/venv/bin/python3"

echo "[*] 校验 Python 依赖是否完整..."
$PYTHON -c "
import importlib
import sys

# 关键运行时依赖清单；当 requirements.txt 新增包而镜像未重新构建时，
# 此处会提前失败并给出明确提示，避免服务进入 ModuleNotFoundError 崩溃循环。
DEPS = [
    'fastapi',
    'uvicorn',
    'pydantic',
    'pydantic_settings',
    'email_validator',
    'sqlalchemy',
    'asyncpg',
    'greenlet',
    'alembic',
    'jose',
    'passlib',
    'bcrypt',
    'redis',
    'multipart',
    'openpyxl',
    'PIL',
    'fitz',
    'user_agents',
]

missing = []
for name in DEPS:
    try:
        importlib.import_module(name)
    except ImportError as exc:
        missing.append((name, str(exc)))

if missing:
    print('[❌] 依赖校验失败，当前镜像缺少以下包：')
    for name, exc in missing:
        print(f'  - {name}: {exc}')
    print()
    print('可能原因：backend/requirements.txt 已新增依赖，但镜像未重新构建。')
    print('解决方法：在宿主机执行 docker compose build backend，然后重新启动服务。')
    sys.exit(2)

print('[✓] 依赖校验通过')
"

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
