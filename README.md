# HIRO AI Book

一本使用 LaTeX 制作的小册子。

## 版式基线

- 成品尺寸：JIS B5，182 mm × 257 mm。
- 排版方式：竖版、双面，装订侧 18 mm、外侧 15 mm、上方 17 mm、下方 20 mm。
- 正文：9 pt，行距 13 pt；小号正文：8 pt，行距 11.2 pt。
- 封面：当前 PDF 内为单页预览；印刷用封面及 3 mm 出血文件应在装订方式和书脊宽度确定后单独制作。

LaTeX 标准 `b5paper` 是 ISO B5（176 mm × 250 mm）。本项目使用 `geometry` 的 `b5j`，不要替换成 `b5paper`。

## 项目结构

```
.
├── main.tex        # 主文档入口
├── figures/        # 图片资源
├── chapters/       # 章节文件（可选，按需拆分）
└── README.md
```

## 编译方式

使用 XeLaTeX 编译（支持中文）：

```bash
xelatex main.tex
xelatex main.tex   # 第二次编译以生成目录
```

或使用 latexmk 自动化编译：

```bash
latexmk -xelatex main.tex
```

## 自定义

- **标题/作者**：修改 `main.tex` 中的 `\title` 和 `\author`
- **颜色**：修改 `primary` 和 `accent` 颜色定义
- **页面尺寸**：当前锁定为 JIS B5；如需修改，统一调整 `geometry` 与封面交付文件
- **章节拆分**：在 `chapters/` 目录下创建独立 `.tex` 文件，用 `\input{chapters/xxx}` 引入
