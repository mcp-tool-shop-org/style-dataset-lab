<p align="center">
  <a href="README.md">English</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
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

視覚的なルールを定義します。画像生成を行い、生成された画像を定義したルールに基づいて評価します。評価結果をバージョン管理された、監査可能な学習データとして出力し、その学習データを用いて訓練したモデルを実際の運用環境で活用します。そして、最も優れた結果を学習データに再投入します。

Style Dataset Labは、お客様が記述されたアートスタイルに関する情報と、実際に学習に使用するデータセットを連携させます。お客様は、シルエットのルール、カラーパレットの制限、素材に関する記述など、プロジェクトにとって重要な要素を定義します。このシステムは、定義されたルールに基づいて候補を生成し、それらを評価し、承認された作品を再現可能なデータセットにまとめます。このデータセットでは、各レコードが、なぜその作品が選択されたのかを説明しています。

次に、本番環境用のワークベンチが稼働します。プロジェクトの要件に基づいて生成指示を作成し、ComfyUIで実行し、結果を評価し、表現シートや環境ボードをまとめて作成し、最適な結果を選択し、新しい候補として再登録します。このサイクルを繰り返します。生成、選択、評価、改善。

## パイプライン

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

この最後のコマンドが重要です。選択された出力は、他のすべてのデータと同様に、同じ評価プロセスを経ます。学習データが蓄積され、ルールが維持されます。

## それが生成するものは何か

7種類のデータセットファイルと、完全な本番環境用ワークベンチが含まれています。各ファイルは、以前のファイルとリンクされており、どの学習記録も、それを承認したルールまで遡ることができます。

| 成果物 | 内容 |
|----------|-----------|
| **Snapshot** | 設定情報と合わせて、一度記録されたデータは固定され、変更されません。すべてのデータには、そのデータが記録された理由が明示的に記載されています。 |
| **Split** | 学習データ、検証データ、テストデータに分割する際、対象となる家族がデータセットの境界線をまたがないようにする。 |
| **Export package** | 自己完結型のデータセット：マニフェスト、メタデータ、画像、分割データ、データセットの説明、およびチェックサム。 |
| **Eval pack** | 規定に準拠した検証タスク：表現の網羅性、許容されない変化、基準/正解データ、対象の一貫性。 |
| **Training package** | アダプター（`diffusers-lora`、`generic-image-caption`）を使用することで、トレーニングに適した構成にすることができます。同じ原理に基づいているものの、形式が異なります。 |
| **Eval scorecard** | 各タスクごとに、評価データセットと照合して生成された結果に基づいて、合格/不合格を判定します。 |
| **Implementation pack** | プロンプトの例、既知の問題点、動作確認テスト、および再取り込みに関する手順。 |

本番環境用ワークベンチには、以下が含まれます。

| 機能 | 概要 |
|---------|-------------|
| **Compiled brief** | ワークフロープロファイルとプロジェクト要件に基づいて、決定論的な画像生成を行います。 |
| **Run** | 生成結果の記録：指示、シード値、ComfyUIの出力、マニフェストファイル。 |
| **Critique** | 生成結果を基準と比較し、多角的な評価を行います。 |
| **Batch** | 表現シート、環境ボード、シルエットパックなど、複数の要素をまとめて生成します。 |
| **Selection** | 選択された出力について、なぜ選択されたのか、どこから来たのかといった情報を記録します。 |
| **Re-ingest** | 選択された出力は、生成元の情報を含む候補レコードとして登録されます。 |

## なぜこれが存在するのか

トレーニングデータは、あらゆる画像認識AIのパイプラインにおいて、最も重要な要素です。しかし、多くのトレーニングデータは、履歴や判断の記録が一切なく、また、本来従うべきスタイルルールとの関連性も欠けている、単なる画像ファイル群に過ぎません。

Style Dataset Labは、これらの要素間の関連性を明確に示します。あなたの規定はルールを定義し、評価基準は評価の基準を定義します。キュレーション記録は判断を記録し、規範文書は関連性を証明します。そして、あなたのデータセットは、これらの要素を構造化された、検索可能で、再現可能な真実として体系的にまとめて提供します。

