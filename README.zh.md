<p align="center">
  <a href="README.md">English</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
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

编写你的视觉规则。生成艺术作品。根据这些规则评估每张图像。将结果作为版本化的、可审计的训练数据进行输出——然后将训练好的模型应用于实际的生产工作流程中，并将最佳输出反馈到你的语料库中。

“风格数据集实验室”将你记录的关于你的艺术风格的内容与你实际用于训练的数据集联系起来，然后将整个流程贯穿到生产阶段。你定义一套规范——轮廓规则、调色板约束、材质语言，以及对你的项目有意义的任何内容。流水线生成候选作品，根据这些规则对其进行评分，并将批准的作品打包成可重现的数据集，其中每条记录都解释了它被包含的原因。

然后，生产工作台接管：从项目的事实中编译生成简报，通过 ComfyUI 运行，评估输出结果，批量生成表现图和环境图，选择最佳结果，并将它们重新导入作为新的候选作品。循环结束：生成、选择、审查、改进。

## 流水线

```bash
# Write your canon. Scaffold the project.
sdlab init my-project --domain character-design

# Generate candidates via ComfyUI, then review them
sdlab generate inputs/prompts/wave1.json --project my-project
sdlab sheet outputs/candidates --project my-project   # HTML contact sheet to triage
sdlab curate <id> approved "Strong silhouette, correct faction palette"

# Already have images? Bring them in without generating anything
sdlab ingest ~/renders/wave1 --project my-project

# Measure what the pixels actually are — palette and texture, as numbers
sdlab measure outputs/candidates --project my-project

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

最后一条命令就是关键。选定的输出会通过与所有其他内容相同的审查流程。语料库不断增长，规则始终有效。

## 资产通道——3D 导出作为训练数据

`sdlab ingest` 信任原始图像。`sdlab asset ingest` 签订一份**协议**。

当一个 3D 资产通过其验收关口后，从 N 个角度重新渲染它，可以得到一个视角一致的图像——这是通过构建方式实现的，而基于视角的扩散模型无法保证这一点。资产通道将这些导出作为带有来源信息的训练数据：

```bash
# Validate an export's manifest end to end, run the gates, write nothing
sdlab asset ingest ~/exports/dragon_dense --project my-project --dry-run

# Register it: records, candidates, masks, channels, receipt
sdlab asset ingest ~/exports/dragon_dense --project my-project
```

导出目录包含一个 `asset-source.json` 清单（模式 **1.3.0**），声明了其通道、调色板频段、关口阈值、验收结果、风格注册表，以及渲染图像的生成方式和来源。sdlab 会根据实际字节验证每个声明，并且如果发现任何违规行为，将拒绝整个导入——任何不符合规范的清单都不会被注册。

**连接点：** sdlab 提供机制，资产提供语义。sdlab 从不进行光线追踪，从不进行渲染，并且从不认为名为“来源”的通道是特殊的。它会证明、测量、注册和打包。数字的*含义*与资产相关联。

协议强制执行的内容：

| 阶段 | 验证的内容 |
|---|---|
| **schema** | 形状、ID、格式良好的调色板频段，以及实际上为 `"accepted"` 的验收结果 |
| **containment** | 每个引用的路径都*位于*导出目录中（它是不受信任的输入），并且存在 |
| **encoding** | PNG 的 IHDR 与其声明的编码匹配；NPY 标头的 dtype 和形状与其声明的 dtype 和形状匹配。如果清单“看起来正确”，但与它的字节不一致，那么这就是本通道旨在阻止的情况。 |
| **categorical** | 索引 PNG 证明 PLTE ⊆ 声明的调色板；使用 `nearest` 过滤的通道会进行*详尽的*像素解码；分类 NPY 会进行详尽的值扫描。 |
| **gates** | 调色板关口在每次渲染时运行，基于清单自身的频段和阈值——如果渲染失败，则会发出明确的拒绝并报告，而不会悄悄地接受。 |

记录以**未整理**（`judgment: null`）的形式与 `provenance.source: "asset"` 一起导入，并携带
验收块的完整内容、每个文件的哈希值、相机和导向信息、关口测量值、声明的风格注册表以及每个图像的生成帧和种子。然后，它们会经历与其他记录相同的整理过程。

导入还会报告清单*未*声明的内容——未知的风格注册表、缺失的 `identity.subject_name`、缺失的生成来源——作为**通知**，而不是
失败。它们会显示在收据中并在 CLI 中打印。如果有一个问题没有人被告知，那么就无法解决这个问题；并且，由于清单可以*声明*其渲染是确定性的派生，并且没有自己的种子，因此该通道不会报告任何导出的差距。

完整的协议、验证层级以及每个字段背后的原因：[docs/asset-lane-design.md](docs/asset-lane-design.md)。

## 规范创作

在数据集流水线运行之前，`sdlab canon *` 命名空间将你的项目的规范实体存储转换为训练和生产实际使用的三个投影——并锁定那些不应漂移的条目。

```bash
# Build three projections from the canon entity store:
#   dataset.jsonl  → training adapters
#   prompts/*.j2   → ComfyUI workflow invocation
#   context/*.md   → Role OS narrative dispatch
sdlab canon build --project my-project

