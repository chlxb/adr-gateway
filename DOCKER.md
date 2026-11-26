# Docker 快速部署

本镜像仅包含 adr-gateway，不包含 WeldOS 或 ADR。推荐在 ADR 所在 Windows 电脑使用 Docker Desktop 的 Linux containers。

在本目录执行（已有 .env 时直接编辑，不要覆盖）：

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force D:/ADR_Data
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose logs -f
```

修改 .env：

- ADR_BASE_URL：容器访问 ADR 的地址，默认 http://host.docker.internal:18080/api/v1。ADR 必须监听容器可达的宿主机地址，不能只监听 Windows 回环地址；按需配置防火墙。
- ADR_SAVE_ROOT：ADR 保存底片的 Windows 路径，如 D:/ADR_Data。
- CAPTURE_HOST_DIR：挂载进容器的宿主机目录，与上面必须是同一物理目录。
- GATEWAY_PORT：中转服务端口，默认 18081。
- GATEWAY_BIND_IP：宿主机监听地址，默认 0.0.0.0；仅本机使用时设置 127.0.0.1。
- ADR_GATEWAY_IMAGE：默认公开镜像 ghcr.io/chlxb/adr-gateway:main，可替换为固定版本或 digest。

在 ADR 与 Docker Desktop 同机的 Windows 环境中，仅使用 compose.yaml 即可启动：ADR_SAVE_ROOT 和 CAPTURE_HOST_DIR 均默认 D:/ADR_Data，目录不存在时自动创建并挂载到 /data。默认连接 host.docker.internal:18080/api/v1，对外提供 18081 端口，不需要源码或本地构建。.env 是可选覆盖配置；换目录时两项要对应同一物理文件夹。其他操作系统或 ADR 不同机时需要调整路径和挂载。

如需本地构建，执行 docker build --target runtime -t adr-gateway:local .，然后将 .env 中 ADR_GATEWAY_IMAGE 改为 adr-gateway:local，执行 docker compose up -d --pull never。不要对本地镜像执行 compose pull。

ADR 保存 D:/ADR_Data/film.tif，容器挂载 D:/ADR_Data 到 /data，再通过 /data/film.tif 提供下载。savedFilePath 仍为 ADR 的 Windows 路径，接口和原有调用顺序不变。原始结果保留在宿主机，更新容器不会清除。

如果 Docker 在另一台电脑，必须先将 ADR 输出目录挂载到 Docker 宿主机，然后设置 CAPTURE_HOST_DIR；单纯设置 IP 不会同步文件。优先同机部署，避免网络共享。

WeldOS 使用 http://设备电脑IP:18081/api/v1。不要同时运行占用同端口的原生中转服务。

## 验证

```powershell
docker build --target test -t adr-gateway:test .
python ../example/test_adr.py --base-url http://127.0.0.1:18081/api/v1 --validation-only
```

镜像测试只使用 mock ADR；validation-only 仅发送缺参请求。完整采集与下载测试使用 ../example/test_gateway.py，会真实操作高压和采集。

## 镜像发布与更新

仓库为 https://github.com/chlxb/adr-gateway，工作流为 .github/workflows/build.yml。

- PR：运行 Linux 模拟测试并构建，不发布镜像。
- 推送 main、develop、test/*：测试通过后发布分支标签与 sha-<完整提交号>。
- 推送 v* 标签：校验该提交属于 main 历史后发布同名版本，例如 v0.1.0。
- Actions 页面可手动运行。仅 chlxb/adr-gateway 仓库允许发布。

目标固定为 ghcr.io/chlxb/adr-gateway。镜像现已由维护者改为公开，部署拉取不需要登录。此前工作流包含仅允许 private 的检查，如仍保留，该检查会阻止后续向公开包发布；这与 Compose 启动无关。

Actions 使用自动提供的 GITHUB_TOKEN（packages:write），无需添加个人令牌到工作流。若已有包无法推送，请在该包 Settings → Manage Actions access 中授权 chlxb/adr-gateway 仓库。代码提交并推送后才触发线上工作流，本次配置本身不会上传镜像。

首次发布 main 后，设置 ADR_GATEWAY_IMAGE=ghcr.io/chlxb/adr-gateway:main；正式部署建议使用已发布的固定版本（如 :v0.1.0）或 digest。第一次下载私有镜像前执行 docker login ghcr.io -u chlxb，在密码提示中输入带 read:packages 权限的 Personal Access Token (classic)，不要输入 GitHub 登录密码或提交令牌到代码仓库。然后执行：

```powershell
docker compose pull
docker compose up -d --no-build
```

私有镜像需要先登录镜像仓库。更新前先完成当前采集流程并关闭高压。

运行时 RT_GATEWAY_ADR_BASE_URL、RT_GATEWAY_STORAGE_ROOT、RT_GATEWAY_ADR_SAVE_ROOT、RT_GATEWAY_HOST、RT_GATEWAY_PORT 环境变量优先于 TOML。原生启动未设置 adr_save_root 时仍使用同一本地目录。
