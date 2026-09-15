# Docker 快速部署

本镜像仅包含 adr-gateway，不包含 WeldOS 或 ADR。推荐在 ADR 所在 Windows 电脑使用 Docker Desktop 的 Linux containers。

在本目录执行（已有 .env 时直接编辑，不要覆盖）：

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force D:/ADR_Data
docker compose up -d --build
docker compose logs -f
```

修改 .env：

- ADR_BASE_URL：容器访问 ADR 的地址，默认 http://host.docker.internal:18080/api/v1。ADR 必须监听容器可达的宿主机地址，不能只监听 Windows 回环地址；按需配置防火墙。
- ADR_SAVE_ROOT：ADR 保存底片的 Windows 路径，如 D:/ADR_Data。
- CAPTURE_HOST_DIR：挂载进容器的宿主机目录，与上面必须是同一物理目录。
- GATEWAY_PORT：中转服务端口，默认 18081。

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

目标固定为 ghcr.io/chlxb/adr-gateway。新 GHCR 包默认私有；已有包发布前检查 visibility，非 private 则失败，不会自动修改可见性。不要手动将包改为 Public。私有镜像权限独立于 Git 仓库可见性。

Actions 使用自动提供的 GITHUB_TOKEN（packages:write），无需添加个人令牌到工作流。若已有包无法推送，请在该包 Settings → Manage Actions access 中授权 chlxb/adr-gateway 仓库。代码提交并推送后才触发线上工作流，本次配置本身不会上传镜像。

首次发布 main 后，设置 ADR_GATEWAY_IMAGE=ghcr.io/chlxb/adr-gateway:main；正式部署建议使用已发布的固定版本（如 :v0.1.0）或 digest。第一次下载私有镜像前执行 docker login ghcr.io -u chlxb，在密码提示中输入带 read:packages 权限的 Personal Access Token (classic)，不要输入 GitHub 登录密码或提交令牌到代码仓库。然后执行：

```powershell
docker compose pull
docker compose up -d --no-build
```

私有镜像需要先登录镜像仓库。更新前先完成当前采集流程并关闭高压。

运行时 RT_GATEWAY_ADR_BASE_URL、RT_GATEWAY_STORAGE_ROOT、RT_GATEWAY_ADR_SAVE_ROOT、RT_GATEWAY_HOST、RT_GATEWAY_PORT 环境变量优先于 TOML。原生启动未设置 adr_save_root 时仍使用同一本地目录。
