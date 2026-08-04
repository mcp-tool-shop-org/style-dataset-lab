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

编写你的视觉规则。生成艺术作品。根据这些规则评估每张图像。将结果作为版本化的、可审计的训练数据进行交付——然后将训练好的模型应用于实际的生产流程中，并将最佳输出反馈到你的语料库中。

“风格数据集实验室”将你记录下来的关于艺术风格的内容与你实际用于训练的数据集联系起来，然后贯穿整个生产过程，形成一个闭环。你可以定义一套规范——轮廓规则、调色板约束、材质语言，或者对你的项目有意义的任何内容。流水线会生成候选作品，根据这些规则对其进行评分，并将批准的作品打包成可重现的数据集，其中每条记录都解释了它被包含的原因。

然后，生产工作台接管：从项目的真实数据中编译生成简报，通过 ComfyUI 运行它们，评估输出结果，批量生成表现图和环境板，选择最佳结果，并将这些结果作为新的候选作品重新导入。循环完成：生成、选择、审查、改进。

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

最后一条命令就是关键。选定的输出会通过与所有其他内容相同的审核流程进行评估。语料库不断增长，规则始终有效。

## 规范创作

Before the dataset pipeline runs, the `sdlab canon *` namespace turns your project's canon entity store into the three projections training and production actually consume — and locks the entries that must not drift.

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

`canon build` 是基于内容的——它的输出由一个 `canon_sha` 确定，并进行缓存，因此未更改的规范可以立即重建。`canon freeze` 会针对特定的构建记录每次冻结状态，并将结果附加到 `freeze-events.jsonl` 审计跟踪中：`frozen` 条目会直接拒绝重新生成，`soft-advisory` 条目默认情况下会拒绝（通过 `--i-know` 可以绕过）。`canon drift` 会重新计算每个已监视条目的哈希值，并标记自上次完整构建以来发生更改的任何内容。

完整的流程在手册中：[构建规范](handbook/canon-build/)、[冻结规范](handbook/canon-freeze/)和[双 LoRA 堆叠](handbook/two-lora-stacking/)。

## 它产生的结果

七个数据集工件和一个完整的生产工作台。每个工件都链接到其前身，因此你可以追溯任何训练记录到批准它的规则。

| 工件 | 它是什么 |
|----------|-----------|
| **Snapshot** | 带有配置指纹的冻结记录选择。每个包含项都有明确的原因。 |
| **Split** | 训练/验证/测试分区，其中主题系列不会跨越边界。 |
| **Export package** | 自包含数据集：清单、元数据、图像、分割、数据集卡、校验和。 |
| **Eval pack** | 考虑规范的测试任务：车道覆盖率、禁止漂移、锚点/黄金标准、主题连续性。 |
| **Training package** | 通过适配器实现训练器友好的布局（`diffusers-lora`、`generic-image-caption`）。相同的真相，不同的格式。 |
| **Eval scorecard** | 根据评估包对生成的输出进行评分后的每个任务的通过/失败结果。 |
| **Implementation pack** | 提示示例、已知错误、连续性测试和重新导入指南。 |

生产工作台添加的内容：

| 表面 | 它做什么 |
|---------|-------------|
| **Compiled brief** | 来自工作流程配置文件 + 项目真实数据的确定性生成指令。 |
| **Run** | 冻结的执行工件：简报 + 种子 + ComfyUI 输出 + 清单。 |
| **Critique** | 对运行输出相对于规范进行结构化的多维评估。 |
| **Batch** | 协调的多插槽生产（表现图、环境板、轮廓包）。 |
| **Selection** | 创意决策工件：选择了哪些输出，原因是什么，以及它们来自哪里。 |
| **Re-ingest** | 选定的输出作为带有完整生成来源的候选记录返回。 |

## 为什么这个系统存在

训练数据是任何视觉 AI 流水线中最重要的工件。但是，大多数训练数据只是一个包含图像的文件夹，没有历史记录、没有判断轨迹，也没有与它应该遵循的风格规则的联系。

