"""lAi_listing 所有 LLM 提示词模板

可配置字段通过 PROMPT_DEFAULTS 暴露，前端可覆盖后传入。
"""

# ═══════════════════════════════════════════════
# 可配置默认值 —— 前端设置面板可覆盖
# ═══════════════════════════════════════════════

PROMPT_DEFAULTS = {
    "core_capabilities": """\
- 深度理解 Amazon A9/COSMO 搜索排名算法
- 精准把握各站点消费者搜索习惯和购买心理
- 通过关键词布局最大化产品曝光和转化率
- 撰写高转化率的 Listing 文案""",

    "company_info": """\
**凌昂科技（Leang Technology）**
- 主营业务：跨境电商，主要在亚马逊（Amazon）平台销售家居用品
- 核心产品线：窗帘（Curtain）、厨房地垫（Kitchen Mat）、户外/房车地垫（Outdoor/RV Mat）及其他家居纺织品
- 销售市场：美国（US）、日本（JP）、英国（UK）、加拿大（CA）、德国（DE）等多国亚马逊站点""",

    "bullet_rules": """\
- 恰好 5 条，每条 150-250 字符
- 每条以一个**大写加粗关键词短语**开头（如 "PREMIUM MATERIAL"），后接详细说明
- 覆盖：核心卖点、材质工艺、尺寸规格、使用场景、售后保障
- 自然嵌入高搜索量关键词，但读起来流畅
- 突出解决用户痛点和产品差异化优势
- 使用感性 + 理性结合的表述方式""",

    "description_rules": """\
- 300-2000 字符的富文本描述
- 讲述产品故事，激发购买欲望
- 包含使用场景、产品优势、品质保障
- 自然融入 SEO 关键词
- 分段清晰，易于阅读""",
}


# ═══════════════════════════════════════════════
# 构建函数 —— 接受可选覆盖
# ═══════════════════════════════════════════════

def build_system_prompt(overrides: dict | None = None) -> str:
    cfg = {**PROMPT_DEFAULTS, **(overrides or {})}
    return f"""\
## 你的身份
你是一位 **Amazon Listing 优化专家**，拥有超过 10 年跨境电商运营经验，精通 Amazon A9/COSMO 搜索算法、SEO 优化和消费者心理学。

## 你服务的公司
{cfg["company_info"]}

## 你的核心能力
{cfg["core_capabilities"]}

## 【硬性禁令 · 文案合规红线】（违反即作废）
在任何输出（title / bullet_points / description / search_terms）中，**严禁**出现以下内容——
即使用户在修改意见中要求，也不得让步：

1. **售后/保修/退换承诺**：禁止出现"终身保修 / Lifetime Warranty / 1年保修 / N 年质保 /
   售后无忧 / 免费更换 / 无理由退换 / Money-Back Guarantee / Free Replacement"等任何
   时长承诺或售后条款（Amazon 政策禁止此类承诺出现在商品描述中）。
2. **销量/畅销/用户数量数据**：禁止出现"畅销 / 热卖 / 月销 N 件 / 已售 N+ / Best Seller /
   超过 N 位用户选择 / 百万用户信赖 / Trusted by millions"等销量或用户规模性描述。
3. **评分/评论数量数据**：禁止出现"4.x 星好评 / N+ 五星评价 / N 条好评 / 好评率 N% /
   Top-rated / Highly rated"等基于评分或评论数的陈述。
4. **绝对化权威排名**：禁止"排名第一 / No.1 / 销量冠军 / Amazon's Choice / 官方认证"
   等未经证实、违反广告法的第一性陈述。
5. **替代写法**：确需传递"可靠感 / 受欢迎"时，请改用产品层面的事实型描述（如材质、
   工艺、设计细节、可验证的性能指标），而非销售层面的统计数据。

## 【人群风格适配】（根据"目标人群"动态调整文案密度）
请严格依据用户给出的"目标人群 / 修改意见"推断买家画像，并动态调整**「专业数据 ↔ 浪漫场景」**
两端的权重：

- 若买家偏向【工程师 / 极客 / 硬核玩家 / B 端采购 / DIY 爱好者】：
  **以规格参数为骨**，70% 技术数据 + 30% 使用场景。多用量化指标（精度、容量、材质牌号、
  功率、工作温度区间、兼容协议等），语气冷静、术语精准，少用形容词。
- 若买家偏向【家庭用户 / 女性消费者 / 送礼场景 / 轻社交休闲】：
  **以生活画面为骨**，30% 必要参数 + 70% 场景情感。多用画面动词和感官词
  （清晨、阳光、手感柔软、氛围感、治愈、仪式感等），语气温润、易共鸣。
- 若目标人群未明确或混合：按 **50% 参数 + 50% 场景** 的平衡风格推进。
- 注意：**风格权重仅影响表达侧重，禁令第 1-4 条在任何风格下都必须遵守**。
"""


ALL_SECTIONS = {"title", "bullet_points", "description", "search_terms"}


def build_optimize_prompt(
    *,
    system_prompt: str,
    asin: str, marketplace: str,
    title: str, brand: str, price: str, currency: str,
    rating: str, review_count: str, category: str, bsr_rank: str,
    bullet_points_text: str, description: str,
    target_keywords: str, target_audience: str, output_language: str,
    overrides: dict | None = None,
    sections: set[str] | None = None,
    competitor_texts: list[str] | None = None,
) -> str:
    cfg = {**PROMPT_DEFAULTS, **(overrides or {})}
    sec = sections if sections else ALL_SECTIONS

    req_parts: list[str] = []
    json_fields: list[str] = []
    idx = 0

    if "title" in sec:
        idx += 1
        req_parts.append(f"""### {idx}. 标题（Title）
- 严格控制在 200 字符以内（{marketplace} 站点标准）
- 结构：品牌名 + 核心关键词 + 产品属性（材质/尺寸/颜色等） + 差异化卖点
- 将最重要的搜索词放在标题前部
- 避免关键词堆砌，保持可读性
- 不使用全大写（标题大小写规范：每个主要单词首字母大写）
- 不使用促销性词语（如 "Best Seller", "Free Shipping"）""")
        json_fields.append('"title": "优化后的标题"')
    else:
        req_parts.append(f"**标题**：保持原样，不做修改。")

    if "bullet_points" in sec:
        idx += 1
        req_parts.append(f"### {idx}. 五点描述（Bullet Points）\n{cfg['bullet_rules']}")
        json_fields.append('"bullet_points": ["第1条", "第2条", "第3条", "第4条", "第5条"]')
    else:
        req_parts.append(f"**五点描述**：保持原样，不做修改。")

    if "description" in sec:
        idx += 1
        req_parts.append(f"### {idx}. 产品描述（Description）\n{cfg['description_rules']}")
        json_fields.append('"description": "优化后的产品描述"')
    else:
        req_parts.append(f"**产品描述**：保持原样，不做修改。")

    if "search_terms" in sec:
        idx += 1
        req_parts.append(f"""### {idx}. 后台搜索关键词（Search Terms）
- 不超过 250 字节
- 包含标题和五点中未覆盖的长尾关键词和同义词
- 不重复标题中已有的词
- 使用空格分隔，不使用逗号
- 不包含品牌名、ASIN、"Amazon" 等禁止词
- 包含常见拼写错误和西班牙语/其他语言的搜索词变体""")
        json_fields.append('"search_terms": "后台搜索关键词（空格分隔）"')
    else:
        req_parts.append(f"**搜索关键词**：保持原样，不做修改。")

    idx += 1
    req_parts.append(f"""### {idx}. 优化说明
- 简要说明优化思路和改进点
- 列出新增覆盖的关键词
- 给出进一步提升 Listing 的建议（如 A+ Content、主图优化等）""")
    json_fields.append('"optimization_notes": "优化说明与建议"')

    requirements = "\n\n".join(req_parts)
    json_tpl = "{" + ", ".join(json_fields) + "}"

    competitor_section = ""
    if competitor_texts:
        competitor_section = (
            "\n## 竞品 Listing 参考\n"
            "请分析以下竞品的优劣势，在优化时取长补短、差异化竞争。\n\n"
            + "\n\n".join(competitor_texts)
            + "\n"
        )

    return f"""\
{system_prompt}

## 当前任务
根据以下 Amazon 产品信息，生成一份优化的 Listing。

## 原始产品数据
- **ASIN**: {asin}
- **站点**: {marketplace}
- **当前标题**: {title}
- **品牌**: {brand}
- **价格**: {price} {currency}
- **评分**: {rating}（{review_count} 条评论）
- **类目**: {category}
- **BSR 排名**: {bsr_rank}
- **当前五点描述**:
{bullet_points_text}
- **当前描述**:
{description}
{competitor_section}
## 用户指定的重点关键词
{target_keywords}

## 目标受众
{target_audience}

## 输出语言
{output_language}

## 优化要求

{requirements}

## 输出格式
请严格按以下 JSON 格式输出，不要添加其他文字或 markdown 代码块标记：

{json_tpl}
"""


