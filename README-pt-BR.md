<div alinhar="centro">
  <h1>🛡️ IDE Verantyx e motor Cortex</h1>
  <p><b>O gateway de codificação de IA neurosimbólica e com vazamento zero e IDE nativo para macOS</b></p>

<p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="Versão 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README-en.md">Inglês</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brasil)</a> · <a href="README-de.md">Alemão</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">Chinês Simplificado</a> · <a href="README-zh-TW.md">Chinês Tradicional</a> · <a href="README-ko.md">한국어</a> · <a href="README.md">Japonês</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">Türkçe</a>
  </p>
</div>

---

## 📖 Sobre Verantyx

Para este projeto, quando eu estava tentando criar uma IA simbólica baseada em regras, percebi que seria impossível criá-la sozinho, então decidi controlá-la criando as partes que são controladas por mim, como a parte de aproveitamento da IA ​​atualmente convencional. (Naquela época, o openclaw estava atraindo atenção)
A partir daí, comecei a desenvolver este projeto porque pensei que seria possível evitar vazamentos de informações ofuscando o código-fonte e as solicitações do usuário em um estado semelhante a um quebra-cabeça antes de passá-los para IA de alto desempenho na nuvem.

A razão pela qual este projeto tem 0 estrelas é porque ele continha uma pasta segura e de repente eu o transformei em um repositório privado, então as 9 estrelas desapareceram. Obrigado por seu apoio contínuo enquanto me recuperei completamente. Separei as partes que parecem se sobrepor a outros repositórios. Eu estava principalmente enviando lançamentos neste repositório, mas descobri que a atualização do código-fonte estava atrasada e o atualizei.

De agora em diante, estou pensando em focar no japonês, minha língua nativa, e traduzir para o inglês usando uma ferramenta de tradução comum e publicá-la por precaução.

## 🔐 Ofuscação e estrutura cruzada 3D de 6 eixos

A ideia por trás de ofuscar este projeto é usar um método de gerenciamento de dados baseado na estrutura cruzada tridimensional encontrada no Axis, o antecessor do verantyx, que foi criado nos primeiros dias como uma imagem de como passar dados.

### 🧩 Definição de 6 dimensões (Eixo)

| Eixo | Nome | Função/Elementos extraídos |
| :--- | :--- | :--- |
| **Eixo X** | **Fluxo de controle** | Eixo de tempo e ordem. ramificações `if`, loops `for`, tratamento de exceções, etc. |
| **Eixo Y** | **Fluxo de dados** | Eixo de dependência. Atribuição de variáveis, passagem de argumentos, etc. |
| **Eixo Z** | **Restrições de tipo** | Eixo limite. Definições de classe, anotações de tipo, genéricos, etc. |
| **Eixo W** | **Ciclo de vida da memória** | Eixo da vida. Vida útil do escopo, alocação/liberação de memória. |
| **Eixo V** | **Hierarquia de escopo** | Eixo de inclusão. Módulo, estrutura de aninhamento de classe. |
| **Eixo U** | **Semântica e Significado** | **★Mais importante★ Eixo da intenção comercial. Nomes concretos de variáveis, nomes de funções, strings brutas e números. ** |

O processo de conversão é realizado instantaneamente localmente no seu MacBook pelo **Gatekeeper Engine** da Verantyx.

---

### 🔄 Código bruto para mecanismo de conversão de topologia opaca

#### Etapa 1: análise e decomposição em AST (árvore de sintaxe abstrata)
Primeiro, o mecanismo Gatekeeper (recomendado com base em regras) analisa o código-fonte de destino e converte a estrutura do programa em dados estruturados em árvore chamados AST (Abstract Syntax Tree).
Neste ponto, todas as informações ainda estão incluídas, como ``qual função está chamando o quê'', ``quais são os nomes das variáveis e o que está definido como uma string?''

