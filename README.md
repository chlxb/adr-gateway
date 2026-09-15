# ADR 轻量接口封装

Docker 部署见 [DOCKER.md](DOCKER.md)。原生 Python 启动方式继续可用。

保留文档中的两个控制、采集接口，增加结果文件下载，调用顺序不变：

1. POST /api/v1/xray/high-voltage，{"enabled": true}
2. POST /api/v1/capture，等待采集、校正、AI 识别和保存完成。
3. 无论采集成功或失败，都 POST /api/v1/xray/high-voltage，{"enabled": false}

没有 taskId、数据库、health、ZIP 或任务管理接口。ADR 负责采集并发控制，忙时原样返回 409；关闭高压不等待采集。封装层不自动重试、不自动开启或关闭高压。

## 启动

在本目录执行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[test]"
./start.ps1
```

修改 config/gateway.toml 的 ADR 地址、固定存储目录、监听地址和端口。相对存储目录按本项目根目录解析。局域网访问可将 host 改成设备网卡地址或 0.0.0.0。此服务与 ADR 一样无鉴权，应部署在设备局域网。

## capture 参数与文件

framePeriodSeconds、integrationCount、overwriteExisting、generateMockDefect 保持文档含义，原样转给 ADR，不添加模拟缺陷默认值。

- 有 savePath：只取文件名，保存到 storage_root，调用方传入的目录不生效。
- 未传 savePath：自动生成唯一 film_<随机编号>.tif 文件名，编号仅用于避免重名，无任务含义。
- savePath 为 ""：保留原文档的“只采集不保存”行为。
- 保存目录不存在时自动创建；不建立采集子目录。
- 同名覆盖仍由 overwriteExisting 控制，默认 false，由 ADR 校验。
- TIFF 与同名 _ai.xml（AI 标注）、.xml（人工复核标注）由 ADR 写入同一目录。没有缺陷时 ADR 可能只保存底片。

保留 ADR 的 HTTP 状态和原有响应字段，成功 capture 额外返回 downloads；savedFilePath 是实际保存路径。缺陷信息仍在 XML 中；“评定”沿用 ADR 的 AI 识别，不新增 RT 等级计算。连接失败、超时或非法响应时，封装层返回文档风格的错误 JSON。请求与完整 ADR 响应打印在服务端日志。

## 下载底片与评定结果

新增 GET /api/v1/files/{filename}，以附件方式传输 TIFF/DCM/XML 原文件，无需共享目录。capture 成功响应增加以下字段（其余字段不变）：

```json
{
  "downloads": {
    "film": {"filename": "film_001.tif", "url": "/api/v1/files/film_001.tif", "sizeBytes": 123456},
    "ai": {"filename": "film_001_ai.xml", "url": "/api/v1/files/film_001_ai.xml", "sizeBytes": 1200},
    "humanReview": {"filename": "film_001.xml", "url": "/api/v1/files/film_001.xml", "sizeBytes": 1200}
  }
}
```

url 相对于封装服务的域名和端口，不要再拼接 /api/v1。缺失文件对应项为 null；未保存时三项均为 null。关闭高压后再下载即可；下载不会调用 ADR 或操作高压。不支持目录浏览、任意路径或其他类型文件，文件不存在时返回 404。地址指向当前文件，人工更新 XML 后再次下载得到更新内容；同名覆盖后也会下载覆盖后的文件。

## WeldOS 对接

当前 WeldOS 已按上述顺序调用，但采集后还校验 savedFilePath，并通过文件系统读取结果。

当前配置 storage_root 与这台电脑上的 WeldOS 默认 ADR_RT_SAVE_ROOT / ADR_RT_READ_ROOT 一致。因此同机部署可仅将 config/adr-rt.env 的 ADR_RT_BASE_URL 改为：

```text
http://127.0.0.1:18081/api/v1
```

此项目没有自动修改 WeldOS 配置。

如果封装层部署在另一台设备电脑，需要同时满足：
- storage_root 与 WeldOS 的 ADR_RT_SAVE_ROOT 指向同一设备端路径；
- WeldOS 的 ADR_RT_READ_ROOT 能通过共享目录读取这些文件。

已有共享映射正确时也只需换 URL。如果要取消共享目录，需要将 WeldOS 的结果导入改成读取 capture.downloads 并通过 HTTP 下载后导入。本次只增加封装层下载功能和示例，未修改 WeldOS 的结果导入逻辑。

## 验证

```powershell
.venv/Scripts/python.exe -m pytest -q
```

测试使用模拟 ADR，不操作硬件。手动真实流程示例：

```powershell
.venv/Scripts/python.exe examples/full_flow.py --operate-hardware --mock
```

--mock 仅模拟缺陷，仍会开启高压并实际采集，且需要 ADR 启用模拟缺陷配置。