# ═══════════════════════════════════════════════
# COSMO 四维策略优化提示词
# ═══════════════════════════════════════════════

COSMO_OPTIMIZE_PROMPT = """\
{system_prompt}

## 当前任务
基于亚马逊 **COSMO / 关键词 / Rufus / IDQ** 四维算法模型，对以下产品 Listing 进行深度优化。
你必须确保优化后的 Listing 在四个维度上都达到高分。

## 原始产品数据
- **ASIN**: {asin}
- **站点**: {marketplace}
- **当前标题**: {title}
- **品牌**: {brand}
- **价格**: {price} {currency}
- **评分**: {rating}（{review_count} 条评论）
- **类目**: {category}
- **BSR 排名**: {bsr_rank}
- **当前五点描述**:
{bullet_points_text}
- **当前描述**:
{description}
{competitor_section}
## 用户指定的重点关键词
{target_keywords}

## 目标受众
{target_audience}

## 输出语言
{output_language}

## ══════════════════════════════════════════
## 四维优化策略（必须逐一满足）
## ══════════════════════════════════════════

### 策略一：COSMO 关系覆盖优化
> COSMO（Customer Obsession Shopping Model）通过知识图谱理解「用户意图 → 产品属性 → 使用场景 → 购买决策」。

**优化要求：**
1. **实体关系显式化** — 标题和要点中必须显式建立产品类型 ↔ 核心属性的关系
   - 示例：不写 "Curtain, Polyester, 52x84"，而写 "Blackout Curtain - Triple Weave Polyester, 52x84 inch for Bedroom Windows"
2. **多意图覆盖** — 覆盖至少 3 种用户搜索意图类型：
   - 功能型（blackout curtains）、场景型（bedroom curtains）、问题解决型（curtains that block light and heat）
3. **场景-功能关联** — 每个使用场景必须关联具体产品功能
   - 示例："遮光功能适合卧室午睡" → "100% Blackout — Perfect for Bedroom Naps and Night Shift Workers"
4. **信任要素植入** — 至少包含 3 项购买决策信任要素：
   质量认证 / 量化对比数据 / 社会证明 / 售后保障 / 用户推荐
5. **属性-需求绑定** — 每个产品属性必须绑定消费者痛点/需求，杜绝"孤立属性"

### 策略二：关键词覆盖优化
> A9/A10 搜索算法通过关键词匹配决定排位，关键词需分层布局。

**优化要求：**
1. **标题前 80 字符** — 必须包含该品类 TOP 3 核心搜索词
2. **五点描述** — 每条至少嵌入 2-3 个长尾关键词，自然融入不堆砌
3. **描述补充** — 覆盖标题和要点未出现的补充长尾词和语义变体
4. **后台搜索词** — 填满接近 250 字节，仅放标题/要点中未出现的同义词、拼写变体、跨语言词
5. **同义词全覆盖** — 同一产品/功能必须覆盖 ≥5 组不同表达
   - 示例：curtain / drape / window covering / window treatment / window panel
6. **密度控制** — 关键词密度 2%-5%，读起来像营销文案而非 SEO 机器文

### 策略三：Rufus 语义覆盖优化
> Rufus 是亚马逊 AI 购物助手，需要能从 Listing 中提取信息回答消费者自然语言提问。

**优化要求：**
1. **核心价值 1 句话可答** — 前 2 个 Bullet Point 必须让 Rufus 能回答 "这个产品是什么？有什么用？"
2. **规格结构化** — 尺寸/材质/重量/颜色等以 「属性: 值」 格式呈现，便于 AI 精准提取
3. **使用/安装指引** — 至少在 1 个 Bullet Point 中包含安装或使用方法说明
4. **量化差异化** — 至少 3 处用量化数据表达与竞品/普通产品的差异
   - 示例："3X thicker than standard curtains" / "Blocks 99.8% of light"
5. **隐式 FAQ 覆盖** — 确保 Listing 内容能让 Rufus 回答至少 5 个该品类常见问题：
   尺寸兼容性 / 清洗维护 / 耐用性 / 安全性 / 安装难度

### 策略四：IDQ 语义完整性优化
> IDQ（Indexing & Detail Page Quality）衡量内容完整性和索引质量。

**优化要求：**
1. **标题** — 150-200 字符，结构：品牌 + 核心词 + 产品属性 + 差异化卖点 + 规格
2. **五点描述** — 恰好 5 条，每条 150-250 字符：
   - 第 1 条：核心卖点/功能
   - 第 2 条：材质工艺
   - 第 3 条：尺寸规格与兼容性
   - 第 4 条：使用场景与安装
   - 第 5 条：售后保障与品牌承诺
   - 每条以 **大写关键词短语** 开头
3. **描述** — 300-2000 字符，讲述产品故事，补充要点未展开的细节
4. **后台搜索词** — 接近 250 字节上限，不重复标题已有词
5. **合规性** — 禁止 "Best Seller"/"Free Shipping"/#1/全大写/竞品品牌名/医疗功效声明/HTML 标签
6. **四板块协同** — 标题聚焦核心词 → 要点展开卖点 → 描述讲故事 → 搜索词补遗漏，层层递进不重复

## 输出格式

请严格按以下 JSON 格式输出，不要添加其他文字或 markdown 代码块标记：

{{"title": "优化后的标题", "bullet_points": ["第1条", "第2条", "第3条", "第4条", "第5条"], "description": "优化后的产品描述", "search_terms": "后台搜索关键词（空格分隔）", "optimization_notes": "四维优化说明：\\n【COSMO】...\\n【关键词】...\\n【Rufus】...\\n【IDQ】..."}}
"""



# ═══════════════════════════════════════════════
# CTR 侧重优化提示词（提高点击率）
# ═══════════════════════════════════════════════

