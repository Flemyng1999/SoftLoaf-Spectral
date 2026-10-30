# T7 上的 RAW 与高光谱数据

2026-10-28，当前工作区按用户要求将 RAW 和高光谱处理数据保存在
`/Volumes/T7 Touch/SoftLoaf-Spectral/`。个人设置在忽略的
`local/storage-settings.json` 中；代码、配方工作区、备份和普通报告保留在项目。
此设置不改变照片的色彩空间、胶片曲线或 LUT 数值定义。

## 迁移范围

迁移的是高光谱源文件、数值材料、RAW 原件副本、RAW 开发缓存、浮点预览、
导出数据和相关图像处理结果。第一批约 23.18 GiB、1,735 个文件，第二批图像
数据约 1.32 GiB、1,965 个文件；旧测试临时目录中的 202 个 RAW/数组文件另约
1.02 GiB，另迁移 3 个历史高光谱数组。合计 3,905 个文件、25.53 GiB。代码、可执行运行时、`workspace.json`、配方备份、普通 Markdown/JSON
报告和 UI/品牌截图没有整目录搬走。原始相机素材目录本来就在 T7，保持只读。

每个数据文件先复制到 T7，计算 SHA-256 并读回核对，确认后再以原路径的兼容
链接替换内置盘副本。原有程序、配方和报告引用仍可用。校验清单仅保存在 T7：

- `data-migration-manifest.json`
- `image-data-migration-manifest.json`
- `data/test-data-migration-manifest.json`
- `archive-data-migration-manifest.json`

迁移按数据目录/文件的明确清单执行，没有移动整个 `local` 或 `artifacts`。

## 后续写入

`DataStorage` 在启用此个人设置时验证卷仍已挂载，检查目标确在该卷内。
RAW 原件、开发缓存、导入临时文件、预览与导出按项目相对路径落入 T7 的
`data/`；原路径保留兼容链接。普通工作区元数据仍保留本地。
`TMPDIR` 和 Python 临时目录设为 T7 的 `tmp/`。pytest 的默认临时目录和
当前 CTest 配置也使用 T7。原生 WebKit 窗口使用非持久化数据存储，图像响应
同时带 `Cache-Control: no-store`。

T7 未连接时，应用明确停止读取/处理，不创建内置盘替代缓存。
现有未迁移目录不会被程序静默移动或覆盖。仅初始化空的数据目录/兼容链接。

T7 文件系统不支持 UNIX 符号链接时，RT 所需的带 RAW 扩展名临时别名使用
同一外置盘上的校验副本。临时 RAW 在关闭写入后才交给引擎；外置盘交接时
完整重验文件哈希，不依赖粗粒度时间戳缓存。不会因换盘跳过源文件、ICC 或
输出数据的完整性检查。

## 验证

`tests/test_external_storage.py` 检查外置落点、工作区保留、拒绝覆盖与离线
不回退；RAW 实际导入、缓存、完整导出与三条 Metal 管线的完整测试均在 T7
临时目录运行：318 个 Python 测试、64 个 JS 测试和 2 个 CTest 检查通过。
卷断开通过模拟验证，没有实际卸载用户磁盘。

原生 APP 已重新启动并回读，保留 3 份配方、没有恢复警告，像素计算使用 Metal。
实际 RAW 界面导入、调整和重载通过；3396×2262 原尺寸图像导出逐像素与 ICC
读回一致。原件、RAW 缓存、导入临时文件、浮点预览、成片、材料和高光谱源
目录的最终解析路径均位于 T7。个人检查报告在
`artifacts/raw-superpixel-final/t7-export-readback.json` 和 `native-t7-readback.json`。

## 两阶段开发后的更新

RAW half/full 阶段现由 ledger 保留，不再参与自动 LRU 淘汰。新增显示成片
缓存同样通过 DataStorage 落在 T7；原生 WebKit 的图像资源缓存仅在内存中。
图库恢复不再逐张读取原始 RAW；预览第一次使用前校验。应用管理的不可变
缓存会复用本进程的已验证文件身份，变动则重新校验；这替代前述每次 RAW
交接强制重算所有文件哈希的旧策略。见 [缓存约束](photo-cache.zh-CN.md)。
