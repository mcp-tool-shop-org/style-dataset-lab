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

一个用于创建视觉数据集的生产流水线，从规范规则到结构化提示，再到 ComfyUI 生成，最终得到经过筛选、符合规范的训练数据。

## 这是什么

一个用于构建结构化视觉训练数据集的**流水线**。 您可以编写风格规则（规范），编写提示，使用 ComfyUI 生成图像，并根据每个维度进行评分进行筛选，将判断结果与规范规则关联，并通过 [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) 以 10 种格式导出。

该流水线不依赖于特定的游戏。 每个游戏都有自己的数据目录，位于 `games/<name>/` 目录下；13 个脚本和空白模板是共享的。 每个生成的资源都包含以下三项：

1. **图像像素**：由 ComfyUI 生成，包含完整的溯源信息（检查点、LoRA、种子、采样器、CFG）。
2. **规范解释**：解释为什么该图像符合或不符合风格，并基于风格规范进行说明。
3. **质量判断**：通过批准/拒绝，并根据每个维度的评分引用相关规则。

## 安全模型

**仅本地运行。** `style-dataset-lab` 只与本地 `localhost:8188` 上的 ComfyUI 进行通信，不会进行任何外部网络请求。 没有遥测数据，没有分析功能，不会向外部发送数据。 图像生成完全在您的 GPU 上进行。 记录和规范数据都存储在您的文件系统中。

## npm 包包含的内容

`npm install @mcptoolshop/style-dataset-lab` 会为您提供：

- **13 个脚本**：用于生成、筛选、比较、与规范关联、生成绘画风格图像、生成身份图像、使用 ControlNet/IP-Adapter 生成图像、批量筛选、数据迁移。
- **空白模板**：位于 `templates/` 目录下，包含起始规范、审查标准和示例提示包。

该 npm 包**不包含**游戏数据。 如果您想使用 Star Freight 示例，请克隆该仓库（包含 1182 条记录，28 个提示集，18 个视觉类别）。

## 安装

```bash
# Get the pipeline scripts + templates
npm install @mcptoolshop/style-dataset-lab

# Or clone the repo for the Star Freight example data
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
npm install
```

要从模板开始一个新的游戏：

```bash
# Copy templates into your game directory
mkdir -p games/my-game/{records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
cp -r templates/canon games/my-game/canon
cp templates/inputs/prompts/example-wave.json games/my-game/inputs/prompts/wave1.json
# Edit the canon and prompts, then generate
```

## 单仓库结构

流水线位于 `scripts/` 和 `templates/` 目录下。 每个游戏位于 `games/<name>/` 目录下，包含自己的规范、记录和资源。 脚本接受 `--game <name>` 参数（默认为 `star-freight`）。

```
style-dataset-lab/
  scripts/                  13 pipeline scripts (generate, curate, compare, etc.)
  templates/                Blank starting point for new games
    canon/                  Starter constitution + review rubric
    inputs/prompts/         Example prompt pack
  games/
    star-freight/           Star Freight example (1,182 records, repo-only)
      canon/                Style constitution, review rubric, species canon
      records/              Per-asset JSON (provenance + judgment + canon)
      comparisons/          A-vs-B preference judgments
      inputs/               Prompt packs, identity packets, references
      outputs/              Generated images (gitignored)
      exports/              repo-dataset output (gitignored)
    <your-game>/            Add more games with the same structure
```

## 流水线工作流程

从规范到训练数据导出的完整流水线：

```bash
# 1. Write your canon -- style constitution + review rubric
#    (start from templates/ or write from scratch)

# 2. Create prompt packs in inputs/prompts/
#    (see templates/inputs/prompts/example-wave.json)

# 3. Start ComfyUI and generate candidates
npm run generate -- --game star-freight inputs/prompts/wave1.json
npm run generate -- --game star-freight inputs/prompts/wave1.json --dry-run

# 4. Generate identity-packet characters (named subjects)
npm run generate:identity -- --game star-freight inputs/identity-packets/wave27a.json

# 5. Curate -- approve, reject, or mark borderline
npm run curate -- --game star-freight <asset_id> approved "explanation"
npm run curate -- --game star-freight <asset_id> rejected "explanation" --failures "too_clean"

# 6. Generate painterly variants of approved assets
npm run painterly -- --game star-freight

# 7. Bind canon explanations to curated assets
npm run canon-bind -- --game star-freight

# 8. Record pairwise comparisons
npm run compare -- --game star-freight <asset_a> <asset_b> a "A has better faction read"

# 9. Export training data via repo-dataset
repo-dataset visual generate ./games/star-freight --format trl
repo-dataset visual inspect ./games/star-freight
```

## 添加新的游戏

```bash
# Create structure and copy blank templates
mkdir -p games/my-game/{records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
cp -r templates/canon games/my-game/canon
cp templates/inputs/prompts/example-wave.json games/my-game/inputs/prompts/wave1.json

# Edit your canon/constitution.md and canon/review-rubric.md
# Edit your prompt pack, then run the pipeline with --game my-game
```

## 每个游戏目录的布局

每个 `games/<name>/` 目录包含：

```
canon/                  Style constitution, review rubric, species canon, identity gates
inputs/
  prompts/              Prompt packs per wave (JSON: subjects, variations, defaults)
  references/           IP-Adapter reference images
  control-guides/       ControlNet guide overlays
  identity-packets/     Named character identity spines
outputs/
  candidates/           Raw generations (gitignored)
  approved/             Curated approved (gitignored)
  rejected/             Curated rejected (gitignored)
  borderline/           Curated borderline (gitignored)
  painterly/            Painterly-style variants (gitignored)
records/                Per-asset JSON (provenance + judgment + canon binding)
comparisons/            A-vs-B preference judgments
exports/                repo-dataset output (gitignored)
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

其他生成模式：ControlNet（姿势/深度引导）、IP-Adapter（参考驱动）和身份包（用于保持角色一致性）。

## 要求

- 运行在 `localhost:8188` 上的 [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- DreamShaper XL Turbo 检查点 + ClassipeintXL LoRA
- Node.js 20+
- [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) 用于训练数据导出

## 许可证

MIT

---

由 <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a> 构建。