CTR_OPTIMIZE_PROMPT = """\
{system_prompt}

## 当前任务
基于 **CTR（点击率）最大化** 策略，对以下产品 Listing 进行深度优化。
核心目标：让消费者在搜索结果页看到该产品时，产生强烈的点击冲动。

## 原始产品数据
- **ASIN**: {asin}
- **站点**: {marketplace}
- **当前标题**: {title}
- **品牌**: {brand}
- **价格**: {price} {currency}
- **评分**: {rating}（{review_count} 条评论）
- **类目**: {category}
- **BSR 排名**: {bsr_rank}
- **当前五点描述**:
{bullet_points_text}
- **当前描述**:
{description}
{competitor_section}
## 用户指定的重点关键词
{target_keywords}

## 目标受众
{target_audience}

## 输出语言
{output_language}

## ══════════════════════════════════════════
## CTR 优化策略（点击率核心要素）
## ══════════════════════════════════════════

### 策略一：标题 CTR 优化（最高优先级）
> 搜索结果中消费者最先看到的是标题，标题决定了 80% 的点击决策。

**优化要求：**
1. **前 40-60 字符黄金区间** — 必须在前 60 字符内出现：
   - 品类最高搜索量核心关键词（精准匹配消费者搜索词）
   - 最强差异化卖点或数字（"100%"/"3X"/"Award-Winning" 等）
2. **数字化吸引力** — 标题中至少包含 1 个数字规格（尺寸/厚度/数量/百分比等）
3. **情绪词触发** — 植入 1-2 个情绪触发词（如：Premium / Luxury / Ultimate / Cozy / Heavy-Duty）
4. **痛点关键词前置** — 如消费者有明显痛点，在标题前部解决（如 "Blackout" 对应睡眠问题）
5. **移动端截断优化** — 前 80 字符为移动端展示区间，核心卖点必须在此范围内完整呈现
6. **禁止** — 不使用介词堆砌，不以品牌名开头（除非品牌已有强认知）

### 策略二：搜索结果视觉化五点描述
> 消费者在搜索结果展开预览时会看到前 2 条要点，这是第二次 CTR 机会。

**优化要求：**
1. **前 2 条要点** — 必须像"广告语"，简短有力，直击消费者最大利益点
   - 每条开头大写词组要像"标签"（如：TOTAL BLACKOUT / HOTEL-GRADE LUXURY）
   - 第 1 条：最强功能卖点 + 量化数据
   - 第 2 条：差异化体验 + 情感价值
2. **第 3-5 条** — 展开细节，覆盖材质/尺寸/使用场景/售后，自然植入长尾词
3. **每条 150-220 字符**，读起来像广告文案而非产品说明书

### 策略三：搜索关键词 CTR 匹配优化
> 关键词与搜索词越精准匹配，搜索结果中的关键词高亮越多，CTR 越高。

**优化要求：**
1. **精准词优先** — 优先覆盖用户实际搜索词（包含完整短语），而非拆散关键词
2. **高频搜索词全覆盖** — 标题中必须包含该品类 TOP 5 月搜索量关键词
3. **后台词补充** — 后台搜索词填充精准长尾词和拼写变体，不重复标题内容

## 输出格式

请严格按以下 JSON 格式输出，不要添加其他文字或 markdown 代码块标记：

{{"title": "优化后的标题", "bullet_points": ["第1条", "第2条", "第3条", "第4条", "第5条"], "description": "优化后的产品描述", "search_terms": "后台搜索关键词（空格分隔）", "optimization_notes": "CTR 优化说明：\\n【标题优化】...\\n【要点优化】...\\n【关键词匹配】...\\n【预期 CTR 提升点】..."}}
"""


# ═══════════════════════════════════════════════
# CVR 侧重优化提示词（提高转化率）
# ═══════════════════════════════════════════════

CVR_OPTIMIZE_PROMPT = """\
{system_prompt}

## 当前任务
基于 **CVR（转化率）最大化** 策略，对以下产品 Listing 进行深度优化。
核心目标：让已经点击产品页的消费者产生强烈购买冲动，消除顾虑，完成下单。

## 原始产品数据
- **ASIN**: {asin}
- **站点**: {marketplace}
- **当前标题**: {title}
- **品牌**: {brand}
- **价格**: {price} {currency}
- **评分**: {rating}（{review_count} 条评论）
- **类目**: {category}
- **BSR 排名**: {bsr_rank}
- **当前五点描述**:
{bullet_points_text}
- **当前描述**:
{description}
{competitor_section}
## 用户指定的重点关键词
{target_keywords}

## 目标受众
{target_audience}

## 输出语言
{output_language}

## ══════════════════════════════════════════
## CVR 优化策略（转化率核心要素）
## ══════════════════════════════════════════

### 策略一：消费者信任体系构建（最高优先级）
> CVR 最大的杀手是购买顾虑，信任是消除顾虑的核心。

**优化要求：**
1. **多维信任信号植入** — 每个要点至少包含 1 个信任要素：
   - 质量认证（OEKO-TEX / CE / RoHS / FDA 等）
   - 量化品质数据（"3X thicker" / "Tested to 50,000 washes"）
   - 品牌保障（"30-Day Money Back" / "Lifetime Warranty"）
   - 社会证明（"Trusted by 50,000+ families"）
2. **痛点-解决方案框架** — 每个要点按「痛点 → 功能 → 结果」结构撰写
   - 示例："Tired of flimsy curtains? Our triple-weave fabric blocks 100% of light — for the perfect sleep every night."
3. **风险消除语言** — 至少 2 处明确告知购买风险极低（退换货政策、质保承诺）

### 策略二：深度产品描述（购买决策页）
> 产品描述是消费者深度了解产品的区域，高 CVR Listing 的描述通常信息最丰富。

**优化要求：**
1. **产品故事化** — 描述开篇以场景/情感切入，让消费者产生代入感
   - 示例："Imagine coming home after a long day, drawing your curtains, and sinking into perfect darkness..."
2. **功能全面展开** — 详细阐述标题和要点未展开的产品细节：
   - 材质组成和工艺说明
   - 适用场景（卧室/客厅/儿童房/RV 等）
   - 尺寸兼容性指南
   - 安装方法和注意事项
3. **FAQ 内嵌** — 在描述中隐式回答 5 个购买前最常见问题
4. **Call to Action** — 描述结尾引导"立即购买"（但不使用违规词）
5. **字符数** — 尽量接近 2000 字符上限，提供最丰富的产品信息

### 策略三：要点 CVR 结构优化
> 五点描述是购买决策的核心载体，每条要点都要推进购买意愿。

**优化要求：**
1. 第 1 条：核心价值主张（让消费者立刻知道"买这个最划算"）
2. 第 2 条：材质/工艺/品质（消除对品质的顾虑）
3. 第 3 条：规格兼容性（消除"不适合我家"的顾虑）
4. 第 4 条：使用场景（强化购买理由：我需要它）
5. 第 5 条：售后保障（消除购买风险："买错了也没关系"）
- 每条以**量化或具体可信的短语**开头（避免空洞的营销词汇）

## 输出格式

请严格按以下 JSON 格式输出，不要添加其他文字或 markdown 代码块标记：

{{"title": "优化后的标题", "bullet_points": ["第1条", "第2条", "第3条", "第4条", "第5条"], "description": "优化后的产品描述（尽量接近 2000 字符）", "search_terms": "后台搜索关键词（空格分隔）", "optimization_notes": "CVR 优化说明：\\n【信任体系】...\\n【描述优化】...\\n【要点结构】...\\n【预期 CVR 提升点】..."}}
"""


# ═══════════════════════════════════════════════
# 流量侧重优化提示词（最大化曝光和流量）
# ═══════════════════════════════════════════════