#### Etapa 2: "Separação física e isolamento" da semântica (eixo U)
É aqui que Verantyx brilha. Retire fisicamente todas as **informações que indicam o significado (intenção) do negócio = eixo U** do AST.

* **Coisas que são eliminadas (eixo U)**: nomes de variáveis, nomes de funções, strings, números fixos, etc.
* **O que resta (eixos X, Y, Z, W, V)**: A estrutura lógica de ``atribuir uma variável'', ``chamar uma função'', ``ramificar com uma instrução if'' e ``fazer loop com uma instrução for.''

O nome específico e os dados da string removidos são armazenados com segurança localmente no **`JCrossIRVault` (cofre)** do seu Mac e nunca são enviados para fora.

#### Etapa 3: Totalmente criptografado para nó opaco
Os “ossos” restantes, desprovidos de significado, são transformados em uma representação totalmente opaca para envio à nuvem LLM.

* **`NODE[0x...]` (Node ID)**: Todas as variáveis ​​e elementos de sintaxe são substituídos por identificadores, como endereços de memória aleatórios.
* **`ARIDADE` (aridade/número de termos)**:
    * `class.nullary`: Um elemento sem argumentos ou conteúdo (apenas um valor ou um nó terminal).
    * `class.standard`: Operações unárias e binárias padrão (A + B, atribuição, etc.).
    * `class.multiway`: Estruturas complexas com múltiplos elementos (for loops, ramificações if-else, definições de funções, etc.).
* **`HASH` (Hash Estrutural)**: Uma soma de verificação que mostra onde o nó está no gráfico e como ele está conectado ao seu entorno. Isso permite verificar localmente se a estrutura não está quebrada quando o LLM resolve o quebra-cabeça e o retorna.

Até mesmo a instrução do código original desaparece e se torna um gráfico matemático puro: os nós `class.multiway` iteram sobre seus nós filhos.''

#### Etapa 4: Injetando “iscas” para evitar inferência estatística
Se você enviar seu código em uma estrutura de gráfico para uma parte externa, existe o risco de que IA avançada ou invasores mal-intencionados inferirão estatisticamente (engenharia reversa) que o formato desse gráfico é o formato de um script comum.

