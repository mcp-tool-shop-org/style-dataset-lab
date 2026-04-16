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

Escreva suas regras visuais. Gere imagens. Avalie cada imagem com base nessas regras. Envie os resultados como dados de treinamento versionados e auditáveis.

O Style Dataset Lab conecta o que você escreveu sobre o estilo da sua arte ao conjunto de dados que você realmente usa para treinamento. Você define uma estrutura – regras de silhueta, restrições de paleta, linguagem de materiais, o que for importante para o seu projeto. O processo gera candidatos, os avalia com base nessas regras e organiza as obras aprovadas em conjuntos de dados reproduzíveis, onde cada registro explica por que foi incluído.

O ciclo se fecha: treine um modelo, gere novas saídas, avalie-as com base nos mesmos critérios e reintroduza o que for aprovado. O conjunto de dados cresce e as regras permanecem válidas.

## O processo

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

Aquele último comando é crucial. As saídas geradas passam pelo mesmo processo de revisão de tudo o mais. O ciclo se fecha.

## O que ele produz

Sete artefatos versionados e com checksum. Cada um está vinculado aos seus predecessores, para que você possa rastrear qualquer registro de treinamento até a regra que o aprovou.

| Artefato | O que é |
|----------|-----------|
| **Snapshot** | Seleção de registros fixos com impressão digital de configuração. Cada inclusão tem uma razão explícita. |
| **Split** | Partição de treinamento/validação/teste, onde as famílias de elementos nunca ultrapassam as fronteiras. |
| **Export package** | Conjunto de dados autônomo: manifesto, metadados, imagens, divisões, descrição do conjunto de dados e checksums. |
| **Eval pack** | Tarefas de verificação compatíveis com as referências: cobertura de aspectos, prevenção de desvios indesejados, pontos de referência/referências, continuidade do sujeito. |
| **Training package** | Formato pronto para treinamento através de adaptadores (`diffusers-lora`, `generic-image-caption`). A mesma informação, em formato diferente. |
| **Eval scorecard** | Avaliação de aprovação/reprovação para cada tarefa, com base na avaliação das saídas geradas. |
| **Implementation pack** | Exemplos de prompts, falhas conhecidas, testes de continuidade e diretrizes para reintrodução. |

## Por que isso existe

Os dados de treinamento são o recurso mais valioso em qualquer pipeline de IA visual. No entanto, a maioria dos dados de treinamento é apenas uma pasta de imagens sem histórico, sem rastreamento de avaliação e sem conexão com as regras de estilo que deveria seguir.

O Style Dataset Lab torna essa conexão explícita. Sua estrutura define as regras. Sua rubrica define as dimensões de avaliação. Seus registros de curadoria documentam a avaliação. Seu cânone vinculante prova a conexão. E seu conjunto de dados carrega tudo isso como uma verdade estruturada, pesquisável e reproduzível.

O resultado prático: quando seu LoRA se desvia, você pode perguntar *por quê*. Quando sua próxima rodada de treinamento precisar de melhores dados, você saberá exatamente quais registros estão próximos do ideal e qual regra específica eles não cumpriram. Quando um novo membro da equipe perguntar qual é a linguagem visual do projeto, a resposta não é um quadro do Figma – é uma estrutura pesquisável com 1.182 exemplos classificados.

## Cinco domínios, regras reais

Não são modelos genéricos. Cada domínio é fornecido com regras de estrutura de produção, definições de categorias, rubricas de avaliação e vocabulário específico.

| Domínio | Aspectos | O que é avaliado. |
|--------|-------|-----------------|
| **game-art** | personagem, ambiente, acessório, interface do usuário, nave, interior, equipamento | Silhueta em escala de jogabilidade, identificação de facção, desgaste e envelhecimento. |
| **character-design** | retrato, corpo inteiro, vista de 360 graus, folha de expressões, pose de ação | Proporções, lógica de figurino, personalidade, clareza de gestos. |
| **creature-design** | conceito, ortográfico, estudo de detalhes, ação, referência de escala, habitat | Anatomia, lógica evolutiva, distinção de silhueta. |
| **architecture** | exterior, interior, paisagem urbana, detalhe estrutural, ruína, paisagem | Estrutura, consistência de materiais, perspectiva, coerência de época. |
| **vehicle-mech** | exterior, cockpit, componente, esquema, folha de silhuetas, variação de dano | Lógica mecânica, linguagem de design funcional, pontos de acesso, descrição de danos. |

## Estrutura do projeto

Cada projeto é autônomo. Cinco arquivos de configuração JSON definem as regras; o resto é apenas dados.

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

## Propriedades de confiabilidade

Essas propriedades não são apenas desejáveis; elas são aplicadas.

- **Os snapshots são imutáveis.** A impressão digital de configuração (SHA-256) prova que nada foi alterado.
- **As divisões evitam vazamentos.** As famílias de elementos (por identidade, linhagem ou sufixo de ID) nunca ultrapassam as fronteiras das partições.
- **Os manifestos são contratos fixos.** Hash de exportação + impressão digital de configuração. Se algo mudar, crie um novo.
- **Os adaptadores não podem alterar a verdade.** Formato diferente, mesmos registros. Sem adições, sem remoções, sem reclassificações.
- **As saídas geradas são submetidas à revisão.** Sem atalhos. Curadoria e vinculação como tudo o mais.

## Star Freight

O repositório inclui um exemplo completo e funcional: 1.182 registros, 5 facções, 7 caminhos, 24 regras constitucionais, 892 ativos aprovados e 2 perfis de treinamento. Um cânone visual de RPG de ficção científica, totalmente organizado.

```bash
git clone https://github.com/mcp-tool-shop-org/style-dataset-lab
cd style-dataset-lab
sdlab project doctor --project star-freight
sdlab snapshot create --project star-freight   # 839 eligible records
sdlab split build --project star-freight       # zero subject leakage
```

## Formatos compatíveis

O projeto `sdlab` é o proprietário do conjunto de dados. A conversão de formatos é gerenciada pelo [`repo-dataset`](https://github.com/mcp-tool-shop-org/repo-dataset): TRL, LLaVA, Qwen2-VL, JSONL, Parquet e outros. O `repo-dataset` é responsável pela renderização; ele nunca decide a inclusão de dados.

## Instalação

```bash
npm install -g @mcptoolshop/style-dataset-lab
```

Requer Node.js 20 ou superior e o [ComfyUI](https://github.com/comfyanonymous/ComfyUI) instalado localmente no endereço localhost:8188 para a geração.

## Segurança

Funciona apenas localmente. Não há coleta de dados de uso, análises ou requisições externas. As imagens permanecem na sua GPU e no seu sistema de arquivos.

## Licença

MIT

---

Criado por <a href="https://mcp-tool-shop.github.io/">MCP Tool Shop</a