TRAFFIC_OPTIMIZE_PROMPT = """\
{system_prompt}

## 当前任务
基于 **流量最大化** 策略，对以下产品 Listing 进行深度优化。
核心目标：通过最大化关键词覆盖广度，让产品在尽可能多的搜索词下获得曝光和排名。

## 原始产品数据
- **ASIN**: {asin}
- **站点**: {marketplace}
- **当前标题**: {title}
- **品牌**: {brand}
- **价格**: {price} {currency}
- **评分**: {rating}（{review_count} 条评论）
- **类目**: {category}
- **BSR 排名**: {bsr_rank}
- **当前五点描述**:
{bullet_points_text}
- **当前描述**:
{description}
{competitor_section}
## 用户指定的重点关键词
{target_keywords}

## 目标受众
{target_audience}

## 输出语言
{output_language}

## ══════════════════════════════════════════
## 流量优化策略（关键词覆盖最大化）
## ══════════════════════════════════════════

### 策略一：关键词宽度最大化（最高优先级）
> 流量来自于搜索词的覆盖广度，让更多搜索词能索引到该产品。

**优化要求：**
1. **多意图词覆盖** — 必须覆盖以下 5 类搜索意图：
   - 功能型（产品主要功能词）
   - 场景型（使用场景词）
   - 属性型（材质/尺寸/颜色等属性词）
   - 问题型（用户痛点词）
   - 比较型（"best X for Y" 结构词）
2. **同义词矩阵** — 每个核心概念覆盖 ≥ 5 个同义表达：
   - 英美英语差异（curtain/drape，grey/gray）
   - 正式/俗称差异（kitchen mat / anti-fatigue mat）
   - 长短词搭配（blackout curtains / room darkening window curtains for bedroom）
3. **长尾词挖掘** — 在标题中植入 1-2 个高转化长尾词短语（如 "for bedroom noise blocking"）
4. **标题关键词密度** — 标题包含 ≥ 8 个独立有意义的关键词，但不堆砌，读起来自然

### 策略二：五点描述关键词扩展矩阵
> 五点描述是关键词第二高权重区域，每条应当覆盖独立的关键词簇。

**优化要求：**
1. **每条要点独立关键词簇** — 5 条要点分别覆盖 5 个不同关键词主题：
   - 第 1 条：核心功能类关键词
   - 第 2 条：材质/工艺类关键词
   - 第 3 条：尺寸/规格/兼容性类关键词
   - 第 4 条：使用场景/房间类关键词
   - 第 5 条：售后/品牌/保障类关键词
2. **每条自然嵌入 4-6 个关键词**，不重复标题中已有的词
3. **描述部分** — 覆盖前两个区域未包含的补充关键词，尤其是：
   - 季节性关键词（winter/summer/holiday）
   - 风格关键词（modern/farmhouse/bohemian/minimalist）
   - 人群关键词（kids/nursery/college dorm/studio apartment）

### 策略三：后台搜索词极限覆盖
> 后台搜索词 250 字节是专门用于覆盖长尾词和变体的隐藏渠道。

**优化要求：**
1. **接近 250 字节上限** — 填满后台搜索词字段
2. **禁止重复** — 不包含标题、五点、描述中已出现的词
3. **必须包含** — 拼写错误词 / 西班牙语等多语言词 / 缩写 / 型号变体 / 竞品类似词（不含品牌名）
4. **词序策略** — 后台词使用空格分隔，无序排列，让 A9 自动组合索引

## 输出格式

请严格按以下 JSON 格式输出，不要添加其他文字或 markdown 代码块标记：

{{"title": "优化后的标题", "bullet_points": ["第1条", "第2条", "第3条", "第4条", "第5条"], "description": "优化后的产品描述", "search_terms": "后台搜索关键词（接近250字节，空格分隔）", "optimization_notes": "流量优化说明：\\n【关键词宽度】已覆盖的意图类型和词组...\\n【同义词矩阵】...\\n【后台词策略】...\\n【预期流量提升】..."}}
"""


# ═══════════════════════════════════════════════
# 自定义优化提示词构建函数
# ═══════════════════════════════════════════════

_TONE_DESCRIPTIONS = {
    "professional": "专业、严谨、权威，适合商务或高品质产品",
    "friendly": "亲切、温暖、易于接近，像朋友推荐，适合家居日用品",
    "luxury": "高端、优雅、彰显品味，适合溢价产品或礼品类目",
    "budget": "实惠、实用、性价比突出，强调价值感，适合价格敏感类目",
    "technical": "技术性、数据驱动、专业参数丰富，适合电子/工具类产品",
}


def build_custom_optimize_prompt(
    *,
    system_prompt: str,
    asin: str, marketplace: str,
    title: str, brand: str, price: str, currency: str,
    rating: str, review_count: str, category: str, bsr_rank: str,
    bullet_points_text: str, description: str,
    target_keywords: str, target_audience: str, output_language: str,
    custom_instructions: str = "",
    tone: str = "professional",
    focus_point: str = "",
    extra_context: str = "",
    title_strategy: str = "",
    bullet_style: str = "",
    competitor_section: str = "",
) -> str:
    """根据用户自定义参数构建优化提示词。"""
    tone_desc = _TONE_DESCRIPTIONS.get(tone, _TONE_DESCRIPTIONS["professional"])

    custom_block_parts = []
    if custom_instructions:
        custom_block_parts.append(f"### 核心优化指令（最高优先级）\n{custom_instructions}")
    if focus_point:
        custom_block_parts.append(f"### 重点优化方向\n{focus_point}")
    if title_strategy:
        custom_block_parts.append(f"### 标题优化策略\n{title_strategy}")
    if bullet_style:
        custom_block_parts.append(f"### 五点描述风格\n{bullet_style}")
    if extra_context:
        custom_block_parts.append(f"### 额外背景信息\n{extra_context}")

    custom_block = "\n\n".join(custom_block_parts) if custom_block_parts else "请根据产品信息自主判断最优优化方向。"

    return f"""\
{system_prompt}

## 当前任务
根据用户的**自定义优化参数**，对以下产品 Listing 进行个性化优化。

## 原始产品数据
- **ASIN**: {asin}
- **站点**: {marketplace}
- **当前标题**: {title}
- **品牌**: {brand}
- **价格**: {price} {currency}
- **评分**: {rating}（{review_count} 条评论）
- **类目**: {category}
- **BSR 排名**: {bsr_rank}
- **当前五点描述**:
{bullet_points_text}
- **当前描述**:
{description}
{competitor_section}
## 用户指定的重点关键词
{target_keywords}

## 目标受众
{target_audience}

## 输出语言
{output_language}

## ══════════════════════════════════════════
## 用户自定义优化参数
## ══════════════════════════════════════════

### 文案风格
**{tone}**：{tone_desc}
请确保所有文案（标题、五点、描述）的语气、措辞和表达方式与此风格保持高度一致。

{custom_block}

## 基础优化要求（在满足上述自定义要求的前提下）
1. **标题** — 200 字符以内，结构合理，关键词自然分布
2. **五点描述** — 恰好 5 条，每条 150-250 字符，以大写短语开头
3. **产品描述** — 300-2000 字符，内容丰富，补充五点未展开的细节
4. **搜索关键词** — 接近 250 字节，不重复标题中已有词
5. **合规性** — 不使用违禁词、不全大写、不包含竞品品牌

## 输出格式

请严格按以下 JSON 格式输出，不要添加其他文字或 markdown 代码块标记：

{{"title": "优化后的标题", "bullet_points": ["第1条", "第2条", "第3条", "第4条", "第5条"], "description": "优化后的产品描述", "search_terms": "后台搜索关键词（空格分隔）", "optimization_notes": "自定义优化说明：\\n【执行的自定义指令】...\\n【文案风格体现】...\\n【优化亮点】..."}}
"""


