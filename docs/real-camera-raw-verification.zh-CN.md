# 实拍 RAW 读取测试

2026-10-27 使用用户提供的相机 RAW 目录进行本地测试。目录有 1,272 个文件、
501 个机型目录和 22 种扩展名；本次按格式、传感器类型和压缩方式选取 23 份，
不是对整个目录的兼容性认证。原件只读，测试后再次核对 SHA-256，23 份均未改变。
源照片、预览和相机配置不打包分发。

## 结果

21 份可读取，覆盖 16 种格式。每份分别经 RawTherapee 5.12 输出浮点 sRGB／D65
和线性 AP1／D60，检查 RGB 类型、有限值、尺寸和输出 ICC，再编码为 ACEScct。

| 样本组 | 结果 |
| --- | --- |
| Canon 7D II CR2、R6 CRAW CR3 | 通过；包括实际只有 2736×1824 的小尺寸 RAW，未误用 EXIF 中较大的 JPEG 尺寸 |
| Nikon D850 无损压缩 NEF、Z6 III High Efficiency DX NEF | 通过 |
| Sony A7S ARW | 通过 |
| Fujifilm X-T30 II X-Trans、X-S10 Bayer 压缩 RAF | 通过 |
| Panasonic LX7 RW2、Olympus TG-5 ORF、E-M5 II ORI、OM-3 ORF | 通过；LX7 样本本身是小幅 RAW，不能用整款相机标称像素判断本文件尺寸 |
| Pentax K-5 II s PEF、Samsung NX500 SRW、Ricoh GR III DNG | 通过 |
| Blackmagic Micro Cinema Camera DNG | 通过 |
| Hasselblad H5D-40 FFF、CFV-50c 3FR、Leaf Credo 40 IIQ | 通过；包含约 4,000–5,300 万像素文件 |
| Sigma SD1 Merrill X3F、Canon CHDK CRW | 可读取并通过输出桥接，但 RawTherapee 明确报告相机白平衡不可用，使用其原生回退 |
| Nikon 1 S2，EXIF Orientation=6 | 通过；两条输出均正确转为 3070×4600 的竖幅 |
| Arri Alexa Mini ARI | 正式入口尚不支持。5.12 CLI 默认过滤该扩展名；诊断用 `.raw` 临时别名可解码，但无相机白平衡，未据此开放正式导入 |
| Sony A7 V 的 `apcs_compressed_hq.ARW` 样本 | 5.12 实际返回 Error loading file；未替换为内嵌 JPEG。不将这一份失败推广为该机型所有压缩格式的结论 |

相机白平衡回退写入实际输入记录，胶片条文件名旁显示「白平衡回退」。两条路径
仍共享同一项 RawTherapee 设置；不把回退值称作已验证的 AsShot。

## 独立颜色交接检查

在每个成功文件上均匀取最多 256×384 个空间位置，共 2,064,384 点。用独立的
colour-science AP1→XYZ、Bradford 和 IEC sRGB 数学转换，与 RawTherapee 的 sRGB
分支比较；两边都在显示比较时限制到 0–1。指标取每点三个通道的最大绝对差。

- 全部抽样点在 2/255 内；最大差 0.4622 个 8 位码值。
- 各文件 P99 的最大值为 0.0441 个码值。
- ACEScct 与独立分段公式一致；编码前不额外裁切。
- 首次双路径开发约 0.78–17.30 秒，缓存读回约 0.03–0.91 秒，均为本机、本批文件
  的观测值；没有以不同机型的平均时间宣称通用性能。

这项检查验证实际 RAW 的读取、输出空间和桥接编码。它不是相机色卡校准精度、
真实胶片准确度或最终胶片 LUT 误差测试；空间抽样也不是整幅每个像素的误差保证。
这些文件的原场景照明、物体反射率和相机标定真值并不齐全。

## 实际发现并修正的问题

1. 应用漏掉 ORI、CRW、X3F；三种均已用真实文件确认引擎能读，补入导入格式。
   文件选择器现在使用后端公布的扩展名，避免前后端各维护一份而再次遗漏。
2. 保存的原件使用 `.source` 后缀。以前命中开发缓存时正常，缓存清理后，CLI 会先
   按扩展名过滤，导致导出失败。现在根据保留的原始文件名建立临时、只读的带正确
   扩展名别名，开发后移除；原件保持不变。失败测试先复现，再通过实调用验证修复。
3. 原记录将请求 Camera 白平衡统一描述为 AsShot。现在解析引擎明确报告的不可用
   情况，分别记录请求和实际回退，不再隐去这一差别。

## 重现

`experiments/validate_camera_raw.py` 接受 RAW 根目录和本地选择 JSON；选择记录只
需要相对于该目录的 `relative_path`，可附 EXIF 信息。原始位置不写入公开文档。

```sh
python -m experiments.validate_camera_raw --source /path/to/raw --selection selection.json
```

逐文件哈希、设置、尺寸、耗时、误差及失败日志在忽略的
`artifacts/real-raw-review/report.json`，缩略图也只保留在本地。自动回归还覆盖无缓存
`.source` 原件重建、扩展名声明、白平衡回退记录和文件选择器选项。

## 界面及批量导出复测

通过实际文件选择器同时导入 ORI、X3F、CRW 和失败的 Sony 样本，前三张成功，
失败文件单独报错；切图、缩略图及重新载入后的顺序恢复正常。随后移走这一个独立
测试工作区的派生 RAW 缓存，再从保存的 `.source` 原件重新开发并批量导出：3/3
成功，尺寸分别为 4632×3464、4806×3204、4632×3472，ZIP CRC、图像哈希与嵌入
ICC 检查通过。原始用户工作区没有混入测试照片。

同一张 X3F 分别进入三条胶片流程，A 的实际预览图像字节保持一致，B 随流程改变；
APD 默认 ACES 2.0，光学放大默认色度转换。X3F 的白平衡回退在胶片条旁可见。
这检验应用接线和实际文件处理，不是对胶片颜色的物理验证。

最终回归：205 项 Python 测试、47 项 JavaScript 界面逻辑测试通过。清缓存后真实
RAW 导出的读回摘要保留在 `artifacts/real-raw-review/batch-rebuild-verification.json`。
