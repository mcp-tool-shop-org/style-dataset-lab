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

将已批准的视觉素材转化为版本控制、经过审核的数据集、分片、导出包和评估包。

## 这是什么

一个用于视觉数据规范和数据集生成的**流水线**。明确您的项目外观。根据既定规则进行筛选。生成可重复的数据集包，并确保数据分割的安全性。生成评估数据集，用于未来模型的验证。

流水线会生成四个产出物：

| 文物。 | 它是什么。 |
|----------|-----------|
| **Snapshot** | 经过筛选，符合条件的记录已冻结，并进行了指纹识别。所有被选入的记录都有明确的纳入理由。 |
| **Split** | 安全的训练/验证/测试数据集划分，防止数据泄露。共享相同主题的数据记录始终会被划分到同一个子集。 |
| **Export package** | 自包含的数据集：包含清单、元数据、图像、数据集划分、数据集描述文档以及校验和。 |
| **Eval pack** | 符合佳能标准的验证任务包括：车道覆盖、禁止漂移、锚点/黄金区域、主体连续性。 |

流水线中的每个资产都包含以下三个要素：

1. **来源信息** -- 完整的生成历史记录（检查点、LoRA、种子、采样器、配置参数、生成时间）。
2. **合规性** -- 指示该资产是否符合相关规定，以及是否完全符合、不符合或部分符合。
3. **质量评估** -- 采用每维度的评分标准，对质量进行评估，结果分为：通过/未通过/临界。

主要从事游戏美术、角色设计、生物设计、建筑设计、车辆/机械概念设计等工作，以及任何需要保持视觉风格一致性的领域。

## 快速入门

```bash
# Install the CLI + pipeline
npm install -g @mcptoolshop/style-dataset-lab

# Scaffold a new project
sdlab init my-project --domain character-design

# Validate the project structure
sdlab project doctor --project my-project
```

可用的领域包括：`game-art`（游戏美术）、`character-design`（角色设计）、`creature-design`（生物设计）、`architecture`（架构）、`vehicle-mech`（车辆机械设计）或`generic`（通用）。

## 命令行界面

```bash
sdlab init <name> [--domain <domain>]     # Scaffold a new project
sdlab project doctor [--project <name>]   # Validate project config

sdlab generate <pack> [--project <name>]  # Generate candidates via ComfyUI
sdlab generate:identity <packet>          # Named-subject identity images
sdlab generate:controlnet                 # ControlNet-guided generation
sdlab generate:ipadapter                  # IP-Adapter reference-guided

sdlab curate <id> <status> <explanation>  # Record review judgment
sdlab compare <a> <b> <winner> <reason>   # Pairwise A-vs-B comparison
sdlab bind [--project <name>]             # Bind records to constitution rules
sdlab painterly [--project <name>]        # Post-processing style pass

sdlab snapshot create [--profile <name>]  # Create frozen dataset snapshot
sdlab snapshot list                       # List all snapshots
sdlab snapshot diff <a> <b>               # Compare two snapshots
sdlab eligibility audit                   # Audit record training eligibility
sdlab split build [--snapshot <id>]       # Build train/val/test split
sdlab split audit <id>                    # Audit split for leakage + balance
sdlab card generate                       # Generate dataset card (md + JSON)
sdlab export build [--snapshot <id>]      # Build versioned export package
sdlab eval-pack build                     # Build canon-aware eval pack
```

所有命令都支持 `--project <名称>` 参数，默认值为 `star-freight`。

## 项目模型

每个项目都位于 `projects/` 目录下，作为一个独立的目录，拥有自己的规范、配置文件和数据。

```
projects/
  my-project/
    project.json            Project identity + generation defaults
    constitution.json       Rules array with rationale templates
    lanes.json              Subject lanes with detection patterns
    rubric.json             Scoring dimensions + thresholds
    terminology.json        Group vocabulary + detection order
    canon/                  Style constitution (markdown)
    records/                Per-asset JSON (provenance + judgment + canon)
    inputs/prompts/         Prompt packs (JSON)
    outputs/                Generated images (gitignored)
    comparisons/            A-vs-B preference judgments
    snapshots/              Frozen dataset snapshots
    splits/                 Train/val/test partitions
    exports/                Versioned export packages
    eval-packs/             Canon-aware eval instruments
```

## 流水线

```
canon → generate → curate → bind → snapshot → split → export → eval
  |        |          |        |        |         |        |       |
rules   ComfyUI   judgment  rules   frozen    subject  package  verify
                                    selection isolation
```

