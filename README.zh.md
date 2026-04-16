<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.md">English</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/style-dataset-lab/readme.png" width="400">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@mcptoolshop/style-dataset-lab"><img src="https://img.shields.io/npm/v/@mcptoolshop/style-dataset-lab" alt="npm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

编写您的视觉规则。生成艺术作品。根据这些规则评估每张图像。将结果作为版本控制的、可审计的训练数据发布。

Style Dataset Lab 将您关于艺术风格的描述与实际用于训练的数据集联系起来。您定义一套规范，包括轮廓规则、调色板限制、材质语言，以及对您的项目而言重要的任何内容。流水线生成候选作品，根据这些规则对其进行评分，并将通过的成果打包成可重复的数据集，其中每个记录都解释了它被包含的原因。

循环闭合：训练一个模型，生成新的输出，根据相同的标准对其进行评分，并将通过的作品重新导入。数据集不断增长，规则始终有效。

## 流水线

```bash
# Write your canon. Scaffold the project.
sdlab init my-project --domain character-design

# Generate candidates via ComfyUI, then review them
sdlab generate inputs/prompts/wave1.json --project my-project
sdlab curate <id> approved "Strong silhouette, correct faction palette"

# Bind approved work to constitution rules
sdlab bind --project my-project

# Freeze a versioned dataset
sdlab snapshot create --project my-project
sdlab split build
sdlab export build

# Build a training package and close the loop
sdlab training-manifest create --profile character-style-lora
sdlab training-package build
sdlab eval-run create && sdlab eval-run score <id> --outputs results.jsonl
sdlab reingest generated --source ./outputs --manifest <id>
```

那个最后的命令至关重要。生成的输出会经过与所有其他内容相同的审查流程。循环闭合。

## 它产生的内容

七个版本控制的、具有校验和的成果。每个成果都链接到其前身，因此您可以追溯任何训练记录，了解它是根据哪个规则被批准的。

| 成果 | 它的定义 |
|----------|-----------|
| **Snapshot** | 带有配置指纹的冻结记录选择。每个包含项都有明确的理由。 |
| **Split** | 训练/验证/测试数据集，其中主题类别之间绝不交叉。 |
| **Export package** | 自包含的数据集：清单、元数据、图像、数据集划分、数据集描述、校验和。 |
| **Eval pack** | 与规范相关的测试任务：覆盖范围、避免偏差、锚定/黄金标准、主题连续性。 |
| **Training package** | 通过适配器（`diffusers-lora`、`generic-image-caption`）提供可供训练器使用的布局。相同的真理，不同的格式。 |
| **Eval scorecard** | 每个任务的通过/失败结果，基于生成的输出与评估包的比较。 |
| **Implementation pack** | 提示示例、已知的失败案例、连续性测试以及重新导入指南。 |

## 存在的理由

训练数据是任何视觉人工智能流水线中最具价值的资源。但大多数训练数据只是一个包含图像的文件夹，没有任何历史记录、评估记录，以及与它应该遵循的风格规则的联系。

Style Dataset Lab 明确地建立了这种联系。您的规范定义了规则。您的评分标准定义了评分维度。您的筛选记录记录了评估结果。您的规范证明了这种联系。您的数据集将所有这些信息以结构化、可查询、可重复的方式传递下去。

实际结果：当您的 LoRA 出现偏差时，您可以询问*原因*。当您的下一个训练轮需要更好的数据时，您清楚地知道哪些记录是接近理想的，以及它们违反了哪个规则。当新团队成员询问项目的视觉语言是什么时，答案不是一个 Figma 板，而是一份包含 1182 个已评分示例的可搜索规范。

## 五个领域，真实的规则

不是占位符模板。每个领域都包含生产级别的规范规则、定义、评分标准和词汇表。

| 领域 | 定义 | 评估内容 |
|--------|-------|-----------------|
| **game-art** | 角色、环境、道具、UI、飞船、内部、设备 | 游戏场景中的轮廓、派系特征、磨损和老化 |
| **character-design** | 人像、全身照、旋转视图、表情图、动作姿势 | 比例、服装逻辑、个性、姿势清晰度 |
| **creature-design** | 概念图、正交视图、细节研究、动作、比例参考、栖息地 | 解剖结构、进化逻辑、轮廓区分 |
| **architecture** | 外部、内部、街道景观、结构细节、废墟、景观 | 结构、材质一致性、透视、时代一致性 |
| **vehicle-mech** | 外部、驾驶舱、组件、示意图、轮廓图、损坏变体 | 机械逻辑、设计语言、访问点、损坏叙述 |

## 项目结构

每个项目都是独立的。五个 JSON 配置文件定义了规则；其他所有内容都是数据。

```
projects/my-project/
  project.json           Identity + generation defaults
  constitution.json      Rules with rationale templates
  lanes.json             Subject lanes with detection patterns
  rubric.json            Scoring dimensions + thresholds
  terminology.json       Group vocabulary + detection order
  records/               Per-asset JSON (provenance + judgment + canon)
  snapshots/             Frozen dataset snapshots
  splits/                Train/val/test partitions
  exports/               Versioned export packages
  training/              Profiles, manifests, packages, eval runs, implementations
```

## 信任属性

这些不是理想化的目标，而是强制执行的。

- **快照是不可变的。** 配置文件指纹（SHA-256）可以证明没有发生任何更改。
- **分片可以防止数据泄露。** 按照身份、血统或 ID 后缀划分的主体类别永远不会跨越分区边界。
- **清单是冻结的合同。** 导出哈希值 + 配置文件指纹。如果任何内容发生更改，请创建一个新的清单。
- **适配器不能修改原始数据。** 不同的布局，相同的记录。不允许添加、删除或重新分类。
- **生成的输出需要经过审核才能重新使用。** 不允许绕过。像其他内容一样，进行筛选和绑定。

## Star Freight

该仓库包含一个完整的示例：1182 条记录，5 个派系，7 条路线，24 条宪法规则，892 个已批准的资源，2 个训练配置文件。这是一个充满科幻感的角色扮演游戏视觉素材库，经过完整的筛选。

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## 下游格式

`sdlab` 拥有数据集。格式转换由 [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) 处理：支持 TRL、LLaVA、Qwen2-VL、JSONL、Parquet 等格式。`repo-dataset` 用于渲染，但不决定数据的包含与否。

## 安装

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

需要 Node.js 20+ 以及安装在本地主机 8188 端口上的 [ComfyUI](https://github.com/comfyanonymous/ComfyUI) 才能进行生成。

## 安全性

仅在本地运行。没有遥测数据，没有分析，没有外部请求。图像保留在您的 GPU 和文件系统中。

## 许可证

MIT

---

由 <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a> 构建。
