<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.md">English</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/style-dataset-lab/readme.png" width="400">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@mcptoolshop/style-dataset-lab"><img src="https://img.shields.io/npm/v/@mcptoolshop/style-dataset-lab" alt="npm"></a>
  <a href="https://github.com/mcp-tool-shop-org/style-dataset-lab/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/style-dataset-lab/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://codecov.io/gh/mcp-tool-shop-org/style-dataset-lab"><img src="https://codecov.io/gh/mcp-tool-shop-org/style-dataset-lab/branch/main/graph/badge.svg" alt="codecov"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

编写您的视觉规则。生成图像。根据这些规则评估每张图像。将结果作为版本控制的、可追溯的训练数据发布，然后将训练好的模型应用于实际的生产流程，并将最佳输出反馈回您的数据集。

Style Dataset Lab 将您关于艺术风格的描述与实际用于训练的数据集联系起来。您定义一套规范，包括轮廓规则、调色板限制、材质语言，以及对您的项目而言重要的任何内容。流水线生成候选作品，根据这些规则对其进行评分，并将通过的成果打包成可重复的数据集，其中每个记录都解释了它被包含的原因。

然后，生产工作台接管：从项目基础信息中提取生成指令，通过 ComfyUI 运行这些指令，评估输出结果，批量生成表情图和环境板，选择最佳结果，并将它们作为新的候选对象重新导入。循环完成：生成、选择、审查、改进。

## 流水线

```bash
# Write your canon. Scaffold the project.
sdlab init my-project --domain character-design

# Generate candidates via ComfyUI, then review them
sdlab generate inputs/prompts/wave1.json --project my-project
sdlab curate <id> approved "Strong silhouette, correct faction palette"

# Bind approved work to constitution rules
# (`sdlab bind` is a shorter alias for `canon-bind`)
sdlab canon-bind --project my-project

# Freeze a versioned dataset
sdlab snapshot create --project my-project
sdlab split build
sdlab export build

# Build a training package
sdlab training-manifest create --profile character-style-lora
sdlab training-package build

# Compile a production brief and run it
sdlab brief compile --workflow character-portrait-set --subject kael_maren
sdlab run generate --brief brief_2026-04-16_001

# Critique, refine, batch-produce
sdlab critique --run run_2026-04-16_001
sdlab refine --run run_2026-04-16_001 --pick 001.png
sdlab batch generate --mode expression-sheet --subject kael_maren

# Select the best outputs and bring them back
sdlab select --run run_2026-04-16_001 --approve 001.png,003.png
sdlab reingest selected --selection selection_2026-04-16_001
```

这个最后的命令至关重要。选定的输出会经过与所有其他内容相同的审查流程。数据集不断增长，规则始终有效。

## 它产生的内容

包含七个数据集文件和一套完整的生产工作台。每个文件都链接到其前驱文件，因此您可以追溯任何训练记录，直到找到最初批准它的规则。

| 成果 | 它的定义 |
|----------|-----------|
| **Snapshot** | 带有配置指纹的冻结记录选择。每个包含项都有明确的理由。 |
| **Split** | 训练/验证/测试数据集，其中主题类别之间绝不交叉。 |
| **Export package** | 自包含的数据集：清单、元数据、图像、数据集划分、数据集描述、校验和。 |
| **Eval pack** | 与规范相关的测试任务：覆盖范围、避免偏差、锚定/黄金标准、主题连续性。 |
| **Training package** | 通过适配器（`diffusers-lora`、`generic-image-caption`）提供可供训练器使用的布局。相同的真理，不同的格式。 |
| **Eval scorecard** | 每个任务的通过/失败结果，基于生成的输出与评估包的比较。 |
| **Implementation pack** | 提示示例、已知的失败案例、连续性测试以及重新导入指南。 |

生产工作台包含以下功能：

