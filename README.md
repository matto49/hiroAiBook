# HIRO AI Book

一本使用 LaTeX 制作的小册子。

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
- **页面尺寸**：修改 `geometry` 宏包参数
- **章节拆分**：在 `chapters/` 目录下创建独立 `.tex` 文件，用 `\input{chapters/xxx}` 引入
