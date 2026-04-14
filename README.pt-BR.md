<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.md">English</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/style-dataset-lab/readme.png" width="400">
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/@mcptoolshop/style-dataset-lab"><img src="https://img.shields.io/npm/v/@mcptoolshop/style-dataset-lab" alt="npm"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

# style-dataset-lab

Ferramenta para criação de conjuntos de dados visuais – gera, organiza e exporta dados de treinamento multimodais para o ajuste fino de modelos de linguagem visuais (VLM).

## O que é isso

Um conjunto de ferramentas para construir a "verdade visual" que pode ser usada para treinamento. Cada elemento contém três coisas:

1. **Pixels da imagem** – gerados pelo ComfyUI com total rastreabilidade (checkpoint, LoRA, seed, sampler, cfg).
2. **Explicação detalhada** – por que este elemento está ou não de acordo com o estilo definido, com base em uma "constituição" de estilo.
3. **Avaliação de qualidade** – aprovado/rejeitado, com pontuações por dimensão e regras citadas.

A saída é integrada ao [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) para produzir dados de treinamento multimodais em 10 formatos: TRL, LLaVA, Qwen2-VL, Axolotl, LLaMA-Factory, ShareGPT, pares para RLHF, DPO, legendagem e classificação.

## Modelo de segurança

**Apenas local.** O style-dataset-lab se comunica com o ComfyUI em `localhost:8188` e nunca faz solicitações de rede externas. Sem telemetria, sem análise, sem envio de dados. A geração de imagens ocorre inteiramente na sua GPU. Os registros e os dados de referência permanecem no seu sistema de arquivos.

## Estatísticas do conjunto de dados

| Métrica | Valor |
|--------|-------|
| Registros organizados | 1,182 |
| Total de elementos | 2.571 (893 aprovados, 887 variações com estilo pictórico) |
| Variações de prompts | 28 |
| Categorias visuais | 18 (roupas, navios, interiores, equipamentos, ambientes, espécies, estações, sinalização, iluminação, carga, arquitetura, criaturas, superfícies, vida cotidiana, planetas, danos/reparos, biologia alienígena, detalhes realistas) |
| Comparativos | 6 criados por humanos + 71 criados sinteticamente |
| Tipos de rejeição distintos | 30+ |
| Sistema de pacotes de identidade | Personagens nomeados com DNA de facção, patente e referências visuais. |
| Formatos de exportação | 10 (via @mcptoolshop/repo-dataset) |

## Instalação

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Em seguida, clone um projeto ou inicialize um novo espaço de trabalho para conjuntos de dados:

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab my-dataset
cd my-dataset
npm install
```

## Fluxo de trabalho

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

## Estrutura de diretórios

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

## Configuração de geração

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

Modos de geração adicionais: ControlNet (guiado por pose/profundidade), IP-Adapter (guiado por referência) e pacotes de identidade (consistência de personagens nomeados).

## Requisitos

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) em execução em localhost:8188
- Checkpoint DreamShaper XL Turbo + LoRA ClassipeintXL
- Node.js 20+
- [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) para exportação de treinamento

## Licença

MIT

---

Criado por <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a