Para evitar isso, injetamos aleatoriamente **nós falsos (iscas)** nas lacunas do gráfico.
```texto
// _TOKEN_匶:0.2___jcross_BM_505__ [metadados-chamariz]
````
Ao misturar esses tokens Kanji sem sentido e conexões fictícias, a própria forma do gráfico é distorcida, tornando matematicamente impossível para a IA externa deduzir a verdadeira identidade do código-fonte original.

---

### 🧩 Como o LLM “conserta” isso? (Processo de restauração)

1. **Resolva como um quebra-cabeça**:
   Sem conhecer o código original, o LLM infere o valor da mudança alvo a partir do contexto indicado e da forma do gráfico (conexões ARITY e HASH).
2. **Devolução do patch estrutural**:
   LLM retorna apenas patches estruturais (GraphPatch) no formato JSON que reescrevem o conteúdo.
3. **Transpilação reversa local**:
   O mecanismo Gatekeeper do Mac recebe o patch e reinjeta o nome da variável real e a string (eixo U) que estavam ocultos em `JCrossIRVault` anteriormente no patch.

Como resultado, uma experiência mágica de desenvolvimento sem vazamento de informações é alcançada, onde ``Mesmo que a IA externa não tenha visto ou entendido uma única linha do código original, quando retorna ao código local, o código foi reescrito corretamente.''** *Pode haver vazamentos de informações que eu esqueci, então se você notar algum, por favor nos avise através do problema.

---

## ⚠️ Tarefas que não consigo realizar no momento (não sou bom nas quais não sou bom)

Atualmente, esta estrutura não pode lidar com tarefas como **Reescrever de Swift para Rust**, que normalmente é a tarefa mais fraca. Além disso, as tarefas 1 a 4 abaixo são difíceis para mim.

### 1. Refatorações e correções de bugs que dependem de “semântica (conhecimento de domínio)”
Como o LLM externo vê apenas o esqueleto de `NODE[0x...]`, ele não pode lidar com ``problemas que não podem ser resolvidos sem entender o significado do código''.
* **❌ Exemplo de instrução fraca**: "Adicione o prefixo `auth_` aos nomes de todas as variáveis ​​relacionadas à autenticação."
* **Motivo**: o LLM não tem visibilidade sobre "qual processo de autenticação".

### 2. Adição de novas funções que dependem fortemente de bibliotecas externas (API)
Todas as instruções `import` e chamadas de biblioteca no código-fonte também são criptografadas como `NODE`, dificultando tarefas que exigem conhecimento de bibliotecas específicas.
* **❌ Exemplo de instruções fracas**: "Adicionar a capacidade de fazer upload de arquivos para AWS S3"
* **Motivo**: o LLM não sabe quais bibliotecas externas o código atual está usando.

### 3. Escrevendo “um recurso totalmente novo do zero”
O Gatekeeper é extremamente poderoso em ``consertar e modificar estruturas existentes (AST)'', mas é fraco em ``criar novos recursos enormes que tenham significado (eixo U) e estrutura a partir de uma folha em branco.''

### 4. Deterioração da inferência devido à ineficácia do “conhecimento prévio aprendido” do próprio LLM
LLMs como Gemma e Claude ficaram mais inteligentes ao estudar códigos-fonte de todo o mundo, mas o formato que Verantyx envia é “um gráfico de símbolos puros e hashes diferente de qualquer outra linguagem no mundo”.
* **Motivo**: Como a especialidade do LLM, ``reconhecimento de padrões a partir do contexto do código'', está bloqueada, ele se torna um quebra-cabeça gráfico matemático difícil que você nunca viu antes, causando um aumento nos custos de cálculo.

### 💡 Como você está superando isso? (Perspectivas futuras)
Atualmente, a Verantyx está implementando uma combinação de ``Tri-Layer JCross Memory'' e **Visual Anchors para superar essas fraquezas. Adotamos uma abordagem em que apenas metadados seguros que não contêm informações confidenciais são parcialmente apresentados ao LLM como âncoras visuais, dando dicas enquanto mantêm a segurança.

---

## 📽️ Vídeo de demonstração e conversão de código em ação

<p alinhar="centro">
  <img src="demo.gif" alt="Verantyx Gatekeeper Demo" width="49%" style="border-radius: 8px;">
  <video src="https://github.com/verantyx/verantyx/releases/download/v1.2.5/demo_skill_generation.mov" controles="controls" muted="muted" width="49%" style="border-radius: 8px;"></video>
</p>

### Antes e Depois: Ofuscação em ação

**[Antes] Código fonte bruto (ambiente local)**
```píton
importar JSON
importar sistema operacional
importar Shutil
solicitações de importação
subprocesso de importação
importar re
de tqdm importar tqdm
sistema de importação

# Importe nosso novo analisador
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
de verantyx.cross_engine.jcross_extraction_parser importar JCrossExtractionParser

ORACLE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_m_cleaned.json"
TARGET_DIR = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v7"
QUERY_BIN = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/release/examples/query_jcross"
MODELO = "gemma4:e2b"
OLLAMA_URL = "http://localhost:11434/api/generate"

FINAL_REPORT = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/official_v7_1_accuracy_report.json"
````

