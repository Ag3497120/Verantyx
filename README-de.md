<div align="center">
  <h1>🛡️ Verantyx IDE & Cortex Engine</h1>
  <p><b>Das Zero-Leakage, Neuro-Symbolic AI Coding Gateway und die native macOS IDE</b></p>

<p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="Version 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README-en.md">Englisch</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brasilien)</a> · <a href="README-de.md">Deutsch</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">Vereinfachtes Chinesisch</a> · <a href="README-zh-TW.md">Traditionelles Chinesisch</a> · <a href="README-ko.md">한국어</a> · <a href="README.md">Japanisch</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Russisch</a> · <a href="README-uk.md">Türkisch</a> · <a href="README-tr.md">Türkisch</a>
  </p>
</div>

---

## 📖 Über Verantyx

Als ich für dieses Projekt zuvor versuchte, eine regelbasierte symbolische KI zu erstellen, wurde mir klar, dass es unmöglich sein würde, sie selbst zu erstellen, also beschloss ich, sie zu steuern, indem ich die Teile erstellte, die ich selbst kontrollierte, wie zum Beispiel den Geschirrteil der derzeit gängigen KI. (Zu dieser Zeit erregte Openclaw Aufmerksamkeit)
Von dort aus begann ich mit der Entwicklung dieses Projekts, weil ich dachte, dass es möglich wäre, Informationslecks zu verhindern, indem der Quellcode und die Benutzeranfragen in einem rätselhaften Zustand verschleiert werden, bevor sie an die Hochleistungs-KI in der Cloud übergeben werden.

Der Grund, warum dieses Projekt 0 Sterne hat, liegt darin, dass es einen sicheren Ordner enthielt und ich es plötzlich zu einem privaten Repository gemacht habe, sodass die 9 Sterne verschwunden sind. Vielen Dank für Ihre anhaltende Unterstützung, da ich mich vollständig erholt habe. Ich habe Teile aussortiert, die sich mit anderen Repositories zu überschneiden scheinen. Ich habe hauptsächlich Veröffentlichungen in diesem Repository vorangetrieben, aber ich habe festgestellt, dass die Aktualisierung des Quellcodes verzögert war, und habe sie aktualisiert.

Von nun an denke ich darüber nach, mich auf Japanisch, meine Muttersprache, zu konzentrieren und Englisch mit einem normalen Übersetzungstool zu übersetzen und es für alle Fälle zu veröffentlichen.

## 🔐 Verschleierung und 6-Achsen-3D-Kreuzstruktur

Die Idee hinter diesem Projekt besteht darin, eine Datenverwaltungsmethode zu verwenden, die auf der dreidimensionalen Kreuzstruktur von Axis, dem Vorgänger von Verantyx, basiert und in den frühen Tagen als Abbild für die Weitergabe von Daten erstellt wurde.

### 🧩 Definition von 6 Dimensionen (Achse)

| Achse | Name | Rolle / Extrahierte Elemente |
| :--- | :--- | :--- |
| **X-Achse** | **Kontrollfluss** | Zeit- und Ordnungsachse. „if“-Verzweigungen, „for“-Schleifen, Ausnahmebehandlung usw. |
| **Y-Achse** | **Datenfluss** | Abhängigkeitsachse. Variablenzuweisung, Argumentübergabe usw. |
| **Z-Achse** | **Typbeschränkungen** | Grenzachse. Klassendefinitionen, Typanmerkungen, Generika usw. |
| **W-Achse** | **Speicherlebenszyklus** | Achse des Lebens. Scope-Lebensdauer, Speicherzuweisung/-freigabe. |
| **V-Achse** | **Bereichshierarchie** | Achse der Inklusion. Modul, Klassenverschachtelungsstruktur. |
| **U-Achse** | **Semantik & Bedeutung** | **★Am wichtigsten★ Achse der Geschäftsabsicht. Konkrete Variablennamen, Funktionsnamen, Rohzeichenfolgen und Zahlen. ** |

