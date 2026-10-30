# 首个测试版的原始数据与许可审查

2026-10-30；Issue #14；工作分支 `codex/first-release`。

用户要求先审清许可，再发布功能完整的测试版。光谱优先从厂商、标准机构
或测量作者的原始资料取得。其他项目的曲线只有在原始来源确实无法取得时
才考虑，并说明搜索经过、原因、处理方法、限制和适用许可。当前没有批准
这类例外。已有本地计算不等于这些输入可以随软件公开分发。

## 已取得的原始数据

| 输入 | 原始来源与当前结果 |
| --- | --- |
| CIE 1931 2°、D50、D65、D55、日光 S0/S1/S2 | 从 [CIE](https://cie.co.at/data-tables) 直接取得五份 CSV；逐份匹配官方元数据 SHA-256。元数据明确为 CC BY-SA 4.0；原字节、DOI、署名和许可链接保存在 `assets/science/cie`。尚未替换运行时输入。 |
| KG3 | 从 [SCHOTT 下载页](https://www.schott.com/en-gb/products/optical-filter-glass-p1000266/downloads) 取得 2024-02 计算工具。原始 XLSX 的 D-Bank 工作表 CI2 为 KG3，CI3 参考厚度为 2 mm，CI4 反射因子为 0.92；不能把内部透射率直接当作含表面反射的透射率。Copyright 工作表对商业用途要求另行申请许可；原文件留在本地。 |
| Edmund CMY | [厂商滤片组](https://www.edmundoptics.com/p/cyan-magentayellow-50mm-diameter-dichroic-filter-set/10628/) 对应 0° 入射、2 mm 基片的减色滤片。已取得原始青色理论透射图，尚未完成三条独立数字化曲线和许可审查。搜索中的 45° 反射滤片不是同一元件，不能代用。 |
| 胶片、相纸 | 当前可选 VISION3、E-6 和新增 RA-4 材料主要已由本项目从 Kodak/Fujifilm 原始文档独立采集。逐材料身份见现有 manifests；取得原图不自动解决嵌入数值、拟合模型或 LUT 的分发依据。 |

CIE 的 D55 与日光基向量 CSV 和元数据文字还有覆盖范围/步长差异。已按实际
文件记录网格，并保留未修改的官方元数据与差异说明；没有凭文字补出额外采样点。

原始 SCHOTT ZIP SHA-256：
`9440bd61ddb49572e21b2af3a6f43f25f9e6018b31d62576bea67da66c4da592`。
Edmund 青色原始 PDF：
<https://www.edmundoptics.com/document/download/532320>，SHA-256：
`7f94d4a02d58824aed2bb24234533f34fb2d5254b6ba01aa0bb536fbd7c889f6`。
它是理论曲线，不能写成独立实测。以上源文件没有随应用公开发布。

## 仍需处理的实际依赖

光学放大的 `spectral-v2` 仍载入 spektrafilm 处理过的 KG3、Edmund CMY、
可选 Canon 镜头和 Ultra Endura 底色。它们是已记录的本地历史输入，当前
不满足首发的原始来源要求。KG3 已有原始表，不能再以找不到原始数据为由
批准仓库曲线。相纸底色仍缺原始测量，不能把另一项目的处理结果写成实测。
来源替换还需重新比较曝光、密度和成片；本次没有静默改变现有配方。

采样模型含 Manchester 光谱场景、BabelColor Average、ColorChecker N Ohta
和 Wolf Faust IT8，不只包含 Manchester。原始 [Manchester v3 数据集](https://doi.org/10.48420/14877285.v3)
API 声明 CC BY 4.0；仍需对应保留的输入文件身份。另几组原始测量的数据
许可、适用范围和模型分发依据尚未核定，不能据此把整个冻结模型标为可分发。
Status A/M 标准表、APD 数值表及各自派生物也需分别审查；Academy 变换代码
的许可不能代替数值表的审查。

这些是尚未取得或核定的分发依据，不是对所有数值事实作统一版权判断。
没有联系厂商、作者或发送许可申请；如需许可，申请应具体列明源表、
独立提取、派生材料/采样模型和测试版分发范围。

## 可执行检查与发布状态

`release/scientific-sources.json` 是科学输入审查清单，
`python scripts/check_release_sources.py` 验证依赖闭包、已审文件哈希、许可记录、
路径边界和仓库例外。派生物不能掩盖未审的上游输入。当前命令返回失败，
明确列出仍待审核的输入；这是阻止误发布，不是打包成功。

LOGO 已生成 PNG、ICNS 和十种尺寸的 ICO。macOS 开发包中的 ICNS 与标准资源
哈希一致；Windows 构建通过四项原生测试，包括实际 PE 图标与中英文产品名读取。
数据检查另有回归测试，覆盖篡改文件、缺失来源、待审模型输入及未说明的仓库曲线。

用户随后明确选择先发布 `0.1.0-alpha.1` 源码测试版，不附未审数据，并说明
运行所需资料。该渠道用独立的源码包内容检查，不把完整数据检查改成通过。
开发程序仍依赖源码工作区、Python 环境和本地材料；独立安装包仍需后续的
冷启动与真实 RAW/LUT 验证、签名和适用平台公证。源码测试版不声称交付这些安装包。
