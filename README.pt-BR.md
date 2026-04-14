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

Uma linha de produção para a criação de conjuntos de dados visuais – desde regras predefinidas até prompts estruturados, passando pela geração no ComfyUI, até dados de treinamento selecionados e vinculados a regras predefinidas.

## O que é isso

Uma **linha de produção** para a criação de conjuntos de dados visuais estruturados para treinamento. Você define regras de estilo (regras predefinidas), compõe prompts, gera imagens com o ComfyUI, seleciona os resultados com base em critérios específicos, associa as avaliações às regras predefinidas e exporta em 10 formatos através do [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset).

A linha de produção é independente de qualquer jogo específico. Cada jogo possui seu próprio diretório de dados em `games/<nome>/`; os 13 scripts e modelos vazios são compartilhados. Cada ativo gerado contém três elementos.

1. **Pixels da imagem** – gerados pelo ComfyUI com total rastreabilidade (checkpoint, LoRA, seed, sampler, cfg).
2. **Explicação detalhada** – por que este elemento está ou não de acordo com o estilo definido, com base em uma "constituição" de estilo.
3. **Avaliação de qualidade** – aprovado/rejeitado, com pontuações por dimensão e regras citadas.

## Modelo de segurança

**Apenas local.** O style-dataset-lab se comunica com o ComfyUI em `localhost:8188` e nunca faz solicitações de rede externas. Sem telemetria, sem análise, sem envio de dados. A geração de imagens ocorre inteiramente na sua GPU. Os registros e os dados de referência permanecem no seu sistema de arquivos.

## O que o pacote npm oferece:

`npm install @mcptoolshop/style-dataset-lab` fornece:

- **13 scripts** – para geração, seleção, comparação, vinculação a regras predefinidas, estilo pictórico, geração de identidade, geração ControlNet/IP-Adapter, seleção em massa, migração.
- **Modelos vazios** – um modelo inicial, um guia de avaliação e um conjunto de exemplos de prompts, localizados em `templates/`.

O pacote npm **não** inclui dados de jogos. Clone o repositório se você quiser o exemplo do Star Freight (1.182 registros, 28 sequências de prompts, 18 categorias visuais).

## Instalação

```bash
# Get the pipeline scripts + templates
npm install @mcptoolshop/style-dataset-lab

# Or clone the repo for the Star Freight example data
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
npm install
```

Para iniciar um novo jogo a partir dos modelos:

```bash
# Copy templates into your game directory
mkdir -p games/my-game/{records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
cp -r templates/canon games/my-game/canon
cp templates/inputs/prompts/example-wave.json games/my-game/inputs/prompts/wave1.json
# Edit the canon and prompts, then generate
```

## Estrutura do monorepository

A linha de produção está localizada nos diretórios `scripts/` e `templates/`. Cada jogo está em `games/<nome>/`, com suas próprias regras predefinidas, registros e ativos. Os scripts aceitam o argumento `--game <nome>` (o padrão é `star-freight`).

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

## Fluxo de trabalho da linha de produção

A linha de produção completa, desde as regras predefinidas até a exportação para treinamento:

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

## Adicionando um novo jogo

```bash
# Create structure and copy blank templates
mkdir -p games/my-game/{records,comparisons,inputs/prompts,outputs/{candidates,approved,rejected,borderline,painterly},exports}
cp -r templates/canon games/my-game/canon
cp templates/inputs/prompts/example-wave.json games/my-game/inputs/prompts/wave1.json

# Edit your canon/constitution.md and canon/review-rubric.md
# Edit your prompt pack, then run the pipeline with --game my-game
```

## Estrutura do diretório por jogo

Cada diretório `games/<nome>/` contém:

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