| 表面功能 | 功能描述 |
|---------|-------------|
| **Compiled brief** | 从工作流程配置文件和项目基础信息中获取确定性的生成指令。 |
| **Run** | 冻结的执行文件：包含指令、种子、ComfyUI 输出和清单。 |
| **Critique** | 对生成结果进行结构化的多维度评估，与标准进行比较。 |
| **Batch** | 协调的多通道生产（表情图、环境板、人物轮廓图）。 |
| **Selection** | 创意决策文件：记录选择了哪些输出，原因以及它们的来源。 |
| **Re-ingest** | 选定的输出作为包含完整生成信息的候选记录返回。 |

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
  workflows/             Workflow profiles + batch mode definitions
  briefs/                Compiled generation briefs
  runs/                  Execution artifacts (brief + outputs + manifest)
  batches/               Coordinated multi-slot productions
  selections/            Chosen outputs with reasons and provenance
  inbox/generated/       Re-ingested images awaiting review
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

### 尝试不使用 ComfyUI

您可以使用捆绑的 Star Freight 项目，探索完整的非生成功能，例如检查、整理、快照、分割和导出，而无需安装 ComfyUI 或下载任何 SDXL 模型文件。

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor` 命令可以验证每个项目的配置（宪法、流程、评分标准、术语），并在不访问 GPU 的情况下报告资格。任何会修改生成状态的命令都支持 `--dry-run` 参数，以便在执行前预览效果。

如果您忘记了 `--project` 参数，CLI 会自动选择 `projects/` 目录下找到的第一个项目，并打印一条警告。要强制指定项目，请明确使用 `--project` 参数。

### 恢复中断的运行

可以恢复长时间的生成运行，而无需重新执行已完成的工作：

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

这两个命令都有效，因为每个通道在完成时都会原子性地写入其清单条目，即使在运行过程中崩溃，也不会损坏部分状态。

## 故障排除

常见的错误模式和解决方法：

**`ECONNREFUSED 127.0.0.1:8188` 错误，出现在任何 `sdlab generate` / `sdlab run generate` / `sdlab batch generate` 命令中**
ComfyUI 未运行。启动 ComfyUI (`python main.py --listen 127.0.0.1 --port 8188`)，并使用 `curl http://127.0.0.1:8188/system_stats` 确认其是否正在运行。要指定不同的主机/端口，请设置 `COMFY_URL=http://host:port`。

**`missing checkpoint` / `LoRA weight not found` 错误**
您的工作流程配置文件中指定了 ComfyUI 的 `models/checkpoints/` 或 `models/loras/` 文件夹中不存在的模型文件。打开 `projects/<project>/workflows/profiles/<profile>.json`，找到 `checkpoint` 或 `lora` 字段，然后要么下载指定的模型文件，要么将其替换为您已有的模型文件。重新运行 `sdlab project doctor --project <project>` 以确认修复。

**`sdlab project doctor` 错误**
Doctor 返回结构化的错误代码。常见的错误代码包括：
- `E_PROJECT_NOT_FOUND`：项目目录不存在于 `projects/` 目录下。检查拼写。
- `E_CONFIG_INVALID`：五个 JSON 配置文件之一未能通过模式验证。`hint` 字段会指出哪个文件和字段存在问题。
- `E_RECORD_DRIFT`：记录的配置指纹与其来源不再匹配。根据提示进行重新整理或重新绑定。

**`未指定 --project，将使用 <name> 作为默认项目`**
这是一个提示信息。为了选择正确的项目并消除此提示，请明确使用 `--project <name>` 参数。

**绘画风格 / 显存不足问题**
请参考 `docs/internal/HANDOFF.md` 中的关于绘画风格降噪的调整说明。 简而言之：降低降噪强度，减少批次大小，或者在工作流程配置文件中切换到较小的模型文件。

**报告错误**
请在 https://github.com/mcp-tool-shop-org/style-dataset-lab/issues 上提交问题，并提供您的 sdlab 版本（`sdlab --version`）、Node 版本（`node -v`）、完整的命令以及结构化的错误输出。 错误报告模板会预先填充字段。

## 安全性

仅在本地运行。没有遥测数据，没有分析，没有外部请求。图像保留在您的 GPU 和文件系统中。

## 许可证

MIT 许可证

---

由 <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a> 构建。
