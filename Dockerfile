# 基于官方 Python 镜像
FROM python:3.13-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt ./

# 安装依赖
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 复制项目代码
COPY . .

# 暴露 SSE 服务端口
EXPOSE 3000

# 默认启动 SSE 服务，监听所有网卡
CMD ["python", "main.py", "--sse", "--bind", "0.0.0.0", "--port", "3000"]
