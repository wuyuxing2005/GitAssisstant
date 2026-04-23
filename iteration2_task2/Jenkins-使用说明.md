# Jenkins CI/CD 使用说明

## 1. 已实现内容

- `iteration2_eval/Jenkinsfile`：声明式流水线
- 仅当 `iteration2_eval/` 子目录有变更时继续执行 CI/CD 阶段
- `ci/backend_ci.sh`：后端安装依赖并做语法校验
- `ci/frontend_ci.sh`：前端安装依赖并构建
- `frontend/Dockerfile`：构建前端静态站点镜像
- `backend/Dockerfile`：构建 FastAPI 服务镜像
- `deploy/docker-compose.yml`：部署到服务器的编排模板
- `ci/deploy_remote.sh`：通过 SSH 远程发布

## 2. 流水线执行流程

1. 拉取代码
2. 执行后端 CI
3. 执行前端 CI
4. 构建前后端 Docker 镜像
5. 可选：推送镜像到镜像仓库
6. 可选：通过 SSH 登录部署机执行 `docker compose up -d`

## 3. Jenkins 前置条件

建议 Jenkins 运行在 Linux Agent 上，并安装：

- Git
- Docker
- Node.js 20+
- Python 3.11+

建议安装 Jenkins 插件：

- Pipeline
- Git
- Credentials Binding
- SSH Agent 或 SSH Credentials
- ANSI Color

## 4. Jenkins 中如何创建任务

推荐使用 **Pipeline** 或 **Multibranch Pipeline**：

1. 新建 Jenkins Job
2. 选择 `Pipeline`
3. 在 `Pipeline script from SCM` 中选择你的 Git 仓库
4. Script Path 填 `iteration2_eval/Jenkinsfile`
5. 保存后点击 `Build with Parameters`

## 5. 只在子目录变化时触发

因为 Git 仓库根目录是 `Desktop/code`，而当前项目在 `iteration2_eval` 子目录，建议在 Jenkins Job 中增加路径过滤：

### Pipeline Job

1. 打开 Job 配置
2. 在 Git SCM 配置中展开 **Additional Behaviours**
3. 添加 **Polling ignores commits in certain paths**
4. Included Regions 填：

```text
iteration2_eval/.*
```

这样 Jenkins 轮询 SCM 时，只会因为 `iteration2_eval/` 下的提交触发构建。

### Multibranch Pipeline

如果使用 Multibranch Pipeline，可以在分支源的构建策略里配置路径过滤；不同插件界面名称略有差异，目标同样是只包含：

```text
iteration2_eval/.*
```

`Jenkinsfile` 内部也做了二次保护：如果构建已经被 webhook 触发，但本次提交没有修改 `iteration2_eval/`，流水线会标记为 `NOT_BUILT` 并跳过后续 CI/CD 阶段。

## 6. 需要配置的凭据

### Docker 仓库凭据

- Jenkins 凭据 ID：`docker-registry-credentials`
- 类型：`Username with password`

### 服务器 SSH 凭据

- Jenkins 凭据 ID：`deploy-ssh-key`
- 类型：`SSH Username with private key`

## 7. 需要修改的变量

在 `Jenkinsfile` 里按你的环境修改：

- `PROJECT_DIR`
- `REGISTRY_HOST`
- `REGISTRY_NAMESPACE`
- `DEPLOY_HOST`
- `DEPLOY_PATH`

例如：

```groovy
REGISTRY_HOST = 'harbor.mycompany.com'
REGISTRY_NAMESPACE = 'agent-eval'
DEPLOY_HOST = '192.168.1.20'
DEPLOY_PATH = '/opt/agent-eval'
```

## 8. 如何使用

### 只跑 CI

- `PUSH_IMAGES = false`
- `DEPLOY_ENV = none`

效果：

- 校验后端
- 构建前端
- 构建 Docker 镜像
- 不推镜像，不部署

### 跑完整 CI/CD

- `PUSH_IMAGES = true`
- `DEPLOY_ENV = staging` 或 `production`

效果：

- 执行 CI
- 构建并推送镜像
- SSH 到服务器部署

## 9. 服务器侧准备

部署机需要提前安装：

- Docker
- Docker Compose

并确保 Jenkins SSH 用户对 `${DEPLOY_PATH}` 有写权限。

如果你不想在部署时交互执行 `docker login`，建议在服务器上提前登录镜像仓库，或改为使用机器人账户和非交互登录方式。

## 10. 推荐优化

- 为前后端补单元测试，让 CI 不只是做构建
- 把 `REGISTRY`、`DEPLOY_HOST` 改成 Jenkins 参数或全局环境变量
- 增加 `staging` / `production` 差异化 compose 文件
- 增加回滚策略和健康检查
- 把 `DEPLOY_ENV` 对应到不同域名、端口或 compose 配置