**[Depois] Topologia opaca do Gatekeeper JCross (enviada para Cloud LLM)**
```ceceio
;;; 🛡️ MODO GATEKEEPER - JCross IR View
;;; Identificadores reais foram substituídos por IDs de nó.
;;; Esquema: D59144D1-BE1
;;; Nós: 124 | Segredos redigidos: 3442
;;; Fonte: cortex/bench_v7_1_puzzle_runner.py
;;;
//JCROSS_6AXIS_BEGIN
// lang:swift doc:0xD5E025

// ── NÓS DE NÍVEL SUPERIOR
  NODE[0x7995] tipo:opaco TIPO:opaco MEM:opaco HASH:0xb4af0a52 ARITY:class.multiway
  NODE[0x9DB8] tipo:opaco TIPO:opaco MEM:opaco HASH:0x504933fd ARITY:class.standard
  NODE[0x627F] tipo:opaco TIPO:opaco MEM:opaco HASH:0x97b540cb ARITY:class.multiway
  NODE[0x7F4C] tipo:opaco TIPO:opaco MEM:opaco HASH:0x86742e8c ARITY:class.standard
  NODE[0xC79E] tipo:opaco TIPO:opaco MEM:opaco HASH:0xd42206c4 ARITY:class.standard
  NODE[0x510B] tipo:opaco TIPO:opaco MEM:opaco HASH:0x14b9be4e ARITY:class.nullary
  NODE[0xB5C0] tipo:opaco TIPO:opaco MEM:opaco HASH:0xcacb18a2 ARITY:class.standard
// _TOKEN_匶:0.2___jcross_BM_505__ [metadados-chamariz]
  NODE[0xE3CF] tipo:opaco TIPO:opaco MEM:opaco HASH:0x375a5480
````

---

## 💻 Método de instalação (construir a partir do código-fonte)

**Requisitos:**
- macOS 14.0 ou posterior (Apple Silicon altamente recomendado)
- Xcode 15.0 ou posterior

```bash
clone do git https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
abra Verantyx.xcodeproj
# Selecione o esquema Verantyx e pressione Cmd+R para construir e executar
````

*Observação: as portas Windows/Linux (Rust core + llama.cpp) estão no roteiro de longo prazo, mas atualmente estamos extremamente focados em completar a arquitetura nativa do macOS/MLX. *

---

## 🔧 Sobre configurações e histórico do repositório

**Aviso sobre configurações do Git:**
Os primeiros commits para este repositório foram feitos sob o nome Git local `kofdai`, derivado do nome de usuário do macOS do desenvolvedor. Este problema foi corrigido em 24 de maio de 2026 e todos os commits agora estão atribuídos corretamente a `@Ag3497120`. Este é um problema comum na configuração do seu ambiente de desenvolvimento e não é causado por um bot ou ferramenta automatizada. Todas as contribuições futuras serão registradas com o nome correto do autor.

---

## 💡 Perguntas e respostas e recurso (recursos experimentais)

Atualmente, você pode iniciar o **Verantyx Agent** pressionando a tecla `Control` três vezes.

<p alinhar="centro">
  <img src="assets/verantyx_agent_v2.png" alt="Interface do agente Verantyx" width="600" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
</p>

Este modo foi criado como um campo de testes para os vários modos IDE encontrados em aplicações anteriores. Para revisar todo o projeto e focar no "modo gatekeeper" que é realmente necessário, consolidamos os recursos experimentais para o comportamento do agente que criamos até agora no **Verantyx Agent**.

Os principais recursos do agente incluídos nas versões anteriores são:

