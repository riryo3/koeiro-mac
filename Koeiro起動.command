#!/bin/bash
# ダブルクリックで Koeiro（Mac版）を起動します。
cd "$(dirname "$0")" || exit 1
echo "Koeiro を起動しています…（このウィンドウは使っている間、閉じないでください）"
.venv/bin/python app.py
echo; echo "Koeiro を終了しました。（Enterキーで閉じます）"; read -r
