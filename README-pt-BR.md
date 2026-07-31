<div alinhar="centro">
  <h1>🛡️ Verantyx (mecanismo de IA verificável e auditável)</h1>
  <p><b>O gateway de codificação de IA neurosimbólica e com vazamento zero e IDE nativo para macOS</b></p>

<p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="Versão 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README.md">Inglês</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brasil)</a> · <a href="README-de.md">Alemão</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">Chinês Simplificado</a> · <a href="README-zh-TW.md">Chinês Tradicional</a> · <a href="README-ko.md">한국어</a> · <a href="README-ja.md">Japonês</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">Türkçe</a>
  </p>
</div>

---

Verantyx é um mecanismo lógico neuro-simbólico de última geração que torna o desenvolvimento de software baseado em IA totalmente controlável e seguro.
Oferecemos dois front-ends diferentes em cima de um poderoso mecanismo central (memória JCross/L3.5). Escolha de acordo com seu propósito.

---

## 1. 🖥️ Verantyx Gatekeeper (modo IDE)
**"Quero que o Cloud LLM leia o código confidencial da minha empresa com segurança"**

O modo Gatekeeper é o IDE seguro definitivo que ofusca seu código-fonte em quebra-cabeças matemáticos sem sentido (topologia opaca) antes de passá-lo para a IA.
👉 [Clique aqui para obter detalhes sobre o modo Gatekeeper e mecanismo de ofuscação (README-Gatekeeper.md)](./docs/README-Gatekeeper.md)

## 2. ⚡ Agente Verantyx (modo Spotlight)
**“Quero utilizar totalmente a IA local mais poderosa como uma extensão do meu cérebro”**

É um agente hiperautônomo que pode ser ativado simplesmente pressionando a tecla `Control` três vezes. É equipado com auditoria interna usando Dual Twin, bloqueio físico de alucinações usando a metáfora de 1930 e um mecanismo de pensamento de última geração que reconhece os ativos do PC como “suas próprias memórias (L3.5)”.
👉 [Clique aqui para detalhes e arquitetura do modo Agente (README-Agent.md)](./docs/README-Agent.md)

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

## 📖 Sobre Verantyx

Para este projeto, quando eu estava tentando criar uma IA simbólica baseada em regras, percebi que seria impossível criá-la sozinho, então decidi controlá-la criando as partes que são controladas por mim, como a parte de aproveitamento da IA atualmente convencional. (Naquela época, o openclaw estava atraindo atenção)
A partir daí, comecei a desenvolver este projeto porque pensei que seria possível evitar vazamentos de informações ofuscando o código-fonte e as solicitações do usuário em um estado semelhante a um quebra-cabeça antes de passá-los para IA de alto desempenho na nuvem.

A razão pela qual este projeto tem 0 estrelas é porque ele continha uma pasta segura e de repente eu o transformei em um repositório privado, então as 9 estrelas desapareceram. Obrigado por seu apoio contínuo enquanto me recuperei completamente. Separei as partes que parecem se sobrepor a outros repositórios. Eu estava principalmente enviando lançamentos neste repositório, mas descobri que a atualização do código-fonte estava atrasada e o atualizei.

De agora em diante, estou pensando em focar no japonês, minha língua nativa, e traduzir para o inglês usando uma ferramenta de tradução comum e publicá-la por precaução.

---

## 🔧 Sobre configurações e histórico do repositório

**Aviso sobre configurações do Git:**
Os primeiros commits para este repositório foram feitos sob o nome Git local `kofdai`, derivado do nome de usuário do macOS do desenvolvedor. Este problema foi corrigido em 24 de maio de 2026 e todos os commits agora estão atribuídos corretamente a `@Ag3497120`. Este é um problema comum na configuração do seu ambiente de desenvolvimento e não é causado por um bot ou ferramenta automatizada. Todas as contribuições futuras serão registradas com o nome correto do autor.