“风格数据集实验室”使这种联系变得明确。你的规范定义了规则。你的评分标准定义了评分维度。你的策划记录了判断结果。你的规范绑定证明了这种联系。并且你的数据集将所有这些内容作为结构化、可查询、可重现的真实数据进行传递。

实际效果：当你的 LoRA 发生漂移时，你可以询问*原因*。当你的下一个训练轮次需要更好的数据时，你确切地知道哪些记录是接近成功的，以及它们未能满足哪个单一规则。当新的团队成员询问项目的视觉语言是什么时，答案不是 Figma 板——而是一个可搜索的规范，其中包含 1,182 个分级的示例。

## 在生产中得到验证

这不是一个演示流水线。两个真实的风格 LoRA 都通过它完成了端到端的流程——相同的规范 → 策划 → 训练 → 发布循环，位于策划频谱的两端。

- **[Tallow Fen](handbook/case-study-tallow-fen/)**（生物设计）——一个从头开始构建的生物图鉴规范，在 293 个精选记录中获得约 **34% 的认可度**（169 个被拒绝——审核非常严格）。以 `tallow_fen_style_v3.safetensors` @ 1.5 的形式发布到 `qwen-image`。
- **[Rustline](handbook/case-study-rustline/)**（概念设计）——一个密集、预先构建的规范，在 180 个记录中获得约 **96% 的认可度**。以 `rustline_v3ckpt_1500.safetensors` @ 1.0 的形式发布到 `qwen-image`，并在第二个项目中重复使用。

相同的流水线，两种生产配置：策划审核是真实的（它会严格拒绝开放主题），并且严谨的规范可以产生很高的接受率。

## 五个领域，真实的规则

不是占位符模板。每个领域都提供生产级别的规范规则、车道定义、评分标准和组词汇表。

| 领域 | 通道 | 评估标准 |
|--------|-------|-----------------|
| **game-art** | 角色、环境、道具、用户界面、飞船、内部场景、设备 | 游戏中的轮廓、阵营特征、磨损和老化效果 |
| **character-design** | 肖像、全身图、旋转图、表情表、动作姿势 | 比例、服装逻辑、个性、手势清晰度 |
| **creature-design** | 概念图、正投影图、细节研究、动态效果、比例参考、栖息地 | 解剖结构、进化逻辑、轮廓区分 |
| **architecture** | 外部、内部、街景、结构细节、废墟、景观 | 结构、材质一致性、透视、时代背景的一致性 |
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

这些不是理想化的，而是强制执行的。

- **快照是不可变的。** 配置指纹（SHA-256）证明没有任何更改。ID 是原子性地声明的，因此两个并发运行不能相互交错到一个目录中。
- **分割可以防止泄漏——并且验证这一点的代码是独立的。** 主题系列（按身份、血统或规范化的 ID 词干）永远不会跨越分区边界，并且第二个检查会从头开始重新推导主题身份，而不是重新读取分割本身使用的映射。数据集卡仅在两个检查都运行并通过时声明“泄漏：无（已验证）”；如果分割早于第二次检查，则会明确说明这一点。
- **清单是冻结的协议。** 导出哈希 + 配置指纹，并且 `validate` 会重新计算 `checksums.txt` 列出的每个文件——因此，替换完成导出中的图像会被捕获，包括对于在进行此检查之前创建的清单。
- **运行会固定其确切的图。** 每个生成都会记录 `comfy_workflow_sha` + 模型/LoRA 内容哈希 + 种子策略，因此可以逐字节地重现一个批次。JS 和 Python 运行器通过一个测试来确保它们具有完全相同的哈希值，该测试会同时启动两者。模型哈希是可选的（`--hash-models`），并且绝不会伪造——如果无法解析某个文件，则会记录 `sha256: null` 并附带说明。
- **没有模型会验证自己的输出。** 判断会记录 `judged_by_model` 和 `generator_model`；如果它们曾经是同一个模型，则会发出警告。
- **判断会说明是谁做出的判断。** `eligibility audit` 会区分某人编写的判断和批量脚本生成的判断，因此描述一个类别而不是图像的理由不能被视为审核。
- **测量不是结论。** `sdlab measure` 将数字附加到记录中。它绝不会设置判断、拟合或认可——并且如果某个图像没有定义度量值，则会记录 `null` 而不是一个合理的数字。
- **适配器无法更改真相。** 不同的布局，相同的记录。没有添加、删除或重新分类。
- **生成的输出会通过审核重新进入。** 没有绕过。像其他内容一样进行审核和绑定。外部生成的图像以相同的方式通过 `sdlab ingest` 进入，未经审核。
- **失败是可见的。** 缺少记录、无法放置的图像或无法构建的标题会导致导出或训练包停止，而不是悄悄地缩小它。

