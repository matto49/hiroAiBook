# This project contains Chinese and Japanese text, so it must use XeLaTeX.
# Some editor recipes call `latexmk -pdf`, which normally selects pdfLaTeX.
# Route that fallback through XeLaTeX to avoid missing CJK characters.
$pdf_mode = 5;
$pdflatex = 'xelatex %O %S';
