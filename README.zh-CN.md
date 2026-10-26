# SoftLoaf Spectral

[English](README.md)

SoftLoaf Spectral 用于模拟胶片成像，并生成照片和视频可用的颜色 LUT。
计算从胶片感光谱、特性曲线和染料吸收谱开始，继续考虑翻拍、光学放大或
透射观看时的光源与材料。

先做三条流程：

- Kodak 5207 负片，由指定光源和相机数字化。
- 同样的 5207 负片，光学放大到 Kodak Ultra Endura 相纸。
- Kodak E100 反转片，在指定光源下透射观看。

光谱模型作为计算参照，普通 RGB 图像通过近似模型处理。参数固定后，
颜色转换可以导出成 LUT；颗粒、光晕等效果由滤镜另行处理。

## 进度

目前已整理项目设计、资料目录和前期实验结果。独立计算引擎及 LUT 导出
尚未实现，暂时没有可安装的软件或可下载的 LUT。

第一步是独立复现 E100 的光谱计算，再做 RGB 近似和 LUT。

## 文档

- [项目说明](docs/project-brief.zh-CN.md)
- [计算方法](docs/science-and-pipelines.md)
- [资料目录](data/registry.json)
- [前期实验](research/README.md)
- [开发计划](docs/validation-and-roadmap.md)
- [参考项目和资料](docs/prior-art.md)

## 已知限制

同一组 RGB 可以对应不同的光谱，胶片对这些光谱的响应也可能不同。
因此，从普通照片生成胶片效果必须采用近似，并检查它在不同颜色和光源下的误差。

中性特性曲线也不足以确定胶片全部的彩色响应。现有材料模型还需要实拍
色块与光谱测量来验证。

整卷定标依赖输入的照片集合。导出固定 LUT 时，需要先固定定标、曝光及
观看条件，随 LUT 一起说明。

## 许可

项目原创代码和文档使用 **AGPL-3.0-only**，见 [LICENSE](LICENSE)。
第三方资料保留原有许可，见 [数据与许可](docs/data-and-licensing.md)。
