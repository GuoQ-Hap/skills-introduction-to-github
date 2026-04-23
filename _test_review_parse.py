"""让 VM 返回产品页中评论区的 HTML 片段，分析真实选择器。"""
import requests, json, re
from bs4 import BeautifulSoup

# 请求 VM 抓取，拿产品页 HTML 来本地分析
# 我们通过一个特殊的 debug 请求——但 VM 没有返回原始 HTML 的端点
# 所以换个思路：直接在 VM 上加一个端点返回评论区 HTML 片段

# 先试试给 VM 一个小请求，看看 debug 里有没有 snippet
# 实际上我们需要用 VM 去分析——让我在 scraper_server 加个端点

# 暂时先利用现有信息：产品页有 15 个 data-hook="review"
# 但 _reviews() 没找到——可能是因为容器选择器不对
# 让我直接写一个脚本通过 VM 做代理来拿 HTML

# 方案：我们添加一个 /debug-reviews 端点到 VM
# 这个端点返回产品页中评论相关 HTML 的结构信息

print("VM 产品页已确认有 15 条 data-hook=review")
print("问题在于 _reviews() 方法的容器/选择器匹配逻辑")
print()

# 让我分析 _reviews() 代码逻辑：
# 1. 先找容器: #cm-cr-dp-review-list 或 #cm_cr-review_list
# 2. 在容器里找 div[data-hook="review"]
# 3. 如果没找到容器，用全局 find_all(data-hook="review")
print("_reviews() 逻辑:")
print("  1. 找容器 #cm-cr-dp-review-list / #cm_cr-review_list")
print("  2. 容器内找 div[data-hook='review']")
print("  3. 全局找 div[data-hook='review']")
print()
print("可能的问题:")
print("  - 容器选对了，但 div[data-hook='review'] 可能是 data-hook='review' 在 span/section 上")
print("  - 或者子元素提取 (stars/title/body) 的选择器不匹配新版页面")
print()
print("需要 VM 返回实际的评论区 HTML 片段来确认")
