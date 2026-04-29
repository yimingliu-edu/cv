#!/usr/bin/env bash
# 推送到本仓库 origin（需已配置 SSH 或 HTTPS 凭据）
# 站点仓库: https://github.com/888dddhhh/Lym
# GitHub Pages: https://888dddhhh.github.io/Lym/
set -euo pipefail
cd "$(dirname "$0")"

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "未配置 origin，请执行:"
  echo "  git remote add origin https://github.com/888dddhhh/Lym.git"
  exit 1
fi

git add -A
if git diff --staged --quiet && git diff --quiet; then
  echo "无变更可提交。"
else
  git commit -m "Update site"
fi
git push -u origin main

echo ""
echo "✓ 已推送。开启 Pages: 仓库 Settings → Pages → Branch main / (root)"
echo "  访问: https://888dddhhh.github.io/Lym/"
echo ""