REFINE_LISTING_PROMPT = """\
{system_prompt}

## 当前任务
用户对之前优化的 Listing 提出了修改意见，请根据用户反馈对 Listing 进行**针对性修改**。

## 当前 Listing 内容
- **ASIN**: {asin}
- **站点**: {marketplace}
- **标题**: {current_title}
- **五点描述**:
{current_bullets_text}
- **描述**: {current_description}
- **后台搜索关键词**: {current_search_terms}

## 用户修改意见
{user_feedback}

## 修改要求
1. 严格按照用户修改意见进行调整
2. 未被提及的部分保持不变或做适当微调以保持整体一致性
3. 修改后仍需符合 Amazon Listing 的 SEO 最佳实践
4. 在 optimization_notes 中说明本次修改了哪些内容

## 输出格式
请严格按以下 JSON 格式输出，不要添加其他文字或 markdown 代码块标记：

{{"title": "修改后的标题", "bullet_points": ["第1条", "第2条", "第3条", "第4条", "第5条"], "description": "修改后的产品描述", "search_terms": "后台搜索关键词（空格分隔）", "optimization_notes": "本次修改说明"}}
"""

# ═══════════════════════════════════════════════
# 四维算法评判规则（COSMO / 关键词 / Rufus / IDQ）
# ═══════════════════════════════════════════════

EVALUATE_LISTING_PROMPT = """\
{system_prompt}

## 当前任务
对以下 Amazon 产品 Listing 进行 **四维算法深度评判**，从亚马逊搜索与推荐引擎的底层逻辑出发，
评估该 Listing 在 COSMO 关系覆盖、关键词覆盖、Rufus 语义覆盖、IDQ 语义完整性四个维度的表现。

## 产品数据
- **ASIN**: {asin}
- **站点**: {marketplace}
- **标题**: {title}
- **品牌**: {brand}
- **价格**: {price} {currency}
- **评分**: {rating}（{review_count} 条评论）
- **类目**: {category}
- **BSR 排名**: {bsr_rank}
- **五点描述**:
{bullet_points_text}
- **描述**:
{description}
- **后台搜索关键词**: {search_terms}

## 评判框架（满分 100 分）

请严格按照以下四个维度逐一评判，每个维度 25 分。

---

### 维度一：COSMO 关系覆盖（25 分）

> **背景**: COSMO（Customer Obsession Shopping Model）是亚马逊的知识图谱模型，
> 通过构建「用户意图 → 产品属性 → 使用场景 → 购买决策」的实体关系网络来理解产品。
> Listing 必须建立清晰的语义实体关系，才能被 COSMO 正确索引和推荐。

请逐项评分：

**1.1 实体关系完整性（5 分）**
- 产品类型 ↔ 核心属性（材质/尺寸/颜色/功能）的关系是否在 Listing 中显式表达？
- 品牌 ↔ 产品线 ↔ 具体型号的层级关系是否清晰？
- 评分标准：5 项以上实体关系清晰 = 5 分；3-4 项 = 3 分；1-2 项 = 1 分；无 = 0 分

**1.2 用户意图映射（5 分）**
- Listing 是否覆盖了该品类消费者的典型搜索意图？
  （如：功能型意图 "blackout curtains"、场景型意图 "bedroom curtains"、问题解决型意图 "curtains that block light"）
- 是否涵盖「知道想要什么」和「探索性浏览」两类意图？
- 评分标准：3 种以上意图类型全覆盖 = 5 分；2 种 = 3 分；1 种 = 1 分

**1.3 使用场景覆盖（5 分）**
- 是否提供了至少 3 个具体使用场景？（如：卧室、客厅、办公室、RV 等）
- 场景描述是否关联了产品功能？（如："遮光功能适合卧室午睡"）
- 评分标准：3 个以上场景且有功能关联 = 5 分；2 个场景 = 3 分；1 个或无关联 = 1 分

**1.4 购买决策路径引导（5 分）**
- 是否通过对比/数据/认证等方式降低购买决策门槛？
- 是否有社会证明（如 "trusted by X families"）、质量认证（如 OEKO-TEX）、售后保障等信任要素？
- 评分标准：包含 3 项以上信任/决策要素 = 5 分；2 项 = 3 分；1 项 = 1 分

**1.5 属性-需求关联度（5 分）**
- 每个产品属性是否对应了消费者的具体需求/痛点？
  （如：三层织物 → 隔热保温；环保面料 → 母婴安全）
- 是否存在"孤立属性"（仅列出规格但未关联用途/好处）？
- 评分标准：所有关键属性均关联需求 = 5 分；大部分关联 = 3 分；多数孤立 = 1 分

---

### 维度二：关键词覆盖（25 分）

> **背景**: Amazon A9/A10 搜索算法通过关键词匹配决定产品在搜索结果中的排位。
> 关键词策略需覆盖核心词、长尾词、同义词，并合理分布在 Title / Bullets / Description / Search Terms 四个位置。

请逐项评分：

**2.1 核心关键词命中（5 分）**
- 该品类 TOP 3-5 搜索量最高的核心关键词是否出现在标题中？
- 核心关键词是否位于标题前 80 个字符？（前端搜索结果展示截断位置）
- 评分标准：TOP5 核心词全部在标题前 80 字符 = 5 分；部分在 = 3 分；缺失核心词 = 1 分

**2.2 长尾关键词分布（5 分）**
- 五点描述中是否覆盖了至少 10 个有效长尾关键词？
- 长尾词是否自然融入语句、而非简单罗列堆砌？
- 描述中是否包含标题和要点未覆盖的补充长尾词？
- 评分标准：≥15 个自然分布的长尾词 = 5 分；10-14 个 = 3 分；<10 个 = 1 分

**2.3 关键词位置权重优化（5 分）**
- 是否遵循 Title > Bullet Points > Description > Search Terms 的权重递减布局？
- 高搜索量词是否优先放在权重更高的位置？
- 低频但精准的词是否补充在后台搜索词中？
- 评分标准：层级策略合理且有明确意图 = 5 分；部分合理 = 3 分；无策略 = 1 分

**2.4 同义词与变体覆盖（5 分）**
- 是否覆盖了同一产品/功能的不同表达方式？
  （如：curtain / drape / window covering / window treatment）
- 是否包含常见拼写错误或缩写形式？
- 是否考虑了目标市场的语言习惯差异？（如 US vs UK 英语差异）
- 评分标准：≥5 组同义词/变体 = 5 分；3-4 组 = 3 分；<3 组 = 1 分

**2.5 关键词密度与自然度（5 分）**
- 关键词密度是否控制在 2%-5% 的合理区间？
- 是否避免了关键词堆砌（keyword stuffing）导致的可读性下降？
- 读起来是否像人写的营销文案而非 SEO 机器生成？
- 评分标准：密度合理且阅读流畅 = 5 分；略有堆砌感 = 3 分；明显堆砌 = 1 分

---

### 维度三：Rufus 语义覆盖（25 分）

> **背景**: Rufus 是亚马逊的 AI 购物助手，使用大语言模型理解 Listing 内容，
> 并在购物过程中回答消费者的自然语言提问。Listing 必须提供结构化、可问答的信息，
> 使 Rufus 能够准确提取并向消费者推荐产品。

请逐项评分：

**3.1 产品核心信息可问答性（5 分）**
- Rufus 能否从 Listing 中回答"这个产品是什么？做什么用的？"
- 产品的核心功能和价值主张是否在前 2 个要点中明确表达？
- 评分标准：1 句话即可概括产品价值 = 5 分；需要拼凑 = 3 分；模糊不清 = 1 分

**3.2 规格参数结构化程度（5 分）**
- 尺寸、材质、重量、颜色等关键规格是否以「属性: 值」的结构化方式呈现？
- Rufus 能否精准提取 "这个窗帘多大？" "什么材质？" 等常见问题的答案？
- 评分标准：≥5 项规格结构化呈现 = 5 分；3-4 项 = 3 分；<3 项 = 1 分

**3.3 使用方法与安装引导（5 分）**
- 是否包含安装/使用步骤或方法说明？
- Rufus 能否回答"怎么安装？""怎么清洗？""怎么使用？"类问题？
- 评分标准：有明确的使用/安装指引 = 5 分；简略提及 = 3 分；完全未提及 = 0 分

**3.4 竞品差异可识别性（5 分）**
- 消费者问 "这个产品和其他产品有什么区别？" 时，Rufus 能否提取明确的差异化卖点？
- 是否有量化的差异化表述？（如 "3X thicker than standard curtains"）
- 评分标准：≥3 个可量化的差异点 = 5 分；1-2 个 = 3 分；无差异化表述 = 0 分

**3.5 FAQ 隐式覆盖（5 分）**
- 是否在 Listing 中隐式回答了该品类的 TOP 常见问题？
  常见问题类型：
  · 尺寸/兼容性："适合多大的窗户？"
  · 维护保养："可以机洗吗？"
  · 耐用性："能用多久？"
  · 安全性："对孩子/宠物安全吗？"
  · 退换货："不满意可以退吗？"
- 评分标准：隐式覆盖 5 个以上常见问题 = 5 分；3-4 个 = 3 分；<3 个 = 1 分

---

### 维度四：IDQ 语义完整性（25 分）

> **背景**: IDQ（Indexing & Detail Page Quality）是亚马逊衡量 Listing 内容质量的核心指标体系，
> 影响搜索索引收录质量和详情页的转化率。IDQ 要求 Listing 在内容完整性、合规性、
> 各板块协同性上达到高标准。

请逐项评分：

**4.1 必填属性完整度（5 分）**
- 标题是否包含：品牌 + 产品类型 + 关键属性（材质/尺寸/颜色）+ 数量/规格？
- 五点描述是否覆盖：核心卖点、材质工艺、尺寸规格、使用场景、售后保障？
- 描述是否有实质内容（非空白/非纯复制五点内容）？
- 后台搜索词是否已填写且未重复标题中已有词？
- 评分标准：四个板块全部完整填写 = 5 分；缺少 1 个 = 3 分；缺少 2 个以上 = 1 分

**4.2 内容丰富度指标（5 分）**
- 标题字符数是否在 150-200 字符的最优区间？（过短浪费权重，过长被截断）
- 五点描述每条是否在 150-250 字符？是否恰好 5 条？
- 描述是否在 300-2000 字符？
- 后台搜索词是否接近 250 字节上限？
- 评分标准：四项均在最优区间 = 5 分；3 项达标 = 3 分；2 项以下 = 1 分

**4.3 品类特定属性覆盖（5 分）**
- 是否覆盖了该品类买家最关注的特有属性？
  （如窗帘类目：遮光等级、杆类型、面料成分、是否含配件、挂法方式等）
- 这些品类属性是否同时出现在结构化信息和文案描述中？
- 评分标准：≥5 个品类关键属性全覆盖 = 5 分；3-4 个 = 3 分；<3 个 = 1 分

**4.4 合规性检查（5 分）**
- 标题是否避免了禁止词？（"Best Seller"、"Free Shipping"、"#1"、全大写等）
- 是否避免了竞品品牌名侵权？
- 是否避免了医疗/功效性违规声明？
- 五点描述是否避免了 HTML 标签、特殊符号堆砌、URL 链接？
- 评分标准：完全合规 = 5 分；有 1 处轻微违规 = 3 分；有明显违规 = 0 分

**4.5 标题/要点/描述/搜索词协同性（5 分）**
- 四个板块之间是否形成互补关系？（而非简单复制粘贴）
- 标题聚焦核心词、要点展开卖点、描述讲故事/补充细节、搜索词覆盖遗漏——是否层层递进？
- 是否避免了关键信息仅出现在单一板块的"信息孤岛"问题？
- 评分标准：四板块协同互补、层次分明 = 5 分；部分重叠但基本合理 = 3 分；大量重复 = 1 分

---

## 输出格式

请严格按以下 JSON 格式输出，不要添加其他文字或 markdown 代码块标记：

{{"scores": {{"cosmo": {{"entity_relations": 0, "intent_mapping": 0, "scene_coverage": 0, "decision_path": 0, "attribute_need_link": 0, "subtotal": 0}}, "keywords": {{"core_keywords": 0, "longtail_distribution": 0, "position_weight": 0, "synonyms_variants": 0, "density_naturalness": 0, "subtotal": 0}}, "rufus": {{"core_info_qa": 0, "spec_structure": 0, "usage_guide": 0, "competitive_diff": 0, "faq_coverage": 0, "subtotal": 0}}, "idq": {{"required_attrs": 0, "content_richness": 0, "category_attrs": 0, "compliance": 0, "synergy": 0, "subtotal": 0}}, "total": 0}}, "analysis": {{"cosmo": {{"summary": "COSMO 维度整体评价", "strengths": ["优势 1", "优势 2"], "weaknesses": ["不足 1", "不足 2"], "suggestions": ["建议 1", "建议 2"]}}, "keywords": {{"summary": "关键词维度整体评价", "identified_core_keywords": ["已识别的核心关键词列表"], "missing_keywords": ["缺失的重要关键词"], "strengths": ["优势 1"], "weaknesses": ["不足 1"], "suggestions": ["建议 1"]}}, "rufus": {{"summary": "Rufus 维度整体评价", "answerable_questions": ["Rufus 可回答的问题示例"], "unanswerable_questions": ["Rufus 无法回答的问题示例"], "strengths": ["优势 1"], "weaknesses": ["不足 1"], "suggestions": ["建议 1"]}}, "idq": {{"summary": "IDQ 维度整体评价", "content_stats": {{"title_chars": 0, "bullet_count": 0, "avg_bullet_chars": 0, "description_chars": 0, "search_terms_bytes": 0}}, "compliance_issues": ["合规问题列表，无则为空数组"], "strengths": ["优势 1"], "weaknesses": ["不足 1"], "suggestions": ["建议 1"]}}}}, "overall_summary": "综合评判总结（200 字以内）", "priority_actions": ["优先行动 1（最紧急）", "优先行动 2", "优先行动 3"]}}
"""


