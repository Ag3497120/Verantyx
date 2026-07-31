<div align="centre">
  <h1>🛡️ Verantyx (moteur d'IA vérifiable et auditable)</h1>
  <p><b>La passerelle de codage d'IA neuro-symbolique sans fuite et l'IDE macOS natif</b></p>

<p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="Version 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README.md">Anglais</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brésil)</a> · <a href="README-de.md">Allemand</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">Chinois simplifié</a> · <a href="README-zh-TW.md">Chinois traditionnel</a> · <a href="README-ko.md">한국어</a> · <a href="README-ja.md">Japonais</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">Türkçe</a>
  </p>
</div>

---

Verantyx est un moteur logique neuro-symbolique de nouvelle génération qui rend le développement de logiciels basé sur l'IA entièrement contrôlable et sécurisé.
Nous proposons deux parties avant différentes en plus d'un moteur de base puissant (mémoire JCross/L3.5). Veuillez choisir en fonction de votre objectif.

---

## 1. 🖥️ Verantyx Gatekeeper (Mode IDE)
**"Je souhaite que le cloud LLM lise le code confidentiel de mon entreprise en toute sécurité"**

Le mode Gatekeeper est l'IDE sécurisé ultime qui masque votre code source en énigmes mathématiques dénuées de sens (topologie opaque) avant de le transmettre à l'IA.
👉 [Cliquez ici pour plus de détails sur le mode Gatekeeper et le mécanisme d'obscurcissement (README-Gatekeeper.md)](./docs/README-Gatekeeper.md)

## 2. ⚡ Agent Verantyx (Mode Spotlight)
**"Je souhaite utiliser pleinement l'IA locale la plus puissante comme extension de mon cerveau"**

Il s'agit d'un agent hyper-autonome qui peut être activé en appuyant simplement trois fois sur la touche « Contrôle ». Il est équipé d'un audit interne utilisant Dual Twin, d'un blocage physique des hallucinations utilisant la métaphore des années 1930 et d'un moteur de réflexion de nouvelle génération qui reconnaît les actifs du PC comme « vos propres souvenirs (L3.5) ».
👉 [Cliquez ici pour les détails et l'architecture du mode Agent (README-Agent.md)](./docs/README-Agent.md)

---

## 💻 Méthode d'installation (build à partir des sources)

**Exigences :**
- macOS 14.0 ou version ultérieure (Apple Silicon fortement recommandé)
- Xcode 15.0 ou version ultérieure

```bash
clone git https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
ouvrez Verantyx.xcodeproj
# Sélectionnez le schéma Verantyx et appuyez sur Cmd+R pour créer et exécuter
````

*Remarque : les ports Windows/Linux (Rust core + llama.cpp) sont sur la feuille de route à long terme, mais nous sommes actuellement extrêmement concentrés sur l'achèvement de l'architecture native macOS/MLX. *

---

## 📖 À propos de Verantyx

Pour ce projet, alors que j'essayais auparavant de créer une IA symbolique basée sur des règles, j'ai réalisé qu'il serait impossible de la créer par moi-même, j'ai donc décidé de la contrôler en créant les parties qui sont contrôlées par moi-même, comme la partie harnais de l'IA actuellement dominante. (A cette époque, openclaw attirait l'attention)
À partir de là, j'ai commencé à développer ce projet parce que je pensais qu'il serait possible d'empêcher les fuites d'informations en obscurcissant le code source et les demandes des utilisateurs dans un état semblable à un puzzle avant de les transmettre à une IA haute performance dans le cloud.

La raison pour laquelle ce projet a 0 étoiles est qu'il contenait un dossier sécurisé et que j'en ai soudainement fait un référentiel privé, donc les 9 étoiles ont disparu. Merci pour votre soutien continu car je me suis complètement rétabli. J'ai trié les parties qui semblent chevaucher avec d'autres référentiels. Je poussais principalement des versions dans ce référentiel, mais j'ai constaté que la mise à jour du code source était retardée et je l'ai mis à jour.

À partir de maintenant, je pense me concentrer sur le japonais, ma langue maternelle, et traduire l'anglais à l'aide d'un outil de traduction classique et le publier au cas où.

---

## 🔧 À propos des paramètres et de l'historique du référentiel

**Avis concernant les paramètres Git :**
Les premiers commits dans ce référentiel ont été effectués sous le nom Git local « kofdai », dérivé du nom d'utilisateur macOS du développeur. Ce problème a été résolu le 24 mai 2026 et tous les commits sont désormais correctement attribués à « @Ag3497120 ». Il s'agit d'un problème courant lors de la configuration de votre environnement de développement et n'est pas causé par un robot ou un outil automatisé. Toutes les contributions futures seront enregistrées avec le nom d'auteur correct.