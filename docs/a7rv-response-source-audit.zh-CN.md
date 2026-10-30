# Sony A7R V 响应曲线检索

2026-10-29，Issue #12。目标是整机 ILCE-7RM5 的独立实测 RGB 光谱响应，
不是裸传感器 QE、DNG 矩阵、估计响应或 A7R IV 的曲线。

截至本次检索，未取得带测量方法、可核验来源及数值表的独立实测 A7R V 曲线。
这个结论限于已查的公开资料，不能据此断言不存在此类测量。

| 来源 | 核验结果 | 本次使用 |
| --- | --- | --- |
| [Cobalt A7R V 测量报告](https://www.cobalt-image.com/spectre-measurements-sony_a7r_v/) | 页面提供分色、Luther–Ives、Vora 等实验指标；未取得可下载 RGB 波长响应表。直接下载返回验证页面，未绕过验证 | 仅记录报告存在，不从指标或图像臆造 SSF |
| [Solomatov、Akkaynak 作者页面](https://color-lab-eilat.github.io/Spectral-sensitivity-estimation-web/) | 作者明确说明以 Adobe DNG 矩阵和自编码器估计，无须实际相机。直接检查作者的预测 ZIP，包含 `csv/Sony-ILCE-7RM5.csv`；实测真值 ZIP 没有对应机型 | 保存预测文件的本地身份记录，未接入本次 LUT |
| [RawToACES 相机库](https://github.com/AcademySoftwareFoundation/rawtoaces-data/tree/main/data/camera) | Sony ILCE-7RM4 等机型不能作为 ILCE-7RM5 实测的证明；本次目录检索未找到 V | 未替代 |
| [butcherg SSF 数据](https://github.com/butcherg/ssf-data/tree/master/Sony) | 原代 A7R 与 NEX-5N 等，不是 V | 未替代 |
| [ilia3101 实测库](https://github.com/ilia3101/SpectralMeasurements) | 列出的 A7、A7 II 等较早机型不是 V | 未替代 |
| [DXOMark A7R V](https://cdn.dxomark.com/Cameras/Sony/A7R-V---Measurements) | 颜色指标、白平衡和颜色矩阵不等于连续 RGB 光谱响应 | 未反推为实测 |

作者预测包 SHA-256：
`7054f1c411c3da2808297fffed456906d787b0d1622ca9c42ec2895262a56522`。
其中 A7R V CSV SHA-256：
`3242e73995695d47bdd55a2a5008b479cfee1ac8e8589146b51ffdb89f9c7e0d`。
作者真值包 SHA-256：
`067aee80100d3685adc4d00e530fd03dc9fc25b3d5a22f01d2c930fac1079bbe`。
数值文件及取回记录只放配置的外置数据卷；尚未据此取得再分发授权。

## 本次 65³ 文件的证据范围

用 000003 透射卡及其实际扫描读数估计的是光源、光路和相机的**联合响应**。
它在数学前向模型中确实包含相机通道响应的作用，但不是独立测量的相机 SSF，
也不能把联合函数唯一拆成灯 SPD、镜头透过率与相机响应。

实测 SSF 即便取得，还需要同一配置下的扫描光源 SPD、光路透过率／IR 阻断、
通道增益、曝光与黑电平约定。当前平场的绿色通道存在剪切、同卷片基使用固定
片边对齐；不能因为换成一条公开相机曲线就认为这些问题已经解决。

本次继续交付明确标为 `estimated-joint-response` 的局部标定实验文件，
不把它称作完成了“独立实测 A7R V 版”。数学过程和可执行文件的验证，见
[65³ 扫描导出](scan-65-lut.zh-CN.md)。

随后按用户要求，将这个已明确身份的预测响应用于独立的
[相机响应敏感度实验](camera-response-sensitivity.zh-CN.md)，与 Weta 的
A7R IV／III／II 来源数据及当前联合拟合比较。此用途没有把预测改称实测，
也没有替换原先联合响应 65³ 文件或桌面应用默认设置。
