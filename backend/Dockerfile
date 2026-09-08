# 消防监控管理系统 - 后端服务
# 多阶段构建，pip 使用清华镜像

# ===== 构建阶段 =====
FROM python:3.10-slim AS builder

# 配置 pip 使用清华镜像
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 安装编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖到虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ===== 运行阶段 =====
FROM python:3.10-slim

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 创建工作目录
WORKDIR /app

# 复制应用代码
COPY . .

# 确保启动脚本有执行权限
RUN chmod +x scripts/entrypoint.sh

# 暴露端口
EXPOSE 8000

# 默认启动命令（可被 docker-compose 覆盖）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