Der Konvertierungsprozess wird sofort lokal auf Ihrem MacBook durch die **Gatekeeper Engine** von Verantyx durchgeführt.

---

### 🔄 Konvertierungsmechanismus für Rohcode in undurchsichtige Topologie

#### Schritt 1: Parsen und Zerlegen in AST (Abstract Syntax Tree)
Zunächst analysiert die Gatekeeper-Engine (regelbasiert empfohlen) den Zielquellcode und wandelt die Programmstruktur in baumstrukturierte Daten namens AST (Abstract Syntax Tree) um.
Zu diesem Zeitpunkt sind noch alle Informationen enthalten, z. B. „Welche Funktion ruft was auf“, „Wie lauten die Variablennamen und was ist als String definiert?“

#### Schritt 2: „Physikalische Trennung und Isolation“ der Semantik (U-Achse)
Hier glänzt Verantyx. Entfernen Sie physisch alle **Informationen, die die Bedeutung (Absicht) des Geschäfts angeben = U-Achse** aus dem AST.

* **Dinge, die entfernt werden (U-Achse)**: Variablennamen, Funktionsnamen, Zeichenfolgen, feste Zahlen usw.
* **Was bleibt (X-, Y-, Z-, W-, V-Achse)**: Der logische Rahmen für „Zuweisen einer Variablen“, „Aufrufen einer Funktion“, „Verzweigen mit einer if-Anweisung“ und „Schleife mit einer for-Anweisung“.

Die entfernten spezifischen Namens- und Zeichenfolgendaten werden sicher lokal im **`JCrossIRVault` (Tresor)** Ihres Mac gespeichert und niemals nach außen gesendet.

#### Schritt 3: Vollständig verschlüsselt zum undurchsichtigen Knoten
Die verbleibenden „Knochen“ werden ihrer Bedeutung beraubt und in eine völlig undurchsichtige Darstellung zum Senden an Cloud LLM umgewandelt.

* **`NODE[0x...]` (Knoten-ID)**: Alle Variablen und Syntaxelemente werden durch Bezeichner ersetzt, wie z. B. zufällige Speicheradressen.
* **`ARITY` (Arität/Anzahl der Begriffe)**:
    * „class.nullary“: Ein Element ohne Argumente oder Inhalt (nur ein Wert oder ein Endknoten).
    * „class.standard“: Standardmäßige unäre und binäre Operationen (A + B, Zuweisung usw.).
    * „class.multiway“: Komplexe Strukturen mit mehreren Elementen (für Schleifen, if-else-Zweige, Funktionsdefinitionen usw.).
* **`HASH` (Struktureller Hash)**: Eine Prüfsumme, die zeigt, wo sich der Knoten im Diagramm befindet und wie er mit seiner Umgebung verbunden ist. Auf diese Weise können Sie lokal überprüfen, ob die Struktur nicht beschädigt ist, wenn LLM das Rätsel löst und zurückgibt.

Sogar die ursprüngliche Codeanweisung verschwindet und wird zu einem rein mathematischen Diagramm: „class.multiway“-Knoten iterieren über ihre untergeordneten Knoten.“

#### Schritt 4: Einschleusen von „Ködern“, um statistische Schlussfolgerungen zu verhindern
Wenn Sie Ihren Code in einer Diagrammstruktur an eine externe Partei senden, besteht das Risiko, dass fortgeschrittene KI oder böswillige Angreifer statistisch ableiten (Reverse Engineering), dass die Form dieses Diagramms die Form eines allgemeinen Skripts ist.

Um dies zu verhindern, fügen wir zufällig **falsche Knoten (Köder)** in die Lücken im Diagramm ein.
„Text
// _TOKEN_匶:0.2___jcross_BM_505__ [decoy-metadata]
````
Durch das Einmischen dieser bedeutungslosen Kanji-Tokens und Scheinverbindungen wird die eigentliche Form des Diagramms verzerrt, wodurch es für externe KI mathematisch unmöglich wird, die wahre Identität des ursprünglichen Quellcodes abzuleiten.

---

