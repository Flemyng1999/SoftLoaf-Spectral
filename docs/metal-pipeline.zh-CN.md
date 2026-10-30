# Metal 像素管线与 2048 px 预览

2026-10-28，Issue #8。macOS 开发版默认使用 Metal 执行图像像素计算。
预览短边上限为 2048 px，保持宽高比，短边未超过该尺寸时不缩放。
原尺寸导出读取保留的源文件，与预览使用同一条计算管线。

当前内置花卉高光谱源只有 329 × 249 px。已恢复其原生尺寸，旧版本只使用
192 px 宽。它不会被插值放大并标成真正的 2048 px 数据。分辨率足够的照片和
RAW 则会生成 2048 px 预览，胶片条的 112 × 80 缩略图仍独立保留。

2026-10-28 后续更新：RGB 输入现已使用分别选定的优化采样模型，LUT 烘焙和
插值/显示验证采用有界 GPU 分块。见[当前模型、内存与精度结果](optimized-sampling-gpu-lut.zh-CN.md)。
下文原始性能数字对应此前的线性输入近似，不能当成新局部模型的性能承诺。

## 像素计算

`core/metal/spectral.metal` 独立实现三条既有管线，没有修改材料数据、密度
定义或曝光参考。普通 RGB 输入先使用既有光谱先验；高光谱输入直接使用
反射谱。随后在每个 GPU 线程内完成感光积分和曲线求值：

- 反转片：曝光与显影 → 透射光谱 → 观看 XYZ → 显示。
- 负片 APD：曝光与显影 → 透射光谱 → APD → 浮点 ADX → ACES → XYZ → 显示。
- 光学放大：曝光与显影 → 负片透射 → 放大光、隔热玻璃、镜头与滤色 →
  固定预闪与相纸曝光 → 相纸显影与反射光谱 → 观看 XYZ → 显示。

显示使用 OpenColorIO 生成的 MSL，上传其原始 1D / 2D / 3D 纹理，保留 ACES 2.0
与 OpenDRT 各视图和三个输出目标。没有额外烘焙一层显示 LUT。OpenDRT 原配置
本身使用的 LUT 仍然存在，不把它说成纯解析计算。

A 对照也由 GPU 执行：高光谱直接积分 XYZ 再转 sRGB；普通 RGB 使用已有的
色彩坐标桥接；RAW 使用 RawTherapee 独立 sRGB 输出。A 不经过胶片模拟。
LUT 生成的 ACEScct 解码、完整材料和显示计算也由同一 GPU 像素实现完成。
文件读回、独立 OCIO 执行和 float64 对照仍单独验证导出。

## CPU 边界与精度

RawTherapee 的解码、相机配置和两个输出分支保持原样。文件解码、ICC 解释、
输入预览尺寸准备、材料拟合、冻结参数准备、单点诊断、PNG 编码和文件读写
仍是 CPU 工作。这些不冒充 Metal 实现。图像范围内的光谱、材料和显示像素
计算使用 float32，保留 C++ / NumPy float64 作为独立数值参考。

GPU 编译禁用 fast math，不使用 half 保存光谱密度。没有静默 CPU 回退。
开发检查需要 CPU 参考时，可明确运行 `python -m spectral_app --compute cpu`。
当前实际验证设备是 Apple M2 Pro；其他 GPU 尚未得到同等硬件测试。

## 调度、缓存和内存

界面至多保留一个正在执行的图像预览请求和一个最新待执行请求。连续调整会合并
等待请求；配方、照片或曝光已变化时，旧结果不能替换新画面。

GPU 每块至多 65,536 个像素，跨预览、导出共享执行层。块间允许其他请求进入，
导出不会占有整个图像期间的 GPU 锁。程序最多缓存 12 份，材料参数最多缓存
16 份；正在执行的程序持有独立引用，缓存淘汰不销毁在用资源。诊断耗时按请求
线程记录，避免导出和预览混写。

光谱积分与两次显影融合在每个线程内，没有整幅图像 × 186 波段的中间数组。
33 波段输入的单块上传约 8.25 MiB，RGB 输入约 0.75 MiB；另有输出、固定参数
和显示纹理。原图解码和最终 RGB/PNG 仍需各自的主存，不能据此声称整次导出
只占这些显存。输入预览使用磁盘 NPY、内存映射和 128 MiB 解码缓存预算。
RAW 原尺寸交接使用只读 TIFF 映射、文件身份校验缓存和交互优先的解码名额；
首次解码保持既有 RT 质量。具体计时与限制见 [RAW 交接](raw-handoff-and-batch.zh-CN.md)。

2048 px 缓存使用 schema 2。旧 schema 1 缓存可恢复照片目录，在首次选择时
从哈希核对的原文件重建，不在启动时重新解码整批照片。原文件、配方材料
快照和每张照片的输入曝光不因缓存升级改变。

## 验证

`experiments/verify_metal_pipeline.py` 检查 26 份材料／流程组合，包括四款
VISION3、四款反转片和新增相纸组合。每份比较 RGB 与直接光谱输入，在
−4 / 0 / +4 EV 下对照 float64，共 156 项。记录 XYZ 和显示 RGB 的误差，
APD 分支另查密度，打印分支另查独立 CMF 积分与 sRGB 矩阵编码。

本次最大编码 RGB 绝对差约 1.87e-5，最大缩放 XYZ 差约 2.44e-6。
额外测试覆盖 18 个视图／输出目标组合、ACEScct 输入、RAW 原图编码、分块
边界、并发及程序淘汰，并启用 Apple Metal 验证层。

Apple M2 Pro 上的单次 2048 × 1366 测试，着色器预热后，整幅像素调用约
56 ms（反转片）、57 ms（APD）、63 ms（光学放大）。这些时间包含该调用的
分块和显示计算，不含 RAW 解码、PNG 编码、HTTP 或 WebKit 呈现，不代表
完整界面的帧率或其他硬件性能。

另用授权测试目录中的 Canon EOS R6 CRAW 核查两条 RawTherapee 分支，实际
开发尺寸为 3396 × 2262，A/B 预览为 2048 × 1364，导出仍为 3396 × 2262。
合成细节图另查 2560 × 1707 原尺寸导出，65³ LUT 通过读回与独立执行检查。
本地结果为 `artifacts/metal-preview/verification.json`，界面证据独立记录。
这些是实现、文件与色度计算检查，不是真实胶片或相纸的色彩准确度测量。

## 参考

依据 Apple 的[GPU 计算](https://developer.apple.com/documentation/metal/performing-calculations-on-a-gpu)、
[线程组织](https://developer.apple.com/documentation/metal/creating-threads-and-threadgroups)、
[资源同步](https://developer.apple.com/documentation/metal/resource-synchronization)
和 [Apple silicon 图像处理指南](https://developer.apple.com/videos/play/wwdc2021/10153/)。
着色器绑定按所用 OCIO 的公开 MSL 生成接口建立。

经用户授权参考 SoftLoaf Negative 的请求合并、导出快照与分块原则，未复制
其私有实现、配置或代码。APD/ADX 常数与算法继续遵循项目既有 Academy 授权
记录，见 `third_party/aces-v1.2/LICENSE.md`。
