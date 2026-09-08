# 消防监控管理系统 - 前端服务
# 多阶段构建：Node 构建 → nginx 托管

# ===== 构建阶段 =====
FROM node:20-alpine AS builder

# 替换 Alpine 源为清华镜像
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories

WORKDIR /app

# 配置 npm 使用淘宝镜像
RUN npm config set registry https://registry.npmmirror.com

# 先复制依赖文件，利用缓存层
COPY package.json .

# 构建阶段只需生产依赖 + 构建工具，剔除测试相关大包（jsdom/vitest）
RUN node -e "const fs=require('fs'), pkg=JSON.parse(fs.readFileSync('package.json')); delete pkg.devDependencies.jsdom; delete pkg.devDependencies.vitest; fs.writeFileSync('package.json', JSON.stringify(pkg, null, 2));" \
    && npm install --no-audit --no-fund --maxsockets 1

# 复制源码并构建
COPY . .
RUN npm run build

# ===== 运行阶段 =====
FROM nginx:alpine

# 替换 Alpine 源为清华镜像
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories

# 复制构建产物到 nginx 目录
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制自定义 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