### 🧩 Wie „behebt“ LLM dieses Problem? (Restaurierungsprozess)

1. **Als Rätsel lösen**:
   Ohne den Originalcode zu kennen, leitet LLM den Wert der Zieländerung aus dem angegebenen Kontext und der Form des Diagramms (ARITY- und HASH-Verbindungen) ab.
2. **Rückgabe des Strukturpatches**:
   LLM gibt nur strukturelle Patches (GraphPatch) im JSON-Format zurück, die den Inhalt neu schreiben.
3. **Lokale Rücktranspilation**:
   Die Gatekeeper-Engine von Mac empfängt den Patch und fügt den echten Variablennamen und die Zeichenfolge (U-Achse), die zuvor in „JCrossIRVault“ verborgen waren, erneut in den Patch ein.

Dadurch wird ein magisches Entwicklungserlebnis ohne Informationslecks erreicht, bei dem „Auch wenn die externe KI keine einzige Zeile des Originalcodes gesehen oder verstanden hat, der Code bei der Rückkehr zum lokalen Code korrekt umgeschrieben wurde.“** *Es kann sein, dass es Informationslecks gibt, die ich übersehen habe. Wenn Sie also welche bemerken, teilen Sie uns dies bitte über das Problem mit.

---

## ⚠️Aufgaben, die ich derzeit nicht bewältigen kann (in denen ich nicht gut bin)

Derzeit kann diese Struktur keine Aufgaben wie **Umschreiben von Swift zu Rust** bewältigen, was normalerweise die schwächste Aufgabe ist. Auch die Aufgaben 1 bis 4 unten fallen mir schwer.

### 1. Refactorings und Fehlerbehebungen, die von „Semantik (Domänenwissen)“ abhängen
Da das externe LLM nur das Grundgerüst von „NODE[0x...]“ sieht, kann es sich nicht mit „Problemen, die nicht gelöst werden können, ohne die Bedeutung des Codes zu verstehen“ befassen.
* **❌ Beispiel einer schwachen Anweisung**: „Fügen Sie das Präfix „auth_“ zu den Namen aller Variablen hinzu, die sich auf die Authentifizierung beziehen.“
* **Grund**: LLM hat keinen Einblick in „welchen Authentifizierungsprozess“.

### 2. Hinzufügung neuer Funktionen, die stark von externen Bibliotheken (API) abhängen
Alle „Import“-Anweisungen und Bibliotheksaufrufe im Quellcode werden ebenfalls als „NODE“ verschlüsselt, was Aufgaben erschwert, die Kenntnisse über bestimmte Bibliotheken erfordern.
* **❌ Beispiel für schwache Anweisungen**: „Fügen Sie die Möglichkeit hinzu, Dateien auf AWS S3 hochzuladen.“
* **Grund**: LLM weiß nicht, welche externen Bibliotheken der aktuelle Code verwendet.

### 3. „Eine völlig neue Funktion von Grund auf“ schreiben
Gatekeeper ist äußerst leistungsfähig beim „Patchen und Modifizieren bestehender Strukturen (AST)“, aber es ist schwach darin, „große neue Features zu erstellen, die sowohl eine Bedeutung (U-Achse) als auch eine Struktur aus einer leeren Tafel haben“.

### 4. Verschlechterung der Schlussfolgerung aufgrund der Ineffektivität des „vorher erlernten Wissens“ über LLM selbst
LLMs wie Gemma und Claude sind durch das Studium von Quellcode aus der ganzen Welt schlauer geworden, aber das Format, das Verantyx sendet, ist „ein Graph aus reinen Symbolen und Hashes, wie es keine andere Sprache auf der Welt gibt.“
* **Grund**: Da die Spezialität von LLM, die „Mustererkennung aus dem Codekontext“, blockiert ist, wird es zu einem schwierigen mathematischen Diagrammrätsel, das Sie noch nie zuvor gesehen haben, was zu einem Anstieg der Berechnungskosten führt.

