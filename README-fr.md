<div align="centre">
  <h1>🛡️ IDE Verantyx et moteur Cortex</h1>
  <p><b>La passerelle de codage d'IA neuro-symbolique sans fuite et l'IDE macOS natif</b></p>

<p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="Version 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README-en.md">Anglais</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brésil)</a> · <a href="README-de.md">Allemand</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">Chinois simplifié</a> · <a href="README-zh-TW.md">Chinois traditionnel</a> · <a href="README-ko.md">한국어</a> · <a href="README.md">Japonais</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">Türkçe</a>
  </p>
</div>

---

## 📖 À propos de Verantyx

Pour ce projet, alors que j'essayais auparavant de créer une IA symbolique basée sur des règles, j'ai réalisé qu'il serait impossible de la créer par moi-même, j'ai donc décidé de la contrôler en créant les parties qui sont contrôlées par moi-même, comme la partie harnais de l'IA actuellement dominante. (A cette époque, openclaw attirait l'attention)
À partir de là, j'ai commencé à développer ce projet parce que je pensais qu'il serait possible d'empêcher les fuites d'informations en obscurcissant le code source et les demandes des utilisateurs dans un état semblable à un puzzle avant de les transmettre à une IA haute performance dans le cloud.

La raison pour laquelle ce projet a 0 étoiles est qu'il contenait un dossier sécurisé et que j'en ai soudainement fait un référentiel privé, donc les 9 étoiles ont disparu. Merci pour votre soutien continu car je me suis complètement rétabli. J'ai trié les parties qui semblent chevaucher avec d'autres référentiels. Je poussais principalement des versions dans ce référentiel, mais j'ai constaté que la mise à jour du code source était retardée et je l'ai mis à jour.

À partir de maintenant, je pense me concentrer sur le japonais, ma langue maternelle, et traduire l'anglais à l'aide d'un outil de traduction classique et le publier au cas où.

## 🔐 Obfuscation et structure croisée 3D 6 axes

L'idée derrière ce projet est d'utiliser une méthode de gestion des données basée sur la structure croisée tridimensionnelle trouvée dans Axis, le prédécesseur de verantyx, qui a été créé au début comme une image de la façon de transmettre des données.

### 🧩 Définition de 6 dimensions (Axe)

| Axe | Nom | Rôle / Éléments extraits |
| :--- | :--- | :--- |
| **Axe X** | **Flux de contrôle** | Axe temps et commande. branches `if`, boucles `for`, gestion des exceptions, etc. |
| **Axe Y** | **Flux de données** | Axe de dépendance. Affectation de variables, passage d'arguments, etc. |
| **Axe Z** | **Contraintes de type** | Axe limite. Définitions de classes, annotations de types, génériques, etc. |
| **Axe W** | **Cycle de vie de la mémoire** | Axe de vie. Durée de vie de la portée, allocation/libération de mémoire. |
| **Axe V** | **Hiérarchie de portée** | Axe d'inclusion. Module, structure d'imbrication de classes. |
| **Axe U** | **Sémantique et signification** | **★Le plus important★ Axe d'intention commerciale. Noms de variables concrets, noms de fonctions, chaînes brutes et nombres. ** |

Le processus de conversion est instantanément effectué localement sur votre MacBook par le **Gatekeeper Engine** de Verantyx.

---

### 🔄 Mécanisme de conversion de code brut en topologie opaque

#### Étape 1 : Analyse et décomposition en AST (Abstract Syntax Tree)
Tout d'abord, le moteur Gatekeeper (basé sur des règles recommandées) analyse le code source cible et convertit la structure du programme en données arborescentes appelées AST (Abstract Syntax Tree).
À ce stade, toutes les informations sont toujours incluses, telles que « quelle fonction appelle quoi », « quels sont les noms de variables et qu'est-ce qui est défini comme chaîne ? »

#### Étape 2 : "Séparation et isolement physiques" de la sémantique (axe U)
C'est là que Verantyx brille. Supprimez physiquement toutes les **informations indiquant la signification (l'intention) de l'entreprise = axe U** de l'AST.

* **Éléments supprimés (axe U)** : noms de variables, noms de fonctions, chaînes, nombres fixes, etc.
* **Ce qui reste (axes X, Y, Z, W, V)** : Le cadre logique de « l'attribution d'une variable », « l'appel d'une fonction », « le branchement avec une instruction if » et la « boucle avec une instruction for ».

Le nom spécifique supprimé et les données de chaîne sont stockés en toute sécurité localement dans le **`JCrossIRVault` (coffre-fort)** de votre Mac et ne sont jamais envoyés à l'extérieur.

#### Étape 3 : Entièrement chiffré sur un nœud opaque
Les « os » restants, dénués de sens, sont transformés en une représentation totalement opaque pour envoi vers le cloud LLM.

* **`NODE[0x...]` (Node ID)** : Toutes les variables et éléments de syntaxe sont remplacés par des identifiants, tels que des adresses de mémoire aléatoire.
* **`ARITY` (arité/nombre de termes)** :
    * `class.nullary` : Un élément sans argument ni contenu (juste une valeur ou un nœud terminal).
    * `class.standard` : Opérations unaires et binaires standards (A + B, affectation, etc.).
    * `class.multiway` : structures complexes avec plusieurs éléments (boucles for, branches if-else, définitions de fonctions, etc.).
* **`HASH` (Structural Hash)** : Une somme de contrôle qui montre où se trouve le nœud dans le graphique et comment il est connecté à son environnement. Cela vous permet de vérifier localement que la structure n'est pas cassée lorsque LLM résout le puzzle et le renvoie.

Même l'instruction de code d'origine disparaît et devient un pur graphe mathématique : les nœuds `class.multiway` parcourent leurs nœuds enfants.''

#### Étape 4 : Injecter des « leurres » pour empêcher l'inférence statistique
Si vous envoyez votre code dans une structure graphique à un tiers externe, il existe un risque qu'une IA avancée ou des attaquants malveillants déduisent statistiquement (ingénierie inverse) que la forme de ce graphique est la forme d'un script commun.

Pour éviter cela, nous injectons de manière aléatoire des **faux nœuds (leurres)** dans les espaces du graphique.
```texte
// _TOKEN_匶:0.2___jcross_BM_505__ [leurre-métadonnées]
````
En mélangeant ces jetons Kanji dénués de sens et ces connexions factices, la forme même du graphique est déformée, rendant mathématiquement impossible pour une IA externe de déduire la véritable identité du code source d'origine.

---

### 🧩 Comment le LLM « résout » ce problème ? (Processus de restauration)

1. **Résolvez un puzzle** :
   Sans connaître le code d'origine, LLM déduit la valeur du changement cible à partir du contexte indiqué et de la forme du graphe (connexions ARITY et HASH).
2. **Retour du patch structurel** :
   LLM renvoie uniquement des correctifs structurels (GraphPatch) au format JSON qui réécrivent le contenu.
3. **Transpilation inversée locale** :
   Le moteur Gatekeeper de Mac reçoit le correctif et réinjecte le vrai nom de variable et la chaîne (axe U) qui étaient cachés dans « JCrossIRVault » plus tôt dans le correctif.

En conséquence, une expérience de développement magique sans fuite d'informations est obtenue, où « Même si l'IA externe n'a pas vu ou compris une seule ligne du code d'origine, lorsqu'elle revient au code local, le code a été réécrit correctement. »** *Il peut y avoir des fuites d'informations que j'ai négligées, donc si vous en remarquez, veuillez nous en informer via un problème.

---

## ⚠️ Tâches que je ne suis actuellement pas en mesure de gérer (je ne suis pas bon pour cela)

Actuellement, cette structure ne peut pas gérer des tâches telles que la **Réécriture de Swift vers Rust**, qui est généralement la tâche la plus faible. De plus, les tâches 1 à 4 ci-dessous sont difficiles pour moi.

### 1. Refactorings et corrections de bugs qui dépendent de la « sémantique (connaissance du domaine) »
Puisque le LLM externe ne voit que le squelette de `NODE[0x...]`, il ne peut pas traiter les "problèmes qui ne peuvent être résolus sans comprendre la signification du code".
* **❌ Exemple d'instruction faible** : "Ajoutez le préfixe `auth_` aux noms de toutes les variables liées à l'authentification."
* **Raison** : LLM n'a aucune visibilité sur "quel processus d'authentification".

### 2. Ajout de nouvelles fonctions qui dépendent fortement de bibliothèques externes (API)
Toutes les instructions `import` et les appels à la bibliothèque dans le code source sont également cryptés en tant que `NODE`, ce qui rend difficiles les tâches qui nécessitent la connaissance de bibliothèques spécifiques.
* **❌ Exemple d'instructions faibles** : "Ajouter la possibilité de télécharger des fichiers sur AWS S3."
* **Raison** : LLM ne sait pas quelles bibliothèques externes le code actuel utilise.

### 3. Écrire « une toute nouvelle fonctionnalité à partir de zéro »
Gatekeeper est extrêmement puissant pour « corriger et modifier les structures existantes (AST) », mais il est faible pour « créer d'énormes nouvelles fonctionnalités qui ont à la fois une signification (axe U) et une structure à partir d'une page vierge ».

### 4. Détérioration de l'inférence due à l'inefficacité des « connaissances acquises antérieurement » du LLM lui-même
Les LLM comme Gemma et Claude sont devenus plus intelligents en étudiant le code source du monde entier, mais le format envoyé par Verantyx est « un graphique de symboles purs et de hachages qui ne ressemble à aucun autre langage au monde ».
* **Raison** : Parce que la spécialité de LLM, « reconnaissance de formes à partir du contexte de code », est bloquée, cela devient un casse-tête graphique mathématique difficile que vous n'avez jamais vu auparavant, provoquant une augmentation des coûts de calcul.

### 💡 Comment faites-vous pour surmonter cela ? (Perspectives d'avenir)
Actuellement, Verantyx implémente une combinaison de « Tri-Layer JCross Memory » et **Visual Anchors pour surmonter ces faiblesses. Nous adoptons une approche dans laquelle seules les métadonnées sécurisées qui ne contiennent pas d'informations sensibles sont partiellement présentées à LLM sous forme d'ancres visuelles, donnant des indices tout en préservant la sécurité.

---

## 📽️ Vidéo de démonstration et conversion de code en action

<p align="center">
  <img src="demo.gif" alt="Démo Verantyx Gatekeeper" width="49%" style="border-radius: 8px;">
  <video src="https://github.com/verantyx/verantyx/releases/download/v1.2.5/demo_skill_generation.mov" controles="controls" muted="muted" width="49%" style="border-radius: 8px;"></video>
</p>

### Avant et après : l'obscurcissement en action

**[Avant] Code source brut (environnement local)**
```python
importer json
importer le système d'exploitation
importer des produits
demandes d'importation
sous-processus d'importation
importer re
depuis tqdm importer tqdm
système d'importation

# Importez notre nouvel analyseur
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
à partir de verantyx.cross_engine.jcross_extraction_parser importer JCrossExtractionParser

ORACLE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_m_cleaned.json"
TARGET_DIR = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v7"
QUERY_BIN = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/release/examples/query_jcross"
MODÈLE = "gemma4:e2b"
OLLAMA_URL = "http://localhost:11434/api/generate"

FINAL_REPORT = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/official_v7_1_accuracy_report.json"
````

**[Après] Topologie opaque JCross Gatekeeper (envoyée à Cloud LLM)**
```zézaiement
;;; 🛡️ MODE GATEKEEPER - Vue IR JCross
;;; Les véritables identifiants ont été remplacés par des identifiants de nœud.
;;; Schéma : D59144D1-BE1
;;; Nœuds : 124 | Secrets expurgés : 3442
;;; Source : cortex/bench_v7_1_puzzle_runner.py
;;;
// JCROSS_6AXIS_BEGIN
// langue: rapide doc: 0xD5E025

// ── NŒUDS DE HAUT NIVEAU
  NODE[0x7995] kind:opaque TYPE:opaque MEM:opaque HASH:0xb4af0a52 ARITY:class.multiway
  NODE[0x9DB8] genre : opaque TYPE : opaque MEM : opaque HASH : 0x504933fd ARITÉ : classe.standard
  NODE[0x627F] genre : opaque TYPE : opaque MEM : opaque HASH : 0x97b540cb ARITÉ : classe.multiway
  NODE[0x7F4C] genre:opaque TYPE:opaque MEM:opaque HASH:0x86742e8c ARITY:class.standard
  NODE[0xC79E] genre:opaque TYPE:opaque MEM:opaque HASH:0xd42206c4 ARITY:class.standard
  NODE[0x510B] genre:opaque TYPE:opaque MEM:opaque HASH:0x14b9be4e ARITY:class.nullary
  NODE[0xB5C0] genre:opaque TYPE:opaque MEM:opaque HASH:0xcacb18a2 ARITY:class.standard
// _TOKEN_匶:0.2___jcross_BM_505__ [leurre-métadonnées]
  NODE[0xE3CF] genre:opaque TYPE:opaque MEM:opaque HASH:0x375a5480
````

---

## 💻 Méthode d'installation (build à partir des sources)

**Exigences :**
- macOS 14.0 ou version ultérieure (Apple Silicon fortement recommandé)
- Xcode 15.0 ou version ultérieure

````bash
clone git https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
ouvrez Verantyx.xcodeproj
# Sélectionnez le schéma Verantyx et appuyez sur Cmd+R pour créer et exécuter
````

*Remarque : les ports Windows/Linux (Rust core + llama.cpp) sont sur la feuille de route à long terme, mais nous sommes actuellement extrêmement concentrés sur l'achèvement de l'architecture native macOS/MLX. *

---

## 🔧 À propos des paramètres et de l'historique du référentiel

**Avis concernant les paramètres Git :**
Les premiers commits dans ce référentiel ont été effectués sous le nom Git local « kofdai », dérivé du nom d'utilisateur macOS du développeur. Ce problème a été résolu le 24 mai 2026 et tous les commits sont désormais correctement attribués à « @Ag3497120 ». Il s'agit d'un problème courant lors de la configuration de votre environnement de développement et n'est pas causé par un robot ou un outil automatisé. Toutes les contributions futures seront enregistrées avec le nom d'auteur correct.

---

## 💡 Questions et réponses et appel (fonctionnalités expérimentales)

Actuellement, vous pouvez démarrer **Verantyx Agent** en appuyant trois fois sur la touche « Contrôle ».

<p align="center">
  <img src="assets/verantyx_agent_v2.png" alt="Interface de l'agent Verantyx" width="600" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
</p>

Ce mode a été créé comme terrain de test pour les différents modes IDE trouvés dans les applications précédentes. Afin de revoir l'ensemble du projet et de nous concentrer sur le « mode gardien » qui est réellement nécessaire, nous avons consolidé les fonctionnalités expérimentales pour le comportement des agents que nous avons créées jusqu'à présent dans **Verantyx Agent**.

Les principales fonctionnalités de l'agent incluses dans les versions précédentes sont :

* **Système d'audit Dual Twin** : Afin d'éviter le problème des appels d'outils d'IA et de la négligence, nous avons introduit un mécanisme par lequel TwinB audite la validité des appels d'outils de TwinA en injectant JCross en interne.
* **Introduction de Visual Anchor** : nous sommes passés du contrôle des compétences et des instructions uniquement avec des invites à une méthode hybride d'injection d'images et d'invites utilisant Visual Anchor.
* **Construction de la carte des actifs du système d'exploitation L3.5** : Dans l'agent démarré avec Control×3, la carte informatique interne appelée "L3.5" est maintenue uniquement localement. Nous avons sensibilisé les agents au fait que les actifs présents sur leurs ordinateurs sont connectés à leur propre intelligence.
* **Opération GUI de haute précision utilisant l'API AX** : Nous sommes passés de l'opération GUI existante utilisant l'enregistrement d'écran à un fonctionnement fiable et de haute précision utilisant l'arborescence API du système d'exploitation (API d'accessibilité).
* **Compression de topologie Kanji** : lors de l'injection d'une carte L3.5 dans un contexte, générez une image et utilisez-la comme invite pour éviter que le contexte ne devienne gonflé. En associant un format de compression unique appelé « Topologie Kanji » aux données réelles, nous nous sommes assurés que seules les données nécessaires sont injectées de manière appropriée.
* **Extension du mode Agent** : Ajout de deux types : "Mode automatique" et "Mode avancé".
* **Mode de priorité aux connaissances internes** : pour les utilisateurs expérimentés qui utilisent des modèles de suppression des restrictions, nous avons mis en œuvre un mode qui leur permet d'utiliser pleinement l'IA locale non seulement en tant qu'orchestrateur, mais également en tant que principal modèle de pensée et source de connaissances.
* **Ligne mémoire dédiée L3.5** : Pour éviter que la mémoire cartographique L3.5 ne devienne complexe et volumineuse, nous avons créé une ligne mémoire complètement distincte de la mémoire de conversation normale.
* **Application au réglage fin** : Nous avons implémenté une fonction qui peut être utilisée comme point d'appui pour extraire les données d'identité de l'utilisateur des mémoires de L1 à L3.5 et effectuer un réglage fin sur n'importe quel modèle (réalisant une optimisation qui n'est pas possible avec un système de mémoire seul).
* **Adoption de la structure de zone FAR** : Basé sur la philosophie « d'organiser les mémoires sans les supprimer », nous avons adopté une structure qui enregistre le processus de transition tel que le package de tâches et le titre lorsqu'une tâche est terminée, et le dépose dans une nouvelle couche appelée « zone FAR ». Cela garantit que les mémoires importantes, telles que le processus de travail, sont conservées même une fois la tâche terminée.

Ce ne sont là que quelques-unes des fonctionnalités actuellement ajoutées.
Une mise à jour récente a introduit l'orchestration (Blind Commander Architecture) utilisant une version partiellement quantifiée de « talkie-1930:13b » publiée sur HuggingFace. Profitant de la limitation de « n'avoir que des connaissances de 1930 », nous utilisons un intermédiaire basé sur des règles pour exécuter les commandes, et avons pour rôle de convertir le message de l'utilisateur en expressions figuratives de l'époque. Des fonctionnalités supplémentaires sont ajoutées qui incarnent la philosophie « expérimentale » du projet.

### 🔄 Feuille de route future et défis surdimensionnés

Ces modes agent et gatekeeper sont actuellement connectés dans la même zone de stockage, mais nous prévoyons à l'avenir de mettre en place une fonction qui permettra de les séparer et de les affiner.

Actuellement, le développement de cet agent a atteint une étape temporaire. Comme je suis moi-même étudiant, une fois que cet agent sera capable de gérer pleinement les tâches données dans Teams, etc. (tâches telles que « Créer et soumettre les tâches 〇〇 les plus récentes »), j'aimerais commencer le développement à grande échelle du « Mode Gatekeeper », sur lequel je travaille actuellement en tant que plan d'amélioration. Merci à tous ceux qui ont donné une étoile. Veuillez patienter un moment.

Enfin, je voudrais parler du défi extra-large que nous avons préparé comme point culminant de ce projet.

1. **Portage vers la version Windows (basée sur Rust)** : cette tâche consiste à réécrire l'implémentation actuellement écrite dans le langage Swift pour macOS vers une version basée sur Rust, afin que les utilisateurs Windows puissent également bénéficier de la même fonction de contrôleur d'accès.
2. **Supprimer complètement la dépendance au cloud** : devenir un agent capable de poursuivre le développement de manière autonome en utilisant uniquement le LLM local sans payer de frais d'API coûteux. Nous aimerions utiliser un modèle de classe 20B qui fonctionne sur un MacBook (comme le récent « qwen3.6:27b », qui est considéré comme comparable au modèle haut de gamme dans certaines conditions), exploiter un agent de codage proche du niveau cloud et poursuivre le projet en apportant des améliorations de manière autonome.