CONVERSION_EVALUATE_PROMPT = """\
{system_prompt}

## 当前任务
这是一条优化后的亚马逊产品 Listing。请你作为熟悉亚马逊 CTR/CVR 经营的运营 / 文案专家，
**仅从"转化能力"这一单一视角**给这条 Listing 打出一个 **0-100 分** 的综合分。
不要评估曝光/搜索覆盖类问题（关键词覆盖、SEO 搜索命中等），这部分由另一套评分负责。

聚焦以下转化维度（综合判断，不需要逐项给分）：
- 买家第一眼被吸引的程度（标题吸引力、主卖点突出度、钩子是否在前 80 字符）
- 对 CTR 的推动：价值主张是否能击中目标用户的搜索意图
- 对 CVR 的推动：五点和描述是否能解决购买犹豫（尺寸 / 兼容性 / 耐用 / 售后 / 对比优势）
- 信任要素密度（数据 / 认证 / 社会证明 / 保障承诺）
- 决策阻力与风险：是否还有让买家犹豫的疑问没答、是否有合规 / 可读性上的转化杀手

## 产品基础信息（仅供品类辨识，非评分对象）
- **品牌**: {brand}
- **类目**: {category}
- **站点**: {marketplace}

## 待评 Listing 全文

### 标题
{title}

### 五点描述
{bullet_points_text}

### 产品描述
{description}

### 后台搜索关键词
{search_terms}

## 输出格式
请严格按以下 JSON 输出，不要添加其他文字或 markdown 代码块标记：

{{"total": 0, "summary": "一句话转化力评价（50 字以内）", "strengths": ["促进转化的亮点 1"], "weaknesses": ["影响转化的短板 1"], "suggestions": ["拉高转化的改进 1"]}}
"""