### 💡 Wie überwindest du es? (Zukunftsausblick)
Derzeit implementiert Verantyx eine Kombination aus „Tri-Layer JCross Memory“ und **Visual Anchors, um diese Schwächen zu beheben. Wir verfolgen einen Ansatz, bei dem dem LLM teilweise nur sichere Metadaten, die keine sensiblen Informationen enthalten, als visuelle Anker präsentiert werden, die Hinweise geben und gleichzeitig die Sicherheit wahren.

---

## 📽️ Demovideo und Codekonvertierung in Aktion

<p align="center">
  <img src="demo.gif" alt="Verantyx Gatekeeper Demo" width="49%" style="border-radius: 8px;">
  <video src="https://github.com/verantyx/verantyx/releases/download/v1.2.5/demo_skill_generation.mov" Controls="controls" muted="muted" width="49%" style="border-radius: 8px;"></video>
</p>

### Vorher und Nachher: Verschleierung in Aktion

**[Vorher] Rohquellcode (lokale Umgebung)**
„Python
json importieren
Betriebssystem importieren
Shutil importieren
Importanfragen
Unterprozess importieren
Import bzgl
aus tqdm tqdm importieren
Importsystem

# Importieren Sie unseren neuen Parser
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
aus verantyx.cross_engine.jcross_extraction_parser JCrossExtractionParser importieren

ORACLE_FILE = „/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_m_cleaned.json“
TARGET_DIR = „/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v7“
QUERY_BIN = „/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/release/examples/query_jcross“
MODEL = "gemma4:e2b"
OLLAMA_URL = "http://localhost:11434/api/generate"

FINAL_REPORT = „/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/official_v7_1_accuracy_report.json“
````

**[Nach] Gatekeeper JCross Opaque Topology (an Cloud LLM gesendet)**
„Lispeln.“
;;; 🛡️ GATEKEEPER-MODUS – JCross IR-Ansicht
;;; Echte Identifikatoren wurden durch Knoten-IDs ersetzt.
;;; Schema: D59144D1-BE1
;;; Knoten: 124 | Geschwärzte Geheimnisse: 3442
;;; Quelle: cortex/bench_v7_1_puzzle_runner.py
;;;
// JCROSS_6AXIS_BEGIN
// lang:swift doc:0xD5E025

// ── KNOTEN DER OBEREN EBENE
  NODE[0x7995] Art: undurchsichtig TYP: undurchsichtig MEM: undurchsichtig HASH: 0xb4af0a52 ARITY: class.multiway
  NODE[0x9DB8] Art: undurchsichtig TYP: undurchsichtig MEM: undurchsichtig HASH: 0x504933fd ARITY: class.standard
  NODE[0x627F] Art: undurchsichtig TYP: undurchsichtig MEM: undurchsichtig HASH: 0x97b540cb ARITY: class.multiway
  NODE[0x7F4C] Art: undurchsichtig TYP: undurchsichtig MEM: undurchsichtig HASH: 0x86742e8c ARITY: class.standard
  NODE[0xC79E] Art: undurchsichtig TYP: undurchsichtig MEM: undurchsichtig HASH: 0xd42206c4 ARITY: class.standard
  NODE[0x510B] Art: undurchsichtig TYPE: undurchsichtig MEM: undurchsichtig HASH: 0x14b9be4e ARITY: class.nullary
  NODE[0xB5C0] Art: undurchsichtig TYP: undurchsichtig MEM: undurchsichtig HASH: 0xcacb18a2 ARITY: class.standard
// _TOKEN_匶:0.2___jcross_BM_505__ [decoy-metadata]
  NODE[0xE3CF] Art: undurchsichtig TYP: undurchsichtig MEM: undurchsichtig HASH: 0x375a5480
````

---

## 💻 Installationsmethode (aus dem Quellcode erstellen)

**Anforderungen:**
- macOS 14.0 oder höher (Apple Silicon dringend empfohlen)
- Xcode 15.0 oder höher

„Bash
Git-Klon https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
Öffnen Sie Verantyx.xcodeproj
# Wählen Sie das Verantyx-Schema aus und drücken Sie Cmd+R, um es zu erstellen und auszuführen
````

