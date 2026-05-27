<div align="centro">
  <h1>🛡️ Verantyx (motor de IA verificable y auditable)</h1>
  <p><b>La puerta de enlace de codificación de IA neurosimbólica y sin fugas y el IDE nativo de macOS</b></p>

<p>
    <a href="https://github.com/verantyx/verantyx/releases/latest"><img src="https://img.shields.io/badge/version-1.4.0-blue?style=flat-square" alt="Versión 1.4.0"></a>
    <img src="https://img.shields.io/badge/platform-macOS%2014%2B-lightgrey?style=flat-square">
    <img src="https://img.shields.io/badge/Apple%20Silicon-optimized-orange?style=flat-square">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  </p>
  <p>
    <a href="README-en.md">English</a> · <a href="README-es.md">Español</a> · <a href="README-pt-BR.md">Português (Brasil)</a> · <a href="README-de.md">Deutsch</a> · <a href="README-fr.md">Français</a> · <a href="README-zh-CN.md">chino simplificado</a> · <a href="README-zh-TW.md">chino tradicional</a> · <a href="README-ko.md">한국어</a> · <a href="README.md">japonés</a> · <a href="README-ar.md">العربية</a> · <a href="README-ru.md">Русский</a> · <a href="README-uk.md">Українська</a> · <a href="README-tr.md">Türkçe</a>
  </p>
</div>

---

Verantyx es un motor lógico neurosimbólico de próxima generación que hace que el desarrollo de software impulsado por IA sea totalmente controlable y seguro.
Ofrecemos dos interfaces diferentes además de un potente motor central (memoria JCross/L3.5). Elija según su propósito.

---

## 1. 🖥️ Verantyx Gatekeeper (modo IDE)
**"Quiero que Cloud LLM lea el código confidencial de mi empresa de forma segura"**

El modo Gatekeeper es el IDE seguro definitivo que confunde su código fuente en acertijos matemáticos sin sentido (topología opaca) antes de pasarlo a la IA.
👉 [Haga clic aquí para obtener detalles sobre el modo Gatekeeper y el mecanismo de ofuscación (README-Gatekeeper.md)](./docs/README-Gatekeeper.md)

## 2. ⚡ Agente Verantyx (Modo Destacado)
**“Quiero utilizar plenamente la IA local más poderosa como una extensión de mi cerebro”**

Es un agente hiperautónomo que se puede activar simplemente presionando tres veces la tecla `Control`. Está equipado con auditoría interna mediante Dual Twin, bloqueo físico de alucinaciones utilizando la metáfora de 1930 y un motor de pensamiento de próxima generación que reconoce los activos de la PC como "tus propios recuerdos (L3.5)".
👉 [Haga clic aquí para obtener detalles y arquitectura del modo Agente (README-Agent.md)](./docs/README-Agent.md)

---

## 💻 Método de instalación (compilación desde la fuente)

**Requisitos:**
- macOS 14.0 o posterior (se recomienda Apple Silicon)
- Xcode 15.0 o posterior

```golpecito
clon de git https://github.com/Ag3497120/Verantyx.git
cd Verantyx/cli/VerantyxIDE
abrir Verantyx.xcodeproj
# Seleccione el esquema Verantyx y presione Cmd+R para compilar y ejecutar
````

*Nota: Las adaptaciones de Windows/Linux (Rust core + llama.cpp) están en la hoja de ruta a largo plazo, pero actualmente estamos extremadamente concentrados en completar la arquitectura nativa de macOS/MLX. *

---

## 📖 Acerca de Verantyx

Para este proyecto, cuando anteriormente estaba intentando crear una IA simbólica basada en reglas, me di cuenta de que sería imposible crearla por mí mismo, así que decidí controlarla creando las partes que controlo yo mismo, como la parte del arnés de la IA actualmente convencional. (En ese momento, openclaw estaba llamando la atención)
A partir de ahí, comencé a desarrollar este proyecto porque pensé que sería posible evitar fugas de información ofuscando el código fuente y las solicitudes de los usuarios en un estado similar a un rompecabezas antes de pasarlos a la IA de alto rendimiento en la nube.

La razón por la que este proyecto tiene 0 estrellas es porque contenía una carpeta segura y de repente lo convertí en un repositorio privado, por lo que las 9 estrellas desaparecieron. Gracias por su continuo apoyo ya que me he recuperado por completo. He ordenado partes que parecen superponerse con otros repositorios. Principalmente estaba impulsando lanzamientos en este repositorio, pero descubrí que la actualización del código fuente se retrasó y lo actualicé.

De ahora en adelante, estoy pensando en centrarme en el japonés, mi lengua materna, y traducir el inglés usando una herramienta de traducción normal y publicarlo por si acaso.

---

## 🔧 Acerca de la configuración y el historial del repositorio

**Aviso sobre la configuración de Git:**
Las primeras confirmaciones para este repositorio se realizaron bajo el nombre local de Git "kofdai", derivado del nombre de usuario de macOS del desarrollador. Este problema se solucionó el 24 de mayo de 2026 y todas las confirmaciones ahora se atribuyen correctamente a `@Ag3497120`. Este es un problema común al configurar su entorno de desarrollo y no es causado por un bot o una herramienta automatizada. Todas las contribuciones futuras se registrarán con el nombre correcto del autor.