# 保留旧名作为别名，兼容外部已有引用
FREE_FORM_EVALUATE_PROMPT = CONVERSION_EVALUATE_PROMPT


_FAB_WRITING_GUIDELINE = """

## FAB 写作原则（必须遵循）
撰写五点描述时，每一条必须严格遵循 **F→A→B 三层结构**：
1. **Feature（特点）**：先陈述产品的客观特点/属性/工艺/规格（是什么）
2. **Advantage（优势）**：再阐明该特点相比竞品或普通产品的优越之处（为什么好）
3. **Benefit（利益）**：最后落脚到消费者能获得的实际价值、好处或情感满足（对我有什么用）

示例：错误："Made of premium cotton（只有Feature）"
正确："PREMIUM 100% COMBED COTTON — 3x softer than standard polyester blends, so you sleep cooler and wake up refreshed every morning"
（Feature: 100%精梳棉 → Advantage: 比普通聚酯混纺柔软3倍 → Benefit: 更凉快睡眠更好）
"""


def append_fab_to_prompt(prompt: str) -> str:
    """在任意优化 prompt 末尾追加 FAB 写作原则指导。不改变 JSON 输出格式，仅约束写作结构。"""
    return prompt.rstrip() + _FAB_WRITING_GUIDELINE


FAB_ANALYZE_PROMPT = """\
你是一位亚马逊 Listing 文案策略专家，精通 FAB 销售法则。

## FAB 说明
- **Feature（特点）**：产品本身具备的客观属性或功能（材质、尺寸、工艺、技术规格等）
- **Advantage（优势）**：该特点相比竞品/替代品的优越性（更轻、更耐用、更节能等）
- **Benefit（利益）**：该优势能给消费者带来的实际价值/好处/情感满足（省时、省钱、更安全、更有面子等）

## 任务
请对以下亚马逊产品五点描述的每一条进行 FAB 拆解分析，评估 F/A/B 三要素是否完整、是否清晰，并给出改进建议。

## 产品信息
- **标题**: {title}
- **品牌**: {brand}
- **类目**: {category}

## 五点描述
{bullets_text}

## 输出要求
请严格按以下 JSON 格式输出（不要加 markdown 代码块标记）：

{{
  "points": [
    {{
      "bullet": "原文五点条目（完整复制）",
      "feature": "提炼出的 Feature（特点），若缺失则写空字符串",
      "advantage": "提炼出的 Advantage（优势），若缺失则写空字符串",
      "benefit": "提炼出的 Benefit（利益），若缺失则写空字符串",
      "score": 评分0-100（F/A/B都有且清晰=90-100，缺一个=60-80，缺两个=30-59，三个都缺=0-29）,
      "suggestion": "针对该条的简短改进建议（如已完整则写"已完整"）"
    }}
  ],
  "overall_score": 所有条目score的平均值（整数）,
  "summary": "整体 FAB 完整度总结，以及最重要的 1-2 条改进方向（100字以内）"
}}
"""


ANALYZE_LISTING_PROMPT = """\
{system_prompt}

## 当前任务
对以下 Amazon 产品 Listing 进行**全面诊断分析**，从 SEO、转化率、竞争力等维度进行评估。

## 产品数据
- **ASIN**: {asin}
- **站点**: {marketplace}
- **标题**: {title}
- **品牌**: {brand}
- **价格**: {price} {currency}
- **评分**: {rating}（{review_count} 条评论）
- **类目**: {category}
- **BSR 排名**: {bsr_rank}
- **五点描述**:
{bullet_points_text}
- **描述**:
{description}

## 请从以下维度评分并分析（每项满分 20 分，总分 100 分）

### 1. 标题质量（20分）
- 关键词覆盖度
- 结构合理性
- 字符长度利用率
- 可读性

### 2. 五点描述（20分）
- 卖点提炼是否到位
- 关键词嵌入自然度
- 信息完整性（材质、尺寸、场景、保障）
- 格式规范性

### 3. 产品描述（20分）
- 内容丰富度
- SEO 优化程度
- 阅读体验
- 转化引导

### 4. 关键词策略（20分）
- 核心关键词覆盖
- 长尾词布局
- 竞品词切入
- 关键词密度合理性

### 5. 整体竞争力（20分）
- 价格竞争力
- 评论基础
- 品牌建设
- 差异化程度

## 输出要求
- 使用中文回答
- 给出每个维度的具体评分和分析
- 总结主要优势和待改进项
- 给出 3-5 条优先级排序的优化建议
- 最后给出总分
"""


# ═══════════════════════════════════════════════
# 增强优化提示词（COSMO + FAB + 评论洞察 + 痛点检查）
# ═══════════════════════════════════════════════


def _build_review_insights_section(review_analysis) -> str:
    """从 ReviewAnalysisResult 构建产品评论洞察段落。"""
    if not review_analysis:
        return ""

    parts = ["## 产品评论洞察（LLM 分析结果）\n"]
    parts.append("> 以下信息来自真实用户评论的 AI 分析，请在优化时充分利用这些洞察。\n")

    if review_analysis.selling_points:
        parts.append("### 用户认可的产品卖点")
        for sp in review_analysis.selling_points:
            freq = {"high": "高频", "medium": "中频", "low": "低频"}.get(sp.frequency, "")
            parts.append(f"- **{sp.title}**（{freq}）：{sp.detail}")
        parts.append("")

    if review_analysis.core_features:
        parts.append("### 产品核心特点")
        for cf in review_analysis.core_features:
            sentiment_map = {"positive": "+", "neutral": "~", "negative": "-"}
            mark = sentiment_map.get(cf.sentiment, "~")
            parts.append(f"- [{mark}] **{cf.title}**：{cf.detail}")
        parts.append("")

    if review_analysis.pain_points:
        parts.append("### 用户痛点与不满")
        for pp in review_analysis.pain_points:
            freq = {"high": "高频", "medium": "中频", "low": "低频"}.get(pp.frequency, "")
            parts.append(f"- **{pp.title}**（{freq}）：{pp.detail}")
        parts.append("")

    if review_analysis.summary:
        parts.append(f"### 综合摘要\n{review_analysis.summary}\n")

    return "\n".join(parts)


def _build_pain_point_checklist(review_analysis) -> str:
    """从痛点列表生成检查清单，要求 LLM 在五点描述中回应。"""
    if not review_analysis or not review_analysis.pain_points:
        return ""

    high_medium = [
        pp for pp in review_analysis.pain_points
        if pp.frequency in ("high", "medium")
    ]
    if not high_medium:
        return ""

    lines = [
        "## 痛点回应检查（必须完成）\n",
        "以下痛点是用户评论中的高频/中频问题，优化后的五点描述**必须**通过正面表述或信任信号回应这些痛点：\n",
    ]
    for i, pp in enumerate(high_medium[:5], 1):
        lines.append(
            f"{i}. **{pp.title}** — {pp.detail}\n"
            f"   → 请在五点描述中用积极语言回应此痛点（如：强调产品如何避免/解决此问题）"
        )
    lines.append(
        "\n在 `pain_point_coverage` 字段中记录每个痛点被哪条 Bullet 回应。"
    )
    return "\n".join(lines)


def build_enhanced_optimize_prompt(
    *,
    system_prompt: str,
    product,
    target_keywords: list[str],
    target_audience: str,
    output_language: str,
    review_analysis=None,
    competitor_products: list | None = None,
    overrides: dict | None = None,
) -> str:
    """基于 COSMO 算法 + FAB 文案逻辑 + 评论洞察的增强优化提示词。

    核心差异：
    1. 代码级组装（非简单模板 format）
    2. 融合评论分析的卖点/痛点到提示词
    3. 要求 LLM 对每条 Bullet 生成 3 条备选（主选 + 2 备选）
    4. 每条 Bullet 严格遵循 FAB 结构并输出拆解
    """
    cfg = {**PROMPT_DEFAULTS, **(overrides or {})}

    bullet_text = (
        "\n".join(f"  - {b}" for b in product.bullet_points)
        if product.bullet_points else "  （无）"
    )
    kw_text = (
        ", ".join(target_keywords) if target_keywords
        else "（未指定，请根据产品类型自动选择高搜索量关键词）"
    )
    audience_text = target_audience or "（未指定，请根据产品类型自动推断目标受众）"

    sections: list[str] = []

    # ── 1. 身份 + 任务 ──
    sections.append(f"""\
{system_prompt}

## 当前任务
基于亚马逊 **COSMO 四维算法**与 **FAB 文案法则**，结合真实用户评论洞察，对以下产品 Listing 进行深度优化。
你必须确保：
- 四维算法（COSMO/关键词/Rufus/IDQ）每个维度都达到高分
- 每条五点描述严格遵循 FAB 结构
- 充分利用评论中的卖点和痛点
- 对每条五点描述提供 **1 条主选 + 2 条备选**，共 3 个方案""")

    # ── 2. 原始产品数据 ──
    sections.append(f"""\
## 原始产品数据
- **ASIN**: {product.asin}
- **站点**: {product.marketplace}
- **当前标题**: {product.title or "（未获取到）"}
- **品牌**: {product.brand or "（未知）"}
- **价格**: {product.price or "N/A"} {product.currency or ""}
- **评分**: {product.rating or "N/A"}（{product.review_count or "0"} 条评论）
- **类目**: {product.category or "（未获取到）"}
- **BSR 排名**: {product.bsr_rank or "N/A"}
- **当前五点描述**:
{bullet_text}
- **当前描述**:
{product.description or "（无）"}""")

    # ── 3. 评论洞察 ──
    review_section = _build_review_insights_section(review_analysis)
    if review_section:
        sections.append(review_section)

    # ── 4. 竞品参考 ──
    if competitor_products:
        comp_parts: list[str] = []
        for i, cp in enumerate(competitor_products, 1):
            bp = "\n".join(f"  - {b}" for b in cp.bullet_points) if cp.bullet_points else "  （无）"
            comp_parts.append(
                f"### 竞品 {i}（{cp.asin}）\n"
                f"- **标题**: {cp.title or '（无）'}\n"
                f"- **品牌**: {cp.brand or '（未知）'}\n"
                f"- **价格**: {cp.price or 'N/A'} {cp.currency or ''}\n"
                f"- **评分**: {cp.rating or 'N/A'}（{cp.review_count or '0'} 条评论）\n"
                f"- **五点描述**:\n{bp}"
            )
        sections.append(
            "## 竞品 Listing 参考\n"
            "请分析以下竞品的优劣势，在优化时取长补短、差异化竞争。\n\n"
            + "\n\n".join(comp_parts)
        )

    # ── 5. 关键词 + 受众 + 语言 ──
    sections.append(f"""\
## 用户指定的重点关键词
{kw_text}

## 目标受众
{audience_text}

## 输出语言
{output_language}""")

    # ── 6. COSMO 四维策略（精简版，核心要求） ──
    sections.append("""\
## ══════════════════════════════════════════
## COSMO 四维优化策略（必须逐一满足）
## ══════════════════════════════════════════

### 策略一：COSMO 关系覆盖
1. **实体关系显式化** — 标题和要点中必须显式建立产品类型 ↔ 核心属性的关系
2. **多意图覆盖** — 覆盖至少 3 种用户搜索意图类型（功能型/场景型/问题解决型）
3. **场景-功能关联** — 每个使用场景必须关联具体产品功能
4. **信任要素植入** — 至少包含 3 项购买决策信任要素（认证/量化数据/社会证明/售后保障）
5. **属性-需求绑定** — 每个产品属性必须绑定消费者痛点/需求

### 策略二：关键词覆盖
1. **标题前 80 字符** — 必须包含该品类 TOP 3 核心搜索词
2. **五点描述** — 每条至少嵌入 2-3 个长尾关键词，自然融入不堆砌
3. **描述补充** — 覆盖标题和要点未出现的补充长尾词和语义变体
4. **后台搜索词** — 填满接近 250 字节，仅放标题/要点中未出现的同义词、拼写变体
5. **密度控制** — 关键词密度 2%-5%，读起来像营销文案而非 SEO 机器文

### 策略三：Rufus 语义覆盖
1. **核心价值 1 句话可答** — 前 2 个 Bullet 必须让 Rufus 能回答"这个产品是什么？"
2. **规格结构化** — 尺寸/材质/重量等以「属性: 值」格式呈现
3. **使用/安装指引** — 至少 1 个 Bullet 包含使用方法
4. **量化差异化** — 至少 3 处用量化数据表达差异
5. **隐式 FAQ 覆盖** — Listing 能让 Rufus 回答至少 5 个常见问题

### 策略四：IDQ 语义完整性
1. **标题** — 150-200 字符，品牌 + 核心词 + 属性 + 卖点 + 规格
2. **五点描述** — 恰好 5 条，每条 150-250 字符，以大写短语开头
3. **描述** — 300-2000 字符，讲产品故事，补充要点未展开的细节
4. **搜索词** — 接近 250 字节上限，不重复标题已有词
5. **合规性** — 禁止 "Best Seller"/"Free Shipping"/全大写/竞品品牌名
6. **四板块协同** — 标题聚焦 → 要点展开 → 描述讲故事 → 搜索词补遗漏""")

    # ── 7. FAB + 备选方案要求 ──
    sections.append("""\
## ══════════════════════════════════════════
## 五点描述 FAB 结构要求
## ══════════════════════════════════════════

每条五点描述**必须**严格遵循 **F→A→B 三层结构**：
- **Feature（特点）**：产品的客观属性/工艺/规格（是什么）
- **Advantage（优势）**：该特点相比竞品的优越之处（为什么好）
- **Benefit（利益）**：消费者获得的实际价值/情感满足（对我有什么用）

**写作要求**：
- 每条只产出 **1 条**最终文案（综合最优，平衡 SEO + 转化，不需要备选）
- 每条开头以 **大写加粗关键词短语** 开头（如 "PREMIUM MATERIAL"）
- 每条 150-250 字符

**5 条的主题分配**：
- 第 1 条：核心卖点/功能（结合评论中最高频卖点）
- 第 2 条：材质工艺/品质差异化
- 第 3 条：尺寸规格与兼容性/使用场景
- 第 4 条：使用体验/安装便捷/多场景适用
- 第 5 条：售后保障/品牌承诺/风险消除""")

    # ── 8. 痛点回应检查 ──
    pain_section = _build_pain_point_checklist(review_analysis)
    if pain_section:
        sections.append(pain_section)

    # ── 9. 输出格式 ──
    sections.append("""\
## 输出格式

请严格按以下 JSON 格式输出，不要添加其他文字或 markdown 代码块标记：

{"title": "优化后的标题", "bullet_points": ["第1条（FAB结构，大写关键词开头）", "第2条（FAB结构）", "第3条（FAB结构）", "第4条（FAB结构）", "第5条（FAB结构）"], "description": "优化后的产品描述", "search_terms": "后台搜索关键词（空格分隔）", "optimization_notes": "优化说明", "pain_point_coverage": {"痛点标题": "回应该痛点的Bullet编号和方式"}}""")

    return "\n\n".join(sections)