1. **定义规范**：编写您的风格指南和评估标准。
2. **生成**：ComfyUI 生成具有完整溯源信息的候选结果。
3. **筛选**：根据每个维度的评分和失败模式，进行批准/拒绝。
4. **关联**：将每个资源与规范规则关联，并给出通过/失败/部分通过的判定。
5. **快照**：将符合条件的记录冻结为具有确定性和唯一标识的选择。
6. **划分**：划分为训练集/验证集/测试集，同时进行主题隔离和类别平衡。
7. **导出**：构建一个独立的软件包，包含清单、元数据、图像和校验和。
8. **评估**：生成符合规范要求的测试工具，用于模型验证。

下游格式转换（例如：TRL、LLaVA、Parquet等）由[`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) 负责。`sdlab` 拥有数据集的原始数据，而 `repo-dataset` 将其转换为各种特定格式。

## 域名模板

每个领域模板都包含针对特定生产环境设计的车道定义、规则、评分标准和术语结构。

| 域名。 | 车道。 | 主要关注点。 |
|--------|-------|-------------|
| **game-art** | 角色、环境、道具、用户界面、飞船、内部、设备。 | 游戏中的角色轮廓、阵营区分、以及磨损/老化效果。 |
| **character-design** | 人像、全身照、360度展示图、表情图、动作姿势图。 | 比例准确性、服装的合理性、人物性格的刻画、动作的清晰度。 |
| **creature-design** | 概念、正字法、详细研究、动作、比例参考、栖息地。 | 解剖学上的合理性、进化逻辑、轮廓的独特性。 |
| **architecture** | 外观、内部、街道景观、结构细节、废墟、景观。 | 结构合理性、材料一致性、视角、时代背景的协调性。 |
| **vehicle-mech** | 外观、驾驶舱、部件、示意图、轮廓图、损坏类型。 | 机械逻辑，功能性设计语言，访问点，损坏描述。 |

## 数据集生成

完整的数据集流程：快照、分割、导出、评估。

```
snapshot  -->  split  -->  export  -->  eval-pack
   |            |            |             |
  frozen     subject      package       canon-aware
  selection  isolation    (manifest,    test instruments
             + lane       metadata,     (4 task types)
             balance      images,
                          checksums,
                          card)
```

**快照**：冻结符合条件的记录的确定性选择。每个包含记录都有其原因的追踪。配置指纹确保可重复性。

**分割**：将记录分配到训练集/验证集/测试集，同时保证样本隔离（同一个样本家族不会出现在多个分割中），并实现通道平衡的分布。使用种子伪随机数生成器，确保从相同的种子生成相同的结果。

**导出包**：是自包含的：清单、metadata.jsonl、图像（符号链接或复制）、分割、数据集卡（Markdown + JSON）以及 BSD 格式的校验和。 包含重建数据集所需的所有内容。

**评估包**：是考虑规范的测试工具，包含四种任务类型：通道覆盖、禁止漂移、锚定/黄金标准、以及样本连续性。 它们证明数据集流程正在为未来的模型评估提供支持，而不仅仅是导出文件。

通过 [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) 导出到下游格式（TRL, LLaVA, Qwen2-VL, JSONL, Parquet 等）。 `repo-dataset` 负责格式转换；`sdlab` 负责数据集的真实性。

## Star Freight 示例

克隆仓库以获取完整的示例：1182 条记录，28 个提示序列，5 个派系，7 个通道，24 条宪法规则，以及来自一个硬核科幻角色扮演游戏的 892 个已批准的资源。

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab

# Validate the project
sdlab project doctor --project star-freight

# Run the full dataset spine
sdlab snapshot create --project star-freight    # 839 eligible records
sdlab split build --project star-freight        # ~80/10/10, zero leakage
sdlab export build --project star-freight       # package with checksums
sdlab eval-pack build --project star-freight    # 78 eval records
```

## 从 v1.x 迁移

v2.0 将 `games/` 重命名为 `projects/`，并将 `--game` 重命名为 `--project`。

```bash
# Rename your data directory
mv games projects

# --game still works with a deprecation warning (removed in v3.0)
sdlab bind --game star-freight   # works, prints warning
sdlab bind --project star-freight # canonical form
```

## 安全模型

**仅本地。** 与运行在 `localhost:8188` 上的 ComfyUI 通信。 没有遥测，没有分析，没有外部请求。 图像保留在您的 GPU 和文件系统中。

## 要求

- 运行在 `localhost:8188` 上的 [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- DreamShaper XL Turbo 检查点 + ClassipeintXL LoRA
- Node.js 20+
- [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) 用于训练数据导出

## 许可证

MIT

---

由 <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a> 构建。