* **Sistema de auditoria Dual Twin**: Para evitar o problema de ferramentas de chamada de IA e negligência, introduzimos um mecanismo onde TwinB audita a validade das chamadas de ferramenta de TwinA injetando JCross internamente.
* **Introdução do Visual Anchor**: Mudamos de controle de habilidades e instruções apenas com prompts para um método híbrido de injeção de imagens e prompts usando Visual Anchor.
* **Construção do Mapa de Ativos do SO L3.5**: No agente iniciado com Control×3, o mapa interno do computador denominado "L3.5" é mantido apenas localmente. Incutimos nos agentes a consciência de que os ativos nos seus computadores estão ligados à sua própria inteligência.
* **Operação GUI de alta precisão usando API AX**: Passamos da operação GUI existente usando gravação de tela para operação confiável e de alta precisão usando a árvore API do sistema operacional (API de acessibilidade).
* **Compressão de topologia Kanji**: Ao injetar um mapa L3.5 em um contexto, gere uma imagem e use-a como um prompt para evitar que o contexto fique inchado. Ao associar um formato de compressão exclusivo denominado "Topologia Kanji" aos dados reais, garantimos que apenas os dados necessários sejam injetados conforme apropriado.
* **Expansão do modo Agente**: Adicionados dois tipos: "Modo automático" e "Modo avançado".
* **Modo de prioridade de conhecimento interno**: Para usuários avançados que usam modelos de remoção de restrições, implementamos um modo que lhes permite utilizar totalmente a IA local, não apenas como orquestrador, mas também como principal modelo de pensamento e fonte de conhecimento.
* **Linha de memória dedicada L3.5**: Para evitar que a memória de mapa L3.5 se torne complexa e grande, criamos uma linha de memória que é completamente separada da memória de conversação normal.
* **Aplicativo para ajuste fino**: Implementamos uma função que pode ser usada como ponto de apoio para extrair dados de identidade do usuário das memórias de L1 a L3.5 e realizar o ajuste fino em qualquer modelo (alcançando uma otimização que não é possível apenas com um sistema de memória).
* **Adoção da estrutura de zona FAR**: Com base na filosofia de "organizar memórias sem excluí-las", adotamos uma estrutura que registra o processo de transição, como o pacote e o título da tarefa, quando uma tarefa é concluída, e os coloca em uma nova camada chamada "zona FAR". Isso garante que memórias importantes, como o processo de trabalho, sejam retidas mesmo após a conclusão da tarefa.

Esses são apenas alguns dos recursos que estão sendo adicionados atualmente.
Uma atualização recente introduziu a orquestração (Blind Commander Architecture) usando uma versão parcialmente quantizada do `talkie-1930:13b` postada no HuggingFace. Aproveitando a limitação de “ter apenas conhecimento de 1930”, utilizamos um intermediário baseado em regras para executar comandos, e temos o papel de converter a mensagem do usuário em expressões figurativas da época. Estão sendo adicionados recursos adicionais que incorporam a filosofia "experimental" do projeto.

### 🔄 Roteiro futuro e desafios superdimensionados

Este modo agente e gatekeeper estão atualmente conectados na mesma área de armazenamento, mas no futuro planejamos implementar uma função que permitirá que eles sejam separados e ajustados.

Atualmente, o desenvolvimento deste agente atingiu um marco temporário. Como sou um estudante, uma vez que este agente seja capaz de lidar totalmente com as tarefas dadas no Teams etc. (tarefas como ``Criar e enviar as 〇〇 tarefas'' mais recentes), gostaria de começar o desenvolvimento em grande escala do ``Modo Gatekeeper'', no qual estou trabalhando atualmente como um plano de melhoria. Obrigado a todos que deram uma estrela. Por favor, espere um pouco.

Por fim, gostaria de falar sobre o desafio extragrande que preparamos como culminação deste projeto.

1. **Portando para a versão Windows (baseada em Rust)**: Esta tarefa é reescrever a implementação atualmente escrita na linguagem Swift para macOS para baseada em Rust, para que os usuários do Windows também possam experimentar a mesma função de gatekeeper.
2. **Romper completamente com a dependência da nuvem**: Tornar-se um agente que pode continuar o desenvolvimento de forma autônoma usando apenas LLM local sem pagar taxas caras de API. Gostaríamos de utilizar um modelo de classe 20B que roda em um MacBook (como o recente `qwen3.6:27b`, que é considerado comparável ao modelo mais sofisticado sob certas condições), operar um agente de codificação próximo ao nível da nuvem e prosseguir com o projeto fazendo melhorias de forma autônoma.