*Hinweis: Windows/Linux-Portierungen (Rust Core + llama.cpp) stehen auf der langfristigen Roadmap, aber wir konzentrieren uns derzeit stark auf die Fertigstellung der nativen macOS/MLX-Architektur. *

---

## 🔧 Über Repository-Einstellungen und -Verlauf

**Hinweis zu Git-Einstellungen:**
Frühe Commits für dieses Repository erfolgten unter dem lokalen Git-Namen „kofdai“, abgeleitet vom macOS-Benutzernamen des Entwicklers. Dieses Problem wurde am 24. Mai 2026 behoben und alle Commits werden nun korrekt „@Ag3497120“ zugeordnet. Dies ist ein häufiges Problem beim Einrichten Ihrer Entwicklungsumgebung und wird nicht durch einen Bot oder ein automatisiertes Tool verursacht. Alle zukünftigen Beiträge werden mit dem korrekten Autorennamen erfasst.

---

## 💡 Fragen und Antworten und Einspruch (experimentelle Funktionen)

Derzeit können Sie den **Verantyx Agent** starten, indem Sie dreimal die „Strg“-Taste drücken.

<p align="center">
  <img src="assets/verantyx_agent_v2.png" alt="Verantyx Agent Interface" width="600" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
</p>

Dieser Modus wurde als Testgelände für die verschiedenen IDE-Modi früherer Anwendungen erstellt. Um das gesamte Projekt zu überprüfen und uns auf den wirklich benötigten „Gatekeeper-Modus“ zu konzentrieren, haben wir die experimentellen Funktionen für das Agentenverhalten, die wir bisher erstellt haben, in **Verantyx Agent** konsolidiert.

Die wichtigsten in früheren Versionen enthaltenen Agentenfunktionen sind:

* **Dual-Twin-Auditsystem**: Um das Problem zu verhindern, dass KI Tools aufruft und fahrlässig handelt, haben wir einen Mechanismus eingeführt, bei dem TwinB die Gültigkeit der Tool-Aufrufe von TwinA prüft, indem es JCross intern einfügt.
* **Einführung von Visual Anchor**: Wir sind von der Steuerung von Fähigkeiten und Anweisungen nur mit Eingabeaufforderungen zu einer Hybridmethode aus Bildinjektion und Eingabeaufforderungen mithilfe von Visual Anchor übergegangen.
* **Erstellung der L3.5-Betriebssystem-Asset-Map**: Im mit Control×3 gestarteten Agenten wird die interne Computer-Map namens „L3.5“ nur lokal verwaltet. Wir haben den Agenten das Bewusstsein vermittelt, dass die Vermögenswerte auf ihren Computern mit ihrer eigenen Intelligenz verbunden sind.
* **Hochpräzise GUI-Bedienung mithilfe der AX-API**: Wir sind von der bestehenden GUI-Bedienung mithilfe der Bildschirmaufzeichnung zu einer zuverlässigen und hochpräzisen Bedienung mithilfe des OS-API-Baums (Barrierefreiheits-API) übergegangen.
* **Kanji-Topologiekomprimierung**: Wenn Sie eine L3.5-Karte in einen Kontext einfügen, generieren Sie ein Bild und verwenden Sie es als Eingabeaufforderung, um zu verhindern, dass der Kontext aufgebläht wird. Indem wir den tatsächlichen Daten ein einzigartiges Komprimierungsformat namens „Kanji Topology“ zuordnen, stellen wir sicher, dass nur die erforderlichen Daten entsprechend eingefügt werden.
* **Erweiterung des Agentenmodus**: Zwei Typen hinzugefügt: „Automatischer Modus“ und „Erweiterter Modus“.
* **Interner Wissensprioritätsmodus**: Für Power-User, die Restriktionsentfernungsmodelle verwenden, haben wir einen Modus implementiert, der es ihnen ermöglicht, die lokale KI nicht nur als Orchestrator, sondern auch als wichtigstes Denkmodell und Wissensquelle vollständig zu nutzen.
* **L3.5-dedizierte Speicherzeile**: Um zu verhindern, dass der L3.5-Kartenspeicher komplex und groß wird, haben wir eine Speicherzeile erstellt, die vollständig vom normalen Konversationsspeicher getrennt ist.
* **Anwendung zur Feinabstimmung**: Wir haben eine Funktion implementiert, die als Grundlage zum Extrahieren von Benutzeridentitätsdaten aus Speichern von L1 bis L3.5 und zur Feinabstimmung an jedem Modell verwendet werden kann (wodurch eine Optimierung erreicht wird, die mit einem Speichersystem allein nicht möglich ist).
* **Übernahme der FAR-Zonenstruktur**: Basierend auf der Philosophie „Speicher organisieren, ohne sie zu löschen“, haben wir eine Struktur übernommen, die den Übergangsprozess wie das Aufgabenpaket und den Titel aufzeichnet, wenn eine Aufgabe abgeschlossen ist, und sie in einer neuen Ebene namens „FAR-Zone“ ablegt. Dadurch wird sichergestellt, dass wichtige Erinnerungen, wie z. B. der Arbeitsprozess, auch nach Abschluss der Aufgabe erhalten bleiben.

