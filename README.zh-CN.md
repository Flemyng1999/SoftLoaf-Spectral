# 面包光谱（SoftLoaf Spectral）

**安装版与科学资料分开提供。** alpha.1 为源码版，alpha.2 增加 macOS arm64
独立运行时打包；Windows 安装器仍在验证。已上线下载见
[Releases](https://github.com/Flemyng1999/SoftLoaf-Spectral/releases)。两种分发均不附
胶片／相纸曲线、冻结采样模型、照片或扫描标定。公开内核测试可独立运行；
应用仍需另行准备科学资料目录。
见[源码构建与运行资料](docs/source-release.md)及[安装与打包说明](docs/installer-setup.md)。

日志、跨平台 CI、本地严格测试和设置中的语言选择见
[检查体系与 Windows 开发](docs/quality-and-windows.md)。自有内核使用 C++23；
Windows 使用 D3D12，保留 CPU 处理及故障重试。独立运行时候选版已完成
真实 RAW 的 GPU／CPU 全尺寸导出和 LUT 回读；最终安装器仍须另行验收。

[English](README.md)

SoftLoaf Spectral 是一个根据光谱数据计算胶片模拟 LUT 的项目。
桌面应用用于组合光源、胶片感光谱、特性曲线、染料谱及其他材料数据，
调整成像参数，预览结果并导出 LUT。

目标是让普通用户打开相机 RAW、使用所生成 LUT 调节效果并导出图像。RAW
显影交给 RawTherapee，匹配的 DCP 或矩阵与经核验的输出转换将相机颜色
接入 LUT 所需的输入空间。用户不需要准备高光谱照片或相机感光谱；光谱
数据随已审核的材料预设提供，或由用户导入。项目不以完整 RAW 编辑器为目标。

首先计算三种成像过程：

- Kodak 5207 负片，采用标准 APD 密度及固定版本的负片至 ACES 转换。
- 同样的 5207 负片，光学放大到 Kodak Ultra Endura 相纸。
- Kodak E100 反转片，在指定光源下透射观看。

计算包括曝光、光学放大和观看时使用的光源与材料。彩负标准输出采用 APD，
不模拟翻拍光源、翻拍相机和设备定标。普通 RGB 图像采用
近似模型处理，用光谱计算检查误差。参数固定后，RGB 颜色转换可以导出
为 LUT。颗粒和光晕另用图像滤镜处理。

胶片 LUT 由所选光谱节点计算生成。桌面应用允许用户替换光源和材料、调整
成像参数，在自己的 RAW 上比较结果并保存配方。应用内部将胶片 LUT 与
OpenDRT 显示处理分开。

固定颜色转换使用 OpenColorIO，显示成像采用 OpenDRT。

## 进度

桌面应用另有[负片正相工作区](docs/scan-workbench.zh-CN.md)：导入透射色卡及实测
光谱、平场 RAW 建立标定，导入同条件的负片 RAW，选一次片基，即可生成扫描
LUT 并批量正相。完整 PNG 导出复用独立保留的 full RAW 阶段，预览使用 half
阶段；两者不因切图、修改或清理预览缓存重新解码。当前输出为 ACES 2.0 SDR
sRGB，联合采集响应来自色卡拟合，尚无独立实拍色彩准确度结论。

仓库目前收录设计说明、资料目录、前期实验记录，以及一项
[E100 模拟 RAW 与 LUT 对比实验](research/hsi-raw-lut-comparison.md)。实验已能
生成 LUT 并与直接光谱计算比较。[本地桌面版 0.1](docs/application-v0.1.zh-CN.md)
已接入 C++23 float64 计算内核与 macOS 窗口，支持 E100 节点编辑、普通 RGB
试片、原尺寸 PNG 与 LUT 导出。开发版依赖构建时的源码、Python 环境和本地
材料资料；尚无独立安装包或已发布的 LUT。

[本机配方工作台](docs/gui-design.zh-CN.md)已接入 E100 参考计算，可预览图像、
在相同输入上比较完整配方、保存 JSON，自选 LUT 网格并查看误差，导出
材料 LUT 或 OCIO/CTF 显示处理包。桌面应用的 5207 APD 与 Ultra Endura 光学放大已接入计算，
数值结果及材料近似见[流程核查](docs/5207-pipeline-audit.zh-CN.md)。RAW 通过
RawTherapee 读取；源资料和生成结果仍限本地，等待数据许可审核。

5207 默认拍摄日光为 5500 K，直接按 Kodak 的 Status M 特性曲线拟合材料。APD 只在负片输出时计算，
再经 ADX 与输入变换进入 ACES；光学放大直接使用透射谱。
见[材料拟合与两条管线验证](docs/5207-status-m-validation.zh-CN.md)。
相纸条件单独依据 E-4020，见[拍摄光与相纸条件](docs/5207-d55-and-paper-conditions.zh-CN.md)。

E100 参考程序仍需补齐资料获取和曲线提取。当前实验从归档数据重新实现
数值计算，没有导入历史程序或私有应用代码。

## 文档

- [桌面版 0.1：构建与使用](docs/application-v0.1.zh-CN.md)
- [光谱与曲线 CSV 输入](docs/spectral-csv.zh-CN.md)
- [项目说明](docs/project-brief.zh-CN.md)
- [总体设计：从光谱配方到普通 RAW](docs/system-design.zh-CN.md)
- [APD、ADX 与 Status M 的职责](docs/apd-adx.zh-CN.md)
- [RAW 输入与相机配置](docs/raw-input-and-dcp.zh-CN.md)
- [计算方法](docs/science-and-pipelines.md)
- [光谱节点与桌面界面](docs/spectral-nodes.zh-CN.md)
- [GUI 设计与交互原型](docs/gui-design.zh-CN.md)
- [生成 LUT 必需的节点输入](docs/lut-generation-inputs.zh-CN.md)
- [光谱采样数据库设计与首轮验证](docs/spectral-sampling-database.zh-CN.md)
- [分库建立、测试与调整结果](research/sampling-database-build.md)
- [色彩管理与显示输出](docs/color-management.zh-CN.md)
- [资料目录](data/registry.json)
- [前期实验](research/README.md)
- [IT8 数据验证与 LUT 构建试验](research/it8-lut-trial.md)
- [视频文稿](video/README.md)
- [本地实验归档](research/local-archive.md)
- [开发计划](docs/validation-and-roadmap.md)
- [参考项目和资料](docs/prior-art.md)

## 已知限制

不同光谱可以得到相同的 RGB，却在胶片上产生不同的响应。RGB 近似模型
需要用实测光谱场景检验，并记录输入条件和光谱假设。

中性特性曲线不足以确定胶片对各种颜色的响应。材料模型还需要独立的
胶片和相纸测量来验证。

整卷定标依赖输入的照片。导出 LUT 前须固定定标、曝光和观看条件，
并随文件记录这些设置。

## 许可

项目原创代码和文档使用 **AGPL-3.0-only**，见 [LICENSE](LICENSE)。
第三方资料保留原有许可，见 [数据与许可](docs/data-and-licensing.md)。

普通 RAW 已通过 RawTherapee 5.12 接入两条路径：sRGB 原图预览，以及线性 ACEScg 胶片输入（LUT 使用 ACEScct）。试片支持多图导入、底部胶片条和后台批量导出。[实际设置和验证范围](docs/raw-handoff-and-batch.zh-CN.md)另列。

内置[胶片材料目录](docs/film-presets.zh-CN.md)现提供 E100、Velvia 100、Velvia 50、Provia 100F 反转片，
以及 VISION3 5203、5207、5213、5219 负片。新增富士材料独立提取各自的原厂 Status A、
感光和染料曲线，采用声明的相对曝光标定与图外尾部假设。其他不完整负片已从
内置选项隐藏；已有用户配方保留。

四款 VISION3 负片现使用各自原厂曲线和冻结的片种相对曝光参考。5203 使用条件明确的
2015 完整版，5219 保留 Status M 的跨图推定说明；VERITA 已排除。旧配方保留原材料
快照，新建或重新选择胶片使用新资料。两种正相方式、原图回算和 LUT 检查见
[接入记录](docs/film-presets.zh-CN.md)。

光学放大的相纸节点与试片调整栏现可独立选择 Ultra Endura、Endura Premier、
Ektacolor EDGE、ROYAL Digital 和 Premier Metallic。新增四款采用各自原厂曲线，
冲洗与曝光条件分别记录；纸白仍为模型假设，Metallic 不模拟金属反光。
详见[光学放大说明](docs/printing-optics.zh-CN.md)。

macOS 预览现以短边 2048 px 为上限，三条材料管线与 OCIO 显示像素计算默认走
Metal，原尺寸导出与 LUT 生成复用同一实现。小原图不向上放大；RAW 开发仍由
RawTherapee 负责。见 [Metal 实现与验证](docs/metal-pipeline.zh-CN.md)。

See [分块处理与缓存设置](docs/streaming-io-cache-settings.zh-CN.md) for the current
image/export modules, settings behavior, measurements and limits.

The selected separate reversal and negative sampling models now drive the
application, with bounded GPU LUT baking and verification. See
[optimized sampling integration and measurements](docs/optimized-sampling-gpu-lut.zh-CN.md).
