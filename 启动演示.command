#!/bin/zsh
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  python3 demo.py
else
  echo "需要先安装 Python 3.9 或更新版本。"
  read
fi
