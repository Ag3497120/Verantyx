<div align="center">
  <h1>🛡️ Verantyx (Überprüfbare und überprüfbare KI-Engine)</h1>
  <p><b>Das Zero-Leakage, Neuro-Symbolic AI Coding Gateway und die native macOS IDE</b></p>

<p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="Version 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README.md">Englisch</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brasilien)</a> · <a href="README-de.md">Deutsch</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">Vereinfachtes Chinesisch</a> · <a href="README-zh-TW.md">Traditionelles Chinesisch</a> · <a href="README-ko.md">한국어</a> · <a href="README-ja.md">Japanisch</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Russisch</a> · <a href="README-uk.md">Türkisch</a> · <a href="README-tr.md">Türkisch</a>
  </p>
</div>

---

Verantyx ist eine neurosymbolische Logik-Engine der nächsten Generation, die die KI-gestützte Softwareentwicklung vollständig kontrollierbar und sicher macht.
Wir bieten zwei verschiedene Frontends auf einer leistungsstarken Kern-Engine (JCross/L3.5 Memory) an. Bitte wählen Sie entsprechend Ihrem Verwendungszweck.

---

## 1. 🖥️ Verantyx Gatekeeper (IDE-Modus)
**„Ich möchte, dass das Cloud-LLM den vertraulichen Code meines Unternehmens sicher liest“**

Der Gatekeeper-Modus ist die ultimative sichere IDE, die Ihren Quellcode in bedeutungslose mathematische Rätsel (undurchsichtige Topologie) verschleiert, bevor er ihn an die KI weitergibt.
👉 [Klicken Sie hier für Details zum Gatekeeper-Modus und Verschleierungsmechanismus (README-Gatekeeper.md)](./docs/README-Gatekeeper.md)

## 2. ⚡ Verantyx Agent (Spotlight-Modus)
**„Ich möchte die leistungsfähigste lokale KI als Erweiterung meines Gehirns voll ausnutzen“**

Es handelt sich um einen hyperautonomen Agenten, der durch einfaches dreimaliges Drücken der „Strg“-Taste aktiviert werden kann. Es ist mit internem Auditing mithilfe von Dual Twin, physischer Blockierung von Halluzinationen mithilfe der Metapher von 1930 und einer Denkmaschine der nächsten Generation ausgestattet, die PC-Assets als „Ihre eigenen Erinnerungen (L3.5)“ erkennt.
👉 [Klicken Sie hier für Details und Architektur des Agent-Modus (README-Agent.md)](./docs/README-Agent.md)

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

## 📖 Über Verantyx

Als ich für dieses Projekt zuvor versuchte, eine regelbasierte symbolische KI zu erstellen, wurde mir klar, dass es unmöglich sein würde, sie selbst zu erstellen, also beschloss ich, sie zu steuern, indem ich die Teile erstellte, die ich selbst kontrollierte, wie zum Beispiel den Geschirrteil der derzeit gängigen KI. (Zu dieser Zeit erregte Openclaw Aufmerksamkeit)
Von dort aus begann ich mit der Entwicklung dieses Projekts, weil ich dachte, dass es möglich wäre, Informationslecks zu verhindern, indem der Quellcode und die Benutzeranfragen in einem rätselhaften Zustand verschleiert werden, bevor sie an die Hochleistungs-KI in der Cloud übergeben werden.

Der Grund, warum dieses Projekt 0 Sterne hat, liegt darin, dass es einen sicheren Ordner enthielt und ich es plötzlich zu einem privaten Repository gemacht habe, sodass die 9 Sterne verschwunden sind. Vielen Dank für Ihre anhaltende Unterstützung, da ich mich vollständig erholt habe. Ich habe Teile aussortiert, die sich mit anderen Repositories zu überschneiden scheinen. Ich habe hauptsächlich Veröffentlichungen in diesem Repository vorangetrieben, aber ich habe festgestellt, dass die Aktualisierung des Quellcodes verzögert war, und habe sie aktualisiert.

Von nun an denke ich darüber nach, mich auf Japanisch, meine Muttersprache, zu konzentrieren und Englisch mit einem normalen Übersetzungstool zu übersetzen und es für alle Fälle zu veröffentlichen.

---

## 🔧 Über Repository-Einstellungen und -Verlauf

**Hinweis zu Git-Einstellungen:**
Frühe Commits für dieses Repository erfolgten unter dem lokalen Git-Namen „kofdai“, abgeleitet vom macOS-Benutzernamen des Entwicklers. Dieses Problem wurde am 24. Mai 2026 behoben und alle Commits werden nun korrekt „@Ag3497120“ zugeordnet. Dies ist ein häufiges Problem beim Einrichten Ihrer Entwicklungsumgebung und wird nicht durch einen Bot oder ein automatisiertes Tool verursacht. Alle zukünftigen Beiträge werden mit dem korrekten Autorennamen erfasst.