具体的な結果として、LoRAモデルの性能が低下した場合、「なぜ」その原因を特定できます。また、次の学習ラウンドでより良いデータが必要になった場合、どのデータがわずかに基準に達していないのか、そしてそれがどの特定のルールに違反しているのかを正確に把握できます。さらに、新しいチームメンバーがプロジェクトのビジュアル表現について質問された場合、答えはFigmaのボードではなく、1,182の評価済みサンプルを含む、検索可能な規定書となります。

## 5つの分野、そして明確なルール

これは単なるプレースホルダーのテンプレートではありません。各分野には、実用レベルの構成ルール、レーン定義、採点基準、および関連語彙が用意されています。

| ドメイン | 表現 | 何が評価されるのか。 |
|--------|-------|-----------------|
| **game-art** | キャラクター、環境、小道具、UI、船、内装、装備 | ゲームプレイ時の外観、派閥ごとの特徴、使用感、経年劣化。 |
| **character-design** | ポートレート、全身像、アングル図、表情シート、アクションポーズ | プロポーション、衣装の合理性、人物の性格、身振り手振りの表現力。 |
| **creature-design** | コンセプト、正投影図、詳細図、アクション、スケール参照、生息地 | 解剖学的構造、進化論的な論理、シルエットの識別。 |
| **architecture** | 外観、内装、街並み、構造の詳細、廃墟、風景 | 構造、素材の一貫性、視点、時代背景との整合性。 |
| **vehicle-mech** | 外観、コックピット、コンポーネント、設計図、シルエット図、損傷バリエーション | 機械的なロジック、機能的なデザイン言語、アクセスポイント、損害状況の説明 |

## プロジェクトの構成

各プロジェクトは独立した構成になっています。5つのJSON設定ファイルがルールを定義し、それ以外の部分はすべてデータです。

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

## 信託財産

これらは目標や理想ではなく、義務として定められています。

- **スナップショットは不変です。** 設定のフィンガープリント（SHA-256）は、何も変更されていないことを証明します。
- **分割によって情報漏洩を防ぎます。** データセット（ID、系統、またはIDの末尾による分類）は、パーティションの境界を越えることはありません。
- **マニフェストは固定された契約です。** エクスポートのハッシュ値と設定のフィンガープリントを含みます。 何か変更があった場合は、新しいものを新たに作成してください。
- **アダプターは真実を改変できません。** レイアウトは異なる場合でも、同じレコードが含まれます。 追加、削除、再分類は一切ありません。
- **生成された出力は、必ずレビュープロセスを経て再利用されます。** スキップすることはできません。 他のデータと同様に、キュレーションと紐付けを行います。

## スターフレイト

このリポジトリには、完全で動作するサンプルが含まれています。具体的には、1,182件のデータ、5つの派閥、7つのルート、24個の憲法ルール、892個の承認済みアセット、および2つのトレーニングプロファイルが含まれています。これは、徹底的にキュレーションされた、ハードなSF RPGのビジュアル表現です。

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## 対応形式

`sdlab` がこのデータセットを所有しています。フォーマット変換は、[`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) によって処理されます。対応形式は、TRL、LLaVA、Qwen2-VL、JSONL、Parquetなどです。`repo-dataset` はデータのレンダリングを担当し、データの取り込みに関する判断は行いません。

## インストール

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

生成には、Node.js 20以降のバージョンと、ローカルホストの8188番ポートで動作している [ComfyUI](https://github.com/comfyanonymous/ComfyUI) が必要です。

### ComfyUIなしで試す

ComfyUIをインストールしたり、SDXLのモデルファイルをダウンロードしたりせずに、検査、キュレーション、スナップショット、分割、エクスポートなど、すべての機能を「Star Freight」プロジェクトを通じて利用できます。

```bash
# Scaffold a fresh project (no ComfyUI needed)
sdlab init test --domain game-art

# Run the canonical health check (no ComfyUI needed)
sdlab project doctor --project test

# Dry-run a snapshot against the bundled Star Freight corpus
sdlab snapshot create --dry-run --project star-freight
```

`sdlab project doctor`コマンドは、すべてのプロジェクト設定（構成、ルール、評価基準、用語集）を検証し、GPUに負荷をかけずに、プロジェクトが利用可能かどうかを報告します。生成状態を変更するコマンドには、事前に効果を確認するための`--dry-run`オプションがあります。

`--project`オプションを省略すると、CLIは`projects/`ディレクトリにある最初のプロジェクトを使用し、警告を表示します。警告を抑制するには、`--project`オプションを明示的に指定してください。

### 中断されたジョブの再開

長時間のジョブ実行中に中断が発生した場合でも、完了済みの作業をやり直すことなく、ジョブを再開することができます。

```bash
# Skip subjects whose record + image are already on disk.
# Seeds are preserved — resumed runs are bit-identical to fresh ones.
sdlab generate inputs/prompts/wave1.json --project my-project --resume

# Re-run only failed/missing slots in an existing batch.
# Inherits mode/subject/theme from the prior manifest.
sdlab batch generate --resume batch_2026-04-22_001 --project my-project
```

これらのコマンドは、いずれも正常に動作します。なぜなら、各処理ステップは、完了時にその結果を完全に記録するため、ジョブ実行中に問題が発生した場合でも、部分的に完了した状態が破損することはないからです。

## トラブルシューティング

一般的なエラーと解決策：

**`ECONNREFUSED 127.0.0.1:8188`が発生した場合（`sdlab generate`、`sdlab run generate`、`sdlab batch generate`など）**
ComfyUIが実行されていません。ComfyUIを起動します（`python main.py --listen 127.0.0.1 --port 8188`）。`curl http://127.0.0.1:8188/system_stats`で確認できます。別のホストまたはポートを使用する場合は、`COMFY_URL=http://host:port`を設定します。

**`missing checkpoint` / `LoRA weight not found`が発生した場合**
ワークフロープロファイルで指定されているモデルファイルが、ComfyUIの`models/checkpoints/`または`models/loras/`フォルダに存在しません。`projects/<project>/workflows/profiles/<profile>.json`を開き、`checkpoint`または`lora`の項目を探し、指定されたモデルファイルをダウンロードするか、代わりに既存のファイルを使用してください。修正後、`sdlab project doctor --project <project>`を再実行して確認します。

**`sdlab project doctor`でエラーが発生した場合**
Doctorは、構造化されたエラーコードを返します。一般的なエラーは以下の通りです。
- `E_PROJECT_NOT_FOUND`：プロジェクトディレクトリが`projects/`ディレクトリに存在しません。スペルを確認してください。
- `E_CONFIG_INVALID`：5つのJSON設定ファイルのいずれかが、スキーマ検証に失敗しました。`hint`の項目には、問題のあるファイルとフィールドの名前が表示されます。
- `E_RECORD_DRIFT`：レコードの設定フィンガープリントが、元のデータと一致しなくなりました。`hint`に示されているように、再キュレーションまたは再バインドを行ってください。

**`No --project specified, falling back to <name>`という警告が表示された場合**
これは、警告です。正しいプロジェクトを選択し、警告を抑制するには、`--project <name>`オプションを明示的に指定してください。

**ペインタリー処理 / VRAMのメモリ不足に関する問題**
ペインタリー処理の調整に関する詳細は、`docs/internal/HANDOFF.md` を参照してください。簡単に言うと、ノイズ除去の強度を下げたり、バッチサイズを小さくしたり、ワークフロープロファイルでより小さいチェックポイントを使用するように変更してください。

**バグの報告**
バグを発見した場合は、https://github.com/mcp-tool-shop-org/style-dataset-lab/issues に、`sdlab --version` で確認できるsdlabのバージョン、`node -v` で確認できるNodeのバージョン、実行したコマンド全体、および構造化されたエラー出力を添えて報告してください。バグレポートのテンプレートには、必要な項目が事前に入力されています。

## セキュリティ

ローカル環境でのみ動作します。テレメトリー、分析、外部へのリクエストは一切ありません。画像はすべて、あなたのGPUとファイルシステム内に保存されます。

## ライセンス

MITライセンス

---

開発：<a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
