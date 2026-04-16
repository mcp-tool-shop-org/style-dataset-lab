<p align="center">
  <a href="README.md">English</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/style-dataset-lab/readme.png" width="400">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@mcptoolshop/style-dataset-lab"><img src="https://img.shields.io/npm/v/@mcptoolshop/style-dataset-lab" alt="npm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

視覚的なルールを定義してください。それに基づいて画像を生成し、生成されたすべての画像をそのルールに照らし合わせて評価します。そして、バージョン管理された、監査可能なトレーニングデータとして結果を配布します。

Style Dataset Labは、お客様が記述されたアートスタイルに関する情報と、実際に学習に使用するデータセットを連携させます。お客様は、シルエットのルール、カラーパレットの制限、素材に関する記述など、プロジェクトにとって重要な要素を定義します。このシステムは、定義されたルールに基づいて候補を生成し、それらを評価し、承認された作品を再現可能なデータセットにまとめます。このデータセットでは、各レコードが、なぜその作品が選択されたのかを説明しています。

このプロセスはループを形成します。モデルを訓練し、新しい出力を生成し、それらを同じ基準で評価し、評価基準を満たしたものをデータセットに再取り込みます。データセットは徐々に成長し、そのルールは維持されます。

## パイプライン

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

最後のコマンドが重要な点です。生成された出力も、他のものと同様に、同じ審査プロセスを経ます。これにより、一連の作業が完了し、サイクルが閉じます。

## それが生成するものは何か

バージョン管理された7つのデータセットがあり、それぞれにチェックサムが付与されています。各データセットは、その前のバージョンとリンクされており、これにより、どのトレーニング記録も、それを承認したルールまで遡って追跡することができます。

| 成果物 | 内容 |
|----------|-----------|
| **Snapshot** | 設定情報と合わせて、一度記録されたデータは固定され、変更されません。すべてのデータには、そのデータが記録された理由が明示的に記載されています。 |
| **Split** | 学習データ、検証データ、テストデータに分割する際、対象となる家族がデータセットの境界線をまたがないようにする。 |
| **Export package** | 自己完結型のデータセット：マニフェスト、メタデータ、画像、分割データ、データセットの説明、およびチェックサム。 |
| **Eval pack** | 規定に準拠した検証タスク：表現の網羅性、許容されない変化、基準/正解データ、対象の一貫性。 |
| **Training package** | アダプター（`diffusers-lora`、`generic-image-caption`）を使用することで、トレーニングに適した構成にすることができます。同じ原理に基づいているものの、形式が異なります。 |
| **Eval scorecard** | 各タスクごとに、評価データセットと照合して生成された結果に基づいて、合格/不合格を判定します。 |
| **Implementation pack** | プロンプトの例、既知の問題点、動作確認テスト、および再取り込みに関する手順。 |

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

## セキュリティ

ローカル環境でのみ動作します。テレメトリー、分析、外部へのリクエストは一切ありません。画像はすべて、あなたのGPUとファイルシステム内に保存されます。

## ライセンス

MIT

---

開発：<a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a>