## 星际货运

该仓库包含一个完整的可运行示例：1,182 条记录、5 个阵营、7 个通道、24 条宪法规则、892 个已批准的资源、2 个训练配置文件。这是一个粗犷的科幻 RPG 视觉规范，经过完全策划。

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

需要 Node.js 20+ 和本地主机上的 [ComfyUI](https://github.com/comfyanonymous/ComfyUI)，地址为 8188，用于生成。

### 在不使用 ComfyUI 的情况下试用

您可以探索完整的非生成界面——检查、策划、快照、分割、导出——使用捆绑的星际货运项目，而无需安装 ComfyUI 或下载任何 SDXL 权重。

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor` validates every project config (constitution, lanes, rubric, terminology) and reports eligibility without touching the GPU. Any command that mutates generated state accepts `--dry-run` to preview the effect first.

如果您忘记了 `--project`，CLI 将回退到在 `projects/` 下找到的第一个项目并打印警告——明确传递 `--project` 以使其停止发出警告。

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

这两个命令都有效，因为每个插槽都会在其完成后以原子方式写入其清单条目——在运行过程中发生崩溃绝不会破坏部分状态。

## 故障排除

常见的失败模式和解决方法：

**`ECONNREFUSED 127.0.0.1:8188` 在任何 `sdlab generate` / `sdlab run generate` / `sdlab batch generate` 上**
ComfyUI 没有运行。启动 ComfyUI（`python main.py --listen 127.0.0.1 --port 8188`）并通过 `curl http://127.0.0.1:8188/system_stats` 进行确认。要指向不同的主机/端口，请设置 `COMFY_URL=http://host:port`。

**`missing checkpoint` / `LoRA weight not found`**
您的工作流程配置文件指定了一个不在 ComfyUI 的 `models/checkpoints/` 或 `models/loras/` 文件夹中的模型文件。打开 `projects/<project>/workflows/profiles/<profile>.json`，找到 `checkpoint` 或 `lora` 字段，然后下载引用的权重或将其替换为您已经拥有的权重。重新运行 `sdlab project doctor --project <project>` 以确认修复。

**`sdlab project doctor` 错误**
Doctor 返回结构化的错误代码。常见的错误：
- `E_PROJECT_NOT_FOUND`——项目目录不存在于 `projects/` 下。检查拼写。
- `E_CONFIG_INVALID`——五个 JSON 配置文件中的一个未能通过模式验证。`hint` 字段指定了错误的 文件和字段。
- `E_RECORD_DRIFT`——某个记录的配置指纹不再与其来源匹配。如提示所述，重新审核或重新绑定。

**`No --project specified, falling back to <name>`**
一个软警告。明确传递 `--project <name>` 以选择正确的项目并停止发出警告。

**Painterly / VRAM out-of-memory issues**
See `docs/internal/HANDOFF.md` for the painterly denoise tuning notes. In short: lower the denoise strength, reduce batch size, or switch to a smaller checkpoint in your workflow profile.

**Reporting bugs**
File an issue at https://github.com/mcp-tool-shop-org/style-dataset-lab/issues with your sdlab version (`sdlab --version`), Node version (`node -v`), the full command, and the structured error output. A bug-report template prefills the fields.

## 安全性

仅限本地使用。没有遥测、分析或外部请求。图像保留在您的 GPU 和文件系统中。

## 许可协议

MIT

---

由 <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a> 构建。
