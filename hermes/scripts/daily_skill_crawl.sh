#!/bin/bash
# HERMES 每日抓取脚本
# 每天 06:00 执行

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_DIR="$(dirname "$SCRIPT_DIR")"

cd "$HERMES_DIR"

# 执行抓取
python3 -c "
import sys
sys.path.insert(0, '$HERMES_DIR')
from scripts.daily_crawler import HermesCrawler
crawler = HermesCrawler()
crawler.run()
" 2>&1 | tee -a "$HERMES_DIR/logs/daily_crawl.log"

# 更新技能库后重建索引
python3 "$HERMES_DIR/scripts/build_skill_index.py" 2>&1 | tee -a "$HERMES_DIR/logs/skill_index.log"

echo "$(date): 每日抓取完成"
