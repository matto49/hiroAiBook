#!/bin/sh

set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_root"
mkdir -p output/pdf

latexmk -xelatex -interaction=nonstopmode -file-line-error \
  -pvc -view=none -jobname=ch1 -outdir=output/pdf \
  preview/hiroAiBook-ch01.tex &
ch01_pid=$!

latexmk -xelatex -interaction=nonstopmode -file-line-error \
  -pvc -view=none -jobname=ch2 -outdir=output/pdf \
  preview/hiroAiBook-ch02.tex &
ch02_pid=$!

latexmk -xelatex -interaction=nonstopmode -file-line-error \
  -pvc -view=none -jobname=ch3 -outdir=output/pdf \
  preview/hiroAiBook-ch03.tex &
ch03_pid=$!

stop_watchers() {
  kill "$ch01_pid" "$ch02_pid" "$ch03_pid" 2>/dev/null || true
}

trap stop_watchers INT TERM EXIT
wait
