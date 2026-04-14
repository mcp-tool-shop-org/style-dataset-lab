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

# style-dataset-lab

视觉数据集工厂 -- 用于生成、整理和导出多模态训练数据，以进行大型视觉语言模型（VLM）的微调。

## 这是什么

一个用于**构建可训练的视觉真理**的工具集。每个资源都包含以下三方面：

1. **图像像素** -- 由 ComfyUI 生成，并包含完整的溯源信息（检查点、LoRA、种子、采样器、CFG）。
2. **规范解释** -- 解释为什么该图像符合或不符合特定风格，并基于风格规范进行判断。
3. **质量评估** -- 经过批准/拒绝，并提供每个维度的评分以及引用规则。

输出结果通过 [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) 生成多模态训练数据，提供 10 种格式：TRL、LLaVA、Qwen2-VL、Axolotl、LLaMA-Factory、ShareGPT、RLHF 对、DPO、图像描述和分类。

## 安全模型

**仅本地运行。** style-dataset-lab 只与本地 `localhost:8188` 上的 ComfyUI 进行通信，不会进行任何外部网络请求。没有遥测数据，没有分析功能，不会向外部发送数据。图像生成完全在您的 GPU 上进行。记录和规范数据都存储在您的文件系统中。

## 数据集统计信息

| 指标 | 数值 |
|--------|-------|
| 整理记录 | 1,182 |
| 总资源数 | 2,571 (其中 893 个已批准，887 个为绘画风格变体) |
| 提示词组合 | 28 |
| 视觉类别 | 18 种 (包括：服装、船只、室内、设备、环境、物种、站点、标识、照明、货物、**架构**、生物、表面、日常生活、行星、损坏/修复、外星生物、细节)。 |
| 成对比较 | 6 个人工标注 + 71 个合成数据 |
| 不同类型的拒绝 | 30+ |
| 身份包系统 | 具有派系 DNA、等级和视觉特征的命名角色。 |
| 导出格式 | 10 种 (通过 `@mcptoolshop/repo-dataset`) |

## 安装

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

然后克隆一个项目或初始化一个新的数据集工作区：

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab my-dataset
cd my-dataset
npm install
```

## 工作流程

```bash
# 1. Start ComfyUI
# (point it at your checkpoint + LoRA setup)

# 2. Generate candidates from a prompt pack
npm run generate -- inputs/prompts/wave1.json
npm run generate -- inputs/prompts/wave1.json --dry-run

# 3. Generate identity-packet characters
npm run generate:identity -- inputs/identity-packets/wave27a-identity-spine.json

# 4. Generate painterly variants of approved assets
npm run painterly -- <asset_id>

# 5. Curate -- approve, reject, or mark borderline
npm run curate -- <asset_id> approved "explanation" --scores "silhouette:0.9,palette:0.8"
npm run curate -- <asset_id> rejected "explanation" --failures "too_clean,wrong_material"

# 6. Bind canon explanations to assets
npm run canon-bind -- <asset_id>

# 7. Record pairwise comparisons
npm run compare -- <asset_a> <asset_b> a "A has better faction read because..."

# 8. Export training data via repo-dataset
npm run export
npm run inspect
npm run validate
```

## 目录结构

```
canon/                  Style constitution, review rubric, identity gates, species canon
inputs/
  prompts/              Prompt packs per wave (JSON: subjects, variations, defaults)
  references/           IP-Adapter reference images
  control/              ControlNet control images
  control-guides/       ControlNet guide overlays
  identity-packets/     Named character identity spines (faction DNA, rank, visual anchors)
outputs/
  candidates/           Raw generations (gitignored)
  approved/             Curated approved (gitignored)
  rejected/             Curated rejected (gitignored)
  borderline/           Curated borderline (gitignored)
  painterly/            Painterly-style variants (gitignored)
records/                Per-asset JSON (provenance + judgment + canon binding)
comparisons/            A-vs-B preference judgments
exports/                repo-dataset output (gitignored)
scripts/                generate, curate, compare, canon-bind, painterly, identity gen
workflows/              Reusable ComfyUI workflow templates
```

## 生成设置

```yaml
checkpoint: dreamshaperXL_v21TurboDPMSDE.safetensors
lora: classipeintxl_v21.safetensors (weight: 1.0)
resolution: 1024x1024
steps: 8
cfg: 2.0
sampler: dpmpp_sde
scheduler: karras
speed: ~9s per image (RTX 5080)
```

其他生成模式：ControlNet（姿势/深度引导）、IP-Adapter（参考驱动）以及身份包（命名角色一致性）。

## 要求

- 运行在 `localhost:8188` 上的 [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- DreamShaper XL Turbo 检查点 + ClassipeintXL LoRA
- Node.js 20+
- [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) 用于训练数据导出

## 许可证

MIT

---

由 <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a> 构建。