# Freeze an entry so regeneration can't silently change it
sdlab canon freeze kael_maren --project my-project --reason "prologue portrait locked"

# Report drift on frozen entries since the last clean build
sdlab canon drift --project my-project
```

本地模型也可以草拟规范，但它不能决定规范。`sdlab canon draft <class_id> --endpoint <url> --brief "<text>" --out <path>` 向仅循环的、与 OpenAI 兼容的服务器请求规范条目和提示，并使用 `status: "draft"`、`judgment: null` 和草拟模型对每个输出进行标记。在有人批准之前，草拟内容不能被冻结：冻结关口拒绝任何由模型草拟的条目，除非有人的批准、理由以及批准的确切草拟的哈希值。

`canon build` 是基于内容的——它的输出由 `canon_sha` 键控并缓存，因此未更改的规范可以立即重建。`canon freeze` 见证每次冻结，并附加到 `freeze-events.jsonl` 审计跟踪中：`frozen` 条目完全拒绝重新生成，`soft-advisory` 条目默认拒绝（使用 `--i-know` 绕过）。`canon drift` 重新计算每个已监视条目的哈希值，并标记自上次干净构建以来发生更改的任何内容。

完整的流程在手册中：[规范构建](handbook/canon-build/)、[规范冻结](handbook/canon-freeze/) 和 [双 LoRA 堆叠](handbook/two-lora-stacking/)。

## 它产生的内容

七个数据集工件和一个完整的生产工作台。每个工件都链接到其前身，因此你可以追溯任何训练记录到批准它的规则。

| 工件 | 它是什么 |
|----------|-----------|
| **Snapshot** | 带有配置指纹的冻结记录选择。每个包含都有明确的理由。 |
| **Split** | 训练/验证/测试分区，其中主题系列不会跨越边界。 |
| **Export package** | 自包含数据集：清单、元数据、图像、分割、数据集卡、校验和。 |
| **Eval pack** | 了解规范的测试任务：车道覆盖、禁止漂移、锚点/黄金样本、主题连续性。 |
| **Training package** | 通过适配器（`diffusers-lora`、`generic-image-caption`）构建可用于训练的布局。相同的真实数据，不同的格式。 |
| **Eval scorecard** | 根据评估包对生成的输出进行评分，从而得出每个任务的通过/失败结果。 |
| **Implementation pack** | 提示示例、已知失败案例、连续性测试和重新导入指南。 |

生产工作台新增：

| 表面 | 其作用 |
|---------|-------------|
| **Compiled brief** | 从工作流程配置文件 + 项目真实数据中生成确定性的生成指令。 |
| **Run** | 冻结的执行工件：简要说明 + 种子 + ComfyUI 输出 + 清单。 |
| **Critique** | 对运行输出相对于规范进行结构化的多维评估。 |
| **Batch** | 协调多插槽生产（表情表、环境板、轮廓包）。 |
| **Selection** | 创意决策工件：选择了哪些输出，原因是什么，以及它们的来源。 |
| **Re-ingest** | 选定的输出作为包含完整生成来源的候选记录返回。 |

## 为什么存在这个系统

在任何视觉 AI 流水线中，训练数据是最有价值的资源。但大多数训练数据只是一个包含图像的文件夹，没有历史记录、没有判断依据，也没有与它应该遵循的风格规则的联系。

“风格数据集实验室”使这种联系变得明确。您的规范定义了规则。您的评分标准定义了评分维度。您的整理记录了判断过程。您的规范绑定证明了这种联系。并且您的数据集将所有这些内容作为结构化、可查询、可重现的真实数据进行保留。

实际结果：当您的 LoRA 发生漂移时，您可以询问*原因*。当您的下一个训练需要更好的数据时，您会确切地知道哪些记录接近失败，以及它们未能满足的单一规则。当新的团队成员询问项目的视觉语言时，答案不是一个 Figma 板——而是一个可搜索的规范，其中包含 1182 个分级示例。

## 已在生产中验证

这不是一个演示流水线。两个真实的风格 LoRA 已经通过它完成了端到端的流程——相同的规范 → 整理 → 训练 → 发布循环，位于整理频谱的相对两端。

- **[Tallow Fen](handbook/case-study-tallow-fen/)**（生物设计）——一个从零开始构建的生物图鉴规范，在 293 个整理的记录中，约有 **34% 的批准率**（169 个被拒绝——筛选非常严格）。发布 `tallow_fen_style_v3.safetensors`，参数为 1.5，在 `qwen-image` 上运行。
- **[Rustline](handbook/case-study-rustline/)**（概念设计）——密集、预先构建的规范，在 180 个记录中，约有 **96% 的批准率**。发布 `rustline_v3ckpt_1500.safetensors`，参数为 1.0，在 `qwen-image` 上运行，并在后续项目中被第二个项目重用。

相同的流水线，两种生产配置文件：整理筛选是真实的（它会严格拒绝开放主题），并且严格的规范会产生很高的接受率。

## 五个领域，真实的规则

不是占位符模板。每个领域都提供生产级别的规范规则、车道定义、评分标准和组词汇。

| 领域 | 车道 | 需要判断的内容 |
|--------|-------|-----------------|
| **game-art** | 角色、环境、道具、UI、飞船、内部、设备 | 在游戏规模下，轮廓、派系特征、磨损和老化 |
| **character-design** | 肖像、全身、旋转图、表情表、动作姿势 | 比例、服装逻辑、个性、姿势清晰度 |
| **creature-design** | 概念、正投影、细节研究、动作、比例参考、栖息地 | 解剖结构、进化逻辑、轮廓区分 |
| **architecture** | 外部、内部、街景、结构细节、废墟、景观 | 结构、材料一致性、透视、时代一致性 |
| **vehicle-mech** | 外部、驾驶舱、组件、示意图、轮廓图、损坏变体 | 机械逻辑、设计语言、访问点、损坏叙事 |

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

这些不是理想化的。它们是强制执行的。

- **快照是不可变的。** 配置指纹（SHA-256）证明没有发生任何更改。ID 以原子方式声明，因此两个并发运行不能交错到同一个目录中。
- **分割可以防止数据泄露——并且验证这一点的是一个独立的检查。** 主题族（按身份、谱系或规范化的 ID 词干）绝不会跨越分区边界，并且第二个检查会从头开始重新推导主题身份，而不是重新读取分割本身使用的映射。数据集卡仅在两个检查都运行并通过时声明“数据泄露：无（已验证）”；如果分割早于第二个检查，则会明确说明这一点。
- **清单是固定的协议。** 导出哈希 + 配置指纹，并且 `validate` 会重新哈希 `checksums.txt` 列出的每个文件——因此，替换已完成导出中的图像会被捕获，包括在创建清单之前进行的检查。
- **每次运行都会固定其确切的图。** 每次生成都会记录 `comfy_workflow_sha` + 模型/LoRA 内容哈希 + 种子策略，因此可以完全重现一次生成。JS 和 Python 运行器通过一个测试来确保字节级的哈希值完全相同，该测试会同时启动两者。模型哈希是可选的（`--hash-models`），并且绝不会伪造——无法解析的文件会记录 `sha256: null` 并附带说明。
- **没有模型会验证自己的输出。** 判决会记录 `judged_by_model` 和 `generator_model`；如果它们曾经是同一个模型，则会发出警告。
- **判决会说明是谁做出的。** `eligibility audit` 区分了某人编写的判决和批量脚本生成的判决，因此，描述的是一个类别而不是一个图像的理由，不能被视为策展。
- **测量不是判决。** `sdlab measure` 将数字附加到记录中。它绝不会设置判决、拟合或批准——并且对于图像而言，如果某个指标未定义，它会记录 `null` 而不是一个合理的数字。
- **发布可以证明每张图像的来源。** `sdlab verify --project <name>` 会为每条记录遍历链条：记录上的所有者和许可，它所绑定的规范条目（通过哈希），每个模型和 LoRA 的许可（SPDX ID、许可 URL、读取日期和文件哈希），以及运行清单中的工作流哈希。如果缺少链接，则检查会失败，而不是通过。
- **适配器不能改变真相。** 不同的布局，相同的记录。没有添加、没有删除、没有重新分类。
- **生成的输出会通过审核重新进入。** 没有绕过。像其他内容一样进行策展和绑定。外部生成的图像通过 `sdlab ingest` 以相同的方式进入，未经策展。
- **失败是可见的。** 缺少记录、无法放置的图像或无法构建的标题会停止导出或训练包，而不是悄悄地缩小它。

## 星际货运

该存储库包含一个完整的可用示例：1182 条记录、5 个派系、7 条路线、24 条宪法规则、892 个已批准的资产、2 个训练配置文件。一个粗犷的科幻 RPG 视觉规范，已完全策展。

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## 下游格式

`sdlab` 拥有数据集。格式转换由 [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) 处理：TRL、LLaVA、Qwen2-VL、JSONL、Parquet 等。`repo-dataset` 进行渲染；它绝不会决定是否包含。

## 安装

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

需要 Node.js 20+ 和本地主机 8188 上的 [ComfyUI](https://github.com/comfyanonymous/ComfyUI) 进行生成。

### 尝试不使用 ComfyUI

您可以使用捆绑的星际货运项目探索完整的非生成表面——检查、策展、快照、分割、导出——而无需安装 ComfyUI 或下载任何 SDXL 权重。

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor` 验证每个项目配置（宪法、路线、评分标准、术语），并在不触及 GPU 的情况下报告资格。任何更改生成状态的命令都接受 `--dry-run` 以首先预览效果。

如果您忘记了 `--project`，CLI 将回退到 `projects/` 下找到的第一个项目，并打印警告——明确传递 `--project` 以使其停止。

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

这两个命令都有效，因为每个插槽都会在其完成时以原子方式写入其清单条目——运行过程中发生崩溃绝不会破坏部分状态。

## 故障排除

常见故障模式和解决方法：

**`ECONNREFUSED 127.0.0.1:8188` 在任何 `sdlab generate` / `sdlab run generate` / `sdlab batch generate` 上**
ComfyUI 尚未运行。启动 ComfyUI（`python main.py --listen 127.0.0.1 --port 8188`），并使用 `curl http://127.0.0.1:8188/system_stats` 进行确认。要指向不同的主机/端口，请设置 `COMFY_URL=http://host:port`。

**`missing checkpoint` / `LoRA weight not found`**
您的工作流配置文件指定了一个不在 ComfyUI 的 `models/checkpoints/` 或 `models/loras/` 文件夹中的模型文件。打开 `projects/<project>/workflows/profiles/<profile>.json`，找到 `checkpoint` 或 `lora` 字段，然后下载引用的权重或将其替换为您已有的权重。重新运行 `sdlab project doctor --project <project>` 以确认修复。

**`sdlab project doctor` 错误**
Doctor 返回结构化的错误代码。常见错误：
- `E_PROJECT_NOT_FOUND`——项目目录不存在于 `projects/` 下。检查拼写。
- `E_CONFIG_INVALID`——五个 JSON 配置文件中的一个未能通过模式验证。`hint` 字段指定了错误的 文件和字段。
- `E_RECORD_DRIFT`——记录的配置指纹不再与其来源匹配。如提示所述，重新策展或重新绑定。

**`No --project specified, falling back to <name>`**
一个软警告。明确传递 `--project <name>` 以选择正确的项目并停止警告。

**绘画风格 / VRAM 内存不足问题**
请参阅 `docs/internal/HANDOFF.md` 以获取绘画风格去噪调整说明。简而言之：降低去噪强度、减少批处理大小或在工作流配置文件中切换到较小的检查点。

**报告错误**
在 https://github.com/mcp-tool-shop-org/style-dataset-lab/issues 上提交问题，并提供您的 sdlab 版本（`sdlab --version`）、Node 版本（`node -v`）、完整的命令以及结构化的错误输出。错误报告模板会预填充字段。

## 安全性

默认情况下为本地。没有遥测、没有分析，并且 `sdlab` CLI 不会进行任何外部请求：图像保留在您的 GPU 和文件系统中，并且 `canon draft` 拒绝任何非环回的端点。

唯一的例外是“选择加入”功能。`scripts/colab/` 包含用于在您自己的 Google Colab 帐户上运行渲染或 LoRA 训练步骤的启动工具包。它们只会上传您指定的文件，并在不超过从您的 Colab 帐户余额中读取的预算限制的情况下运行，并在退出时停止自身的会话。这些工具包是**实验性的**：它们尚未完成完整的端到端测试。

## 许可

MIT

---

由 <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a> 构建