Dies sind nur einige der Funktionen, die derzeit hinzugefügt werden.
Ein kürzlich veröffentlichtes Update führte die Orchestrierung (Blind Commander Architecture) mit einer teilweise quantisierten Version von „talkie-1930:13b“ ein, die auf HuggingFace veröffentlicht wurde. Wir nutzen die Einschränkung, „nur über Wissen aus dem Jahr 1930 zu verfügen“, nutzen einen regelbasierten Vermittler zur Ausführung von Befehlen und haben die Aufgabe, die Botschaft des Benutzers in bildliche Ausdrücke der Zeit umzuwandeln. Es werden zusätzliche Funktionen hinzugefügt, die die „experimentelle“ Philosophie des Projekts verkörpern.

### 🔄 Zukünftiger Fahrplan und übergroße Herausforderungen

Dieser Agent- und Gatekeeper-Modus sind derzeit im selben Speicherbereich verbunden, wir planen jedoch, in Zukunft eine Funktion zu implementieren, die eine Trennung und Feinabstimmung ermöglicht.

Derzeit hat diese Agentenentwicklung einen vorläufigen Meilenstein erreicht. Da ich selbst Student bin, möchte ich mit der umfassenden Entwicklung des „Gatekeeper-Modus“ beginnen, an dem ich derzeit als Verbesserungsplan arbeite, sobald dieser Agent in der Lage ist, die in Teams usw. gegebenen Aufgaben vollständig zu bewältigen (Aufgaben wie „Erstellen und Senden der neuesten 〇〇-Aufgaben“). Vielen Dank an alle, die einen Stern gegeben haben. Bitte warten Sie eine Weile.

Abschließend möchte ich noch auf die übergroße Herausforderung eingehen, die wir als Abschluss dieses Projekts vorbereitet haben.

1. **Portierung auf die Windows-Version (Rust-basiert)**: Diese Aufgabe besteht darin, die derzeit in der Swift-Sprache für macOS geschriebene Implementierung auf Rust-basiert umzuschreiben, damit auch Windows-Benutzer die gleiche Gatekeeper-Funktion nutzen können.
2. **Vollständige Abkehr von der Cloud-Abhängigkeit**: Sich zu einem Agenten entwickeln, der die Entwicklung autonom fortsetzen kann, indem er nur lokales LLM verwendet, ohne teure API-Gebühren zu zahlen. Wir möchten ein 20B-Klassenmodell verwenden, das auf einem MacBook läuft (wie das aktuelle „qwen3.6:27b“, das unter bestimmten Bedingungen mit dem High-End-Modell vergleichbar sein soll), einen Codierungsagenten nahe der Cloud-Ebene betreiben und das Projekt durch autonome Verbesserungen vorantreiben.