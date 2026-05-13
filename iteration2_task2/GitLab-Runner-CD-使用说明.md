# GitLab Runner CD 使用说明

本项目迭代二任务二的 CD 以公网 GitLab 镜像仓库为入口：

```text
https://git.nju.edu.cn/2026seiii/2026seiii-045-1145
```

内网仓库同步到该公网仓库后，由 GitLab Runner 执行 `.gitlab-ci.yml`。当前 CD 不依赖 Jenkins，也不要求 Runner 拥有 Docker 特权模式；Runner 只负责通过 SSH 连接部署机，部署机本地完成 `docker build` 和 `docker compose up`。

## 流程

1. GitLab Runner 拉取公网镜像仓库代码。
2. 执行后端 CI：安装依赖并编译检查 `backend/app`。
3. 执行前端 CI：`npm ci` 和 `npm run build`。
4. 手动触发 `deploy-staging`。
5. Runner 通过 SSH 登录部署机。
6. 部署机拉取指定分支代码到 `/opt/agent-eval/repo`。
7. 部署机用当前 commit 短 SHA 构建本地镜像：
   - `agent-eval-backend:<commit>`
   - `agent-eval-frontend:<commit>`
8. 部署机在 `/opt/agent-eval/staging` 生成 Compose 运行配置并启动：
   - PostgreSQL
   - Redis
   - FastAPI backend
   - Celery worker
   - Nginx frontend
9. 脚本检查后端 `/health` 和前端 Nginx 首页，失败时输出容器日志并使流水线失败。

## GitLab CI/CD Variables

必填变量：

```text
DEPLOY_HOST=部署机 IP 或域名
DEPLOY_USER=部署机 SSH 用户
DEPLOY_PASSWORD=部署机 SSH 密码
```

也可以不用密码，改用私钥：

```text
DEPLOY_HOST=部署机 IP 或域名
DEPLOY_USER=部署机 SSH 用户
DEPLOY_SSH_PRIVATE_KEY=私钥内容
```

兼容之前尝试中的变量名：

```text
SSH_HOST
SSH_USER
SSH_PASSWORD
```

可选变量：

```text
DEPLOY_PORT=22
DEPLOY_ROOT=/opt/agent-eval
DEPLOY_ENV=staging
FRONTEND_PORT=80
BACKEND_PORT=8000
POSTGRES_PORT=5432
```

## 部署机要求

部署机需要提前安装：

```bash
git --version
docker --version
docker compose version
```

部署机还需要能访问公网 GitLab 仓库：

```bash
git ls-remote https://git.nju.edu.cn/2026seiii/2026seiii-045-1145.git HEAD
```

首次部署会创建：

```text
/opt/agent-eval/repo
/opt/agent-eval/staging
/opt/agent-eval/staging/.env
/opt/agent-eval/staging/.deploy.env
```

`.env` 只在首次部署时从 `.env.example` 创建，后续部署不会覆盖。需要启用真实 LLM Judge 时，在部署机上编辑：

```text
/opt/agent-eval/staging/.env
```

## 触发方式

1. 推送或镜像同步代码到公网 GitLab。
2. 打开 GitLab 项目的 CI/CD Pipeline。
3. 等待 `backend-ci` 和 `frontend-ci` 成功。
4. 手动运行 `deploy-staging`。
5. 成功后访问：

```text
http://<DEPLOY_HOST>:<FRONTEND_PORT>
http://<DEPLOY_HOST>:<BACKEND_PORT>/health
```

## 回滚

每次部署使用 commit 短 SHA 作为镜像标签。需要回滚时，在 GitLab 中找到旧 commit 对应的 pipeline，重新运行 `deploy-staging` 即可重新构建并部署该版本。
