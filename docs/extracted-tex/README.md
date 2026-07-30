# PDF 到 TeX 抽取说明

本目录由本地 PDF 自动抽取生成，作为后续人工整理、改写或并入正文的素材。

## 文件

- `ml-optimization-seminar-first-lecture.tex`：第一讲中文稿抽取；其中《和补习组一起学习泊松分布》没有文字层，已转为页面图片引用。
- `ml-optimization-seminar-first-lecture-jp-source.tex`：第一讲日文合志 PDF 的文字层抽取。
- `hiro-physics-anthology.tex`：物理学合志 PDF 的文字层抽取。

## 注意

- 这些文件是 LaTeX 片段，不是完整主文档；可从 `main.tex` 或临时 wrapper 中 `\input{...}`。
- 数学公式来自 PDF 文字层，可能存在断行、缺字、上下标丢失或符号顺序错乱，需要人工校对。
- 图片页资源放在 `figures/extracted/ml-optimization-seminar-1/`。
