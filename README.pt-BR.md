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

Transforme trabalhos visuais aprovados em conjuntos de dados versionados, com revisões, divisões, pacotes de exportação e pacotes de avaliação.

## O que é isso

Um **pipeline de produção de conjuntos de dados e de referências visuais**. Defina a aparência do seu projeto. Crie conjuntos de dados de acordo com as regras estabelecidas. Produza pacotes de dados reproduzíveis com divisões seguras contra vazamento de informações. Gere pacotes de avaliação para a verificação futura do modelo.

O pipeline produz quatro artefatos:

| Artefato | O que é |
|----------|-----------|
| **Snapshot** | Seleção de registros elegíveis, com informações detalhadas e rastreáveis. Cada inclusão tem uma justificativa explícita. |
| **Split** | Partição de treinamento/validação/teste segura contra vazamento de informações. Registros que compartilham a mesma família de sujeitos sempre ficam na mesma divisão. |
| **Export package** | Conjunto de dados autônomo: manifesto, metadados, imagens, divisões, descrição do conjunto de dados e checksums. |
| **Eval pack** | Tarefas de verificação compatíveis com as referências: cobertura de aspectos, prevenção de desvios indesejados, pontos de referência/referências, continuidade do sujeito. |

Cada ativo no pipeline contém três elementos:

1. **Rastreabilidade** -- histórico completo de geração (checkpoint, LoRA, seed, sampler, cfg, tempo de execução)
2. **Conformidade com as referências** -- quais regras de estilo este ativo cumpre, não cumpre ou cumpre parcialmente
3. **Avaliação de qualidade** -- aprovado/rejeitado/limítrofe, com pontuações por dimensão

Funciona para arte de jogos, design de personagens, design de criaturas, arquitetura, conceitos de veículos/máquinas, e qualquer área onde a produção visual precisa seguir um padrão.

## Como começar

```bash
# Install the CLI + pipeline
npm install -g @mcptoolshop/style-dataset-lab

# Scaffold a new project
sdlab init my-project --domain character-design

# Validate the project structure
sdlab project doctor --project my-project
```

Domínios disponíveis: `game-art`, `character-design`, `creature-design`, `architecture`, `vehicle-mech` ou `generic`.

## Interface de linha de comando (CLI)

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

Todos os comandos aceitam `--project <nome>` (padrão: `star-freight`).

## Modelo do projeto

Cada projeto é um diretório autônomo dentro de `projects/`, com suas próprias referências, configuração e dados:

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

## Pipeline

```
canon → generate → curate → bind → snapshot → split → export → eval
  |        |          |        |        |         |        |       |
rules   ComfyUI   judgment  rules   frozen    subject  package  verify
                                    selection isolation
```

1. **Definir referências** -- escreva sua constituição de estilo e guia de revisão
2. **Gerar** -- o ComfyUI produz candidatos com rastreabilidade completa
3. **Curadoria** -- aprovar/rejeitar com pontuações por dimensão e modos de falha
4. **Associar** -- vincular cada ativo às regras de estilo, com veredictos de aprovação/rejeição/parcial
5. **Captura de instantâneo** -- congelar os registros elegíveis em uma seleção determinística e identificada
6. **Dividir** -- particionar em treinamento/validação/teste, com isolamento do sujeito e equilíbrio de aspectos
7. **Exportar** -- criar um pacote autônomo com manifesto, metadados, imagens e checksums
8. **Avaliar** -- gerar instrumentos de teste compatíveis com as referências para a verificação do modelo

A conversão de formato para outros sistemas (TRL, LLaVA, Parquet, etc.) é gerenciada por [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset). O `sdlab` define a "verdade" do conjunto de dados; o `repo-dataset` a transforma em formatos especializados.

## Modelos de domínio

Cada modelo de domínio é fornecido com definições de aspectos, regras de estilo, guias de pontuação e estruturas de terminologia projetadas para aquele contexto de produção:

| Domínio | Aspectos | Principais preocupações |
|--------|-------|-------------|
| **game-art** | personagem, ambiente, acessório, interface do usuário, nave, interior, equipamento | Silhueta na escala do jogo, diferenciação de facções, desgaste/envelhecimento |
| **character-design** | retrato, corpo inteiro, vista de 360 graus, folha de expressões, pose de ação | Precisão das proporções, lógica do figurino, leitura da personalidade, clareza dos gestos |
| **creature-design** | conceito, ortográfico, estudo de detalhes, ação, referência de escala, habitat | Plausibilidade anatômica, lógica evolutiva, distinção de silhuetas |
| **architecture** | exterior, interior, paisagem urbana, detalhe estrutural, ruína, paisagem | Plausibilidade estrutural, consistência dos materiais, perspectiva, coerência da época |
| **vehicle-mech** | exterior, cockpit, componente, esquema, folha de silhuetas, variação de dano | Lógica mecânica, linguagem de design funcional, pontos de acesso, descrição de danos. |

## Produção do conjunto de dados

A estrutura completa do conjunto de dados: instantâneo, divisão, exportação, avaliação.

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

**Instantâneos** congelam uma seleção determinística de registros elegíveis. Cada inclusão tem um registro de motivo. As "impressões digitais" de configuração garantem a reprodutibilidade.

**Divisões** atribuem registros às partições de treinamento/validação/teste, com isolamento de sujeitos (nenhuma família de sujeitos aparece em várias divisões) e distribuição equilibrada por "faixa". Um gerador de números pseudoaleatórios (PRNG) com semente garante resultados idênticos a partir da mesma semente.

Os **pacotes de exportação** são autônomos: manifesto, metadata.jsonl, imagens (com links simbólicos ou cópias), divisões, cartão do conjunto de dados (Markdown + JSON) e somas de verificação no formato BSD. Tudo o que é necessário para reconstruir o conjunto de dados do zero.

Os **pacotes de avaliação** são instrumentos de teste que levam em consideração o contexto e possuem quatro tipos de tarefas: cobertura de "faixas", desvio proibido, âncora/referência e continuidade do sujeito. Eles comprovam que a estrutura do conjunto de dados está sendo usada para futuras avaliações de modelos, e não apenas para descartar arquivos.

Exportação para formatos compatíveis através de [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) (TRL, LLaVA, Qwen2-VL, JSONL, Parquet, e mais). `repo-dataset` gerencia a conversão de formatos; `sdlab` detém a "verdade" do conjunto de dados.

## Exemplo do Star Freight

Clone o repositório para um exemplo completo e funcional: 1.182 registros, 28 "ondas" de prompts, 5 facções, 7 "faixas", 24 regras constitucionais e 892 ativos aprovados de um RPG de ficção científica.

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

## Migrando da versão v1.x

A versão 2.0 renomeia `games/` para `projects/` e `--game` para `--project`:

```bash
# Rename your data directory
mv games projects

# --game still works with a deprecation warning (removed in v3.0)
sdlab bind --game star-freight   # works, prints warning
sdlab bind --project star-freight # canonical form
```

## Modelo de segurança

**Apenas local.** Comunica-se com o ComfyUI em `localhost:8188`. Sem telemetria, sem análises, sem requisições externas. As imagens permanecem na sua GPU e sistema de arquivos.

## Requisitos

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) em execução em localhost:8188
- Checkpoint DreamShaper XL Turbo + LoRA ClassipeintXL
- Node.js 20+
- [`@mcptoolshop/repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset) para exportação de treinamento

## Licença

MIT

---

Criado por <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a
