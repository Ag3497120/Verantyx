<div align="centro">
  <h1>🛡️ Verantyx IDE y motor Cortex</h1>
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

## 📖 Acerca de Verantyx

Para este proyecto, cuando anteriormente estaba intentando crear una IA simbólica basada en reglas, me di cuenta de que sería imposible crearla por mí mismo, así que decidí controlarla creando las partes que controlo yo mismo, como la parte del arnés de la IA actualmente convencional. (En ese momento, openclaw estaba llamando la atención)
A partir de ahí, comencé a desarrollar este proyecto porque pensé que sería posible evitar fugas de información ofuscando el código fuente y las solicitudes de los usuarios en un estado similar a un rompecabezas antes de pasarlos a la IA de alto rendimiento en la nube.

La razón por la que este proyecto tiene 0 estrellas es porque contenía una carpeta segura y de repente lo convertí en un repositorio privado, por lo que las 9 estrellas desaparecieron. Gracias por su continuo apoyo ya que me he recuperado por completo. He ordenado partes que parecen superponerse con otros repositorios. Principalmente estaba impulsando lanzamientos en este repositorio, pero descubrí que la actualización del código fuente se retrasó y lo actualicé.

De ahora en adelante, estoy pensando en centrarme en el japonés, mi lengua materna, y traducir el inglés usando una herramienta de traducción normal y publicarlo por si acaso.

## 🔐 Ofuscación y estructura cruzada 3D de 6 ejes

La idea detrás de ofuscar este proyecto es utilizar un método de gestión de datos basado en la estructura cruzada tridimensional que se encuentra en Axis, el predecesor de verantyx, que se creó en los primeros días como una imagen de cómo pasar datos.

### 🧩 Definición de 6 dimensiones (Eje)

| Eje | Nombre | Rol / Elementos extraídos |
| :--- | :--- | :--- |
| **Eje X** | **Control de flujo** | Eje tiempo y orden. Ramas `if`, bucles `for`, manejo de excepciones, etc. |
| **Eje Y** | **Flujo de datos** | Eje de dependencia. Asignación de variables, paso de argumentos, etc. |
| **Eje Z** | **Restricciones de tipo** | Eje límite. Definiciones de clases, anotaciones de tipos, genéricos, etc. |
| **Eje W** | **Ciclo de vida de la memoria** | Eje de la vida. Duración del alcance, asignación/liberación de memoria. |
| **Eje V** | **Jerarquía de alcance** | Eje de inclusión. Módulo, estructura de anidamiento de clases. |
| **Eje U** | **Semántica y significado** | **★Más importante★ Eje de intención de negocio. Nombres de variables concretos, nombres de funciones, cadenas sin formato y números. ** |

El proceso de conversión se realiza instantáneamente localmente en su MacBook mediante el **Gatekeeper Engine** de Verantyx.

---

### 🔄 Mecanismo de conversión de código sin formato a topología opaca

#### Paso 1: análisis y descomposición en AST (árbol de sintaxis abstracta)
Primero, el motor Gatekeeper (se recomienda basado en reglas) analiza el código fuente de destino y convierte la estructura del programa en datos estructurados en árbol llamados AST (árbol de sintaxis abstracta).
En este punto, toda la información todavía está incluida, como "qué función llama a qué", "¿cuáles son los nombres de las variables y qué se define como una cadena?"

#### Paso 2: "Separación física y aislamiento" de la semántica (eje U)
Aquí es donde brilla Verantyx. Elimine físicamente toda la **información que indique el significado (intención) del negocio = eje U** del AST.

* **Cosas que se eliminan (eje U)**: nombres de variables, nombres de funciones, cadenas, números fijos, etc.
* **Lo que queda (ejes X, Y, Z, W, V)**: el marco lógico de ``asignar una variable'', ``llamar a una función'', ``ramificarse con una declaración if'' y ``hacer un bucle con una declaración for''.

Los datos de cadena y nombre específicos eliminados se almacenan de forma local de forma segura en **`JCrossIRVault` (bóveda)** de tu Mac y nunca se envían al exterior.

#### Paso 3: Totalmente cifrado en el nodo opaco
Los "huesos" restantes, despojados de significado, se transforman en una representación totalmente opaca para enviar a la nube LLM.

* **`NODE[0x...]` (ID de nodo)**: Todas las variables y elementos de sintaxis se reemplazan con identificadores, como direcciones de memoria aleatorias.
* **`ARITY` (aridad/número de términos)**:
    * `class.nullary`: Un elemento sin argumentos ni contenido (solo un valor o un nodo terminal).
    * `class.standard`: Operaciones unarias y binarias estándar (A+B, asignación, etc.).
    * `class.multiway`: Estructuras complejas con múltiples elementos (bucles for, ramas if-else, definiciones de funciones, etc.).
* **`HASH` (Hash estructural)**: una suma de comprobación que muestra dónde está el nodo en el gráfico y cómo está conectado con su entorno. Esto le permite verificar localmente que la estructura no esté rota cuando LLM resuelve el rompecabezas y lo devuelve.

Incluso la declaración del código original desaparece y se convierte en un gráfico matemático puro: los nodos `class.multiway` iteran sobre sus nodos secundarios.''

#### Paso 4: Inyectar “señuelos” para evitar la inferencia estadística
Si envía su código en una estructura gráfica a una parte externa, existe el riesgo de que la IA avanzada o atacantes maliciosos infieran estadísticamente (ingeniería inversa) que la forma de este gráfico es la forma de un script común.

Para evitar esto, inyectamos aleatoriamente **nodos falsos (señuelos)** en los espacios del gráfico.
```texto
// _TOKEN_匶:0.2___jcross_BM_505__ [metadatos-señuelo]
````
Al mezclar estos tokens Kanji sin sentido y conexiones ficticias, la forma misma del gráfico se distorsiona, lo que hace matemáticamente imposible que la IA externa deduzca la verdadera identidad del código fuente original.

---

### 🧩 ¿Cómo “soluciona” esto el LLM? (Proceso de restauración)

1. **Resuelve como un rompecabezas**:
   Sin conocer el código original, LLM infiere el valor del cambio objetivo a partir del contexto indicado y la forma del gráfico (conexiones ARITY y HASH).
2. **Devolución del parche estructural**:
   LLM solo devuelve parches estructurales (GraphPatch) en formato JSON que reescriben el contenido.
3. **Transpilación inversa local**:
   El motor Gatekeeper de Mac recibe el parche y reinyecta el nombre real de la variable y la cadena (eje U) que estaban ocultos anteriormente en `JCrossIRVault` en el parche.

Como resultado, se logra una experiencia de desarrollo mágica sin fugas de información, donde "Aunque la IA externa no ha visto ni comprendido ni una sola línea del código original, cuando regresa al código local, el código se ha reescrito correctamente".** *Puede haber fugas de información que he pasado por alto, así que si nota alguna, háganoslo saber a través del problema.

---

## ⚠️ Tareas que actualmente no puedo realizar (no soy bueno en)

Actualmente, esta estructura no puede manejar tareas como **Reescribir de Swift a Rust**, que suele ser la tarea más débil. Además, las tareas 1 a 4 siguientes me resultan difíciles.

### 1. Refactorizaciones y correcciones de errores que dependen de la “semántica (conocimiento del dominio)”
Dado que el LLM externo sólo ve el esqueleto de `NODE[0x...]`, no puede abordar ``problemas que no se pueden resolver sin comprender el significado del código''.
* **❌ Ejemplo de instrucción débil**: "Agregue el prefijo `auth_` a los nombres de todas las variables relacionadas con la autenticación".
* **Motivo**: LLM no tiene visibilidad sobre "qué proceso de autenticación".

### 2. Adición de nuevas funciones que dependen en gran medida de bibliotecas externas (API)
Todas las declaraciones de "importación" y llamadas a bibliotecas en el código fuente también están cifradas como "NODO", lo que dificulta las tareas que requieren conocimiento de bibliotecas específicas.
* **❌ Ejemplo de instrucciones débiles**: "Agregue la capacidad de cargar archivos a AWS S3"
* **Razón**: LLM no sabe qué bibliotecas externas está utilizando el código actual.

### 3. Escribir "una característica completamente nueva desde cero"
Gatekeeper es extremadamente poderoso para "parchear y modificar estructuras existentes (AST)", pero es débil para "crear enormes características nuevas que tienen significado (eje U) y estructura a partir de una pizarra en blanco".

### 4. Deterioro de la inferencia debido a la ineficacia del “conocimiento previo aprendido” del propio LLM
LLM como Gemma y Claude se han vuelto más inteligentes al estudiar el código fuente de todo el mundo, pero el formato que envía Verantyx es "un gráfico de símbolos puros y hashes como ningún otro lenguaje en el mundo".
* **Razón**: debido a que la especialidad de LLM, "reconocimiento de patrones a partir del contexto del código", está bloqueada, se convierte en un difícil rompecabezas de gráficos matemáticos que nunca antes había visto, lo que provoca un aumento en los costos de cálculo.

### 💡 ¿Cómo lo estás superando? (Perspectivas de futuro)
Actualmente, Verantyx está implementando una combinación de ``Memoria JCross de tres capas'' y **Visual Anchors para superar estas debilidades. Adoptamos un enfoque en el que solo los metadatos seguros que no contienen información confidencial se presentan parcialmente a LLM como anclajes visuales, brindando sugerencias mientras se mantiene la seguridad.

---

## 📽️ Video de demostración y conversión de código en acción

<p align="centro">
  <img src="demo.gif" alt="Demostración de Verantyx Gatekeeper" width="49%" style="border-radius: 8px;">
  <video src="https://github.com/verantyx/verantyx/releases/download/v1.2.5/demo_skill_generación.mov" controles="controls" muted="silenciado" width="49%" style="border-radius: 8px;"></video>
</p>

### Antes y después: la ofuscación en acción

**[Antes] Código fuente sin formato (entorno local)**
```pitón
importar json
importar sistema operativo
importar Shuil
solicitudes de importación
subproceso de importación
importar re
desde tqdm importar tqdm
sistema de importación

# Importar nuestro nuevo analizador
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
desde verantyx.cross_engine.jcross_extraction_parser importar JCrossExtractionParser

ORACLE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_m_cleaned.json"
TARGET_DIR = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v7"
QUERY_BIN = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/target/release/examples/query_jcross"
MODELO = "gemma4:e2b"
OLLAMA_URL = "http://localhost:11434/api/generate"

FINAL_REPORT = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/official_v7_1_accuracy_report.json"
````

**[Después] Topología opaca Gatekeeper JCross (enviada a Cloud LLM)**
```ceceo
;;; 🛡️ MODO PORTERO - Vista JCross IR
;;; Los identificadores reales han sido reemplazados por ID de nodo.
;;; Esquema: D59144D1-BE1
;;; Nodos: 124 | Secretos redactados: 3442
;;; Fuente: corteza/bench_v7_1_puzzle_runner.py
;;;
// JCROSS_6AXIS_BEGIN
// idioma:swift doc:0xD5E025

// ── NODOS DE NIVEL SUPERIOR
  NODO[0x7995] tipo:opaco TIPO:opaco MEM:opaco HASH:0xb4af0a52 ARITY:class.multiway
  NODO[0x9DB8] tipo:opaco TIPO:opaco MEM:opaco HASH:0x504933fd ARITY:class.standard
  NODO[0x627F] tipo:opaco TIPO:opaco MEM:opaco HASH:0x97b540cb ARITY:class.multiway
  NODO[0x7F4C] tipo:opaco TIPO:opaco MEM:opaco HASH:0x86742e8c ARITY:clase.estándar
  NODO[0xC79E] tipo:opaco TIPO:opaco MEM:opaco HASH:0xd42206c4 ARITY:clase.estándar
  NODO[0x510B] tipo:opaco TIPO:opaco MEM:opaco HASH:0x14b9be4e ARITY:class.nullary
  NODO[0xB5C0] tipo:opaco TIPO:opaco MEM:opaco HASH:0xcacb18a2 ARITY:clase.estándar
// _TOKEN_匶:0.2___jcross_BM_505__ [metadatos-señuelo]
  NODO[0xE3CF] tipo:opaco TIPO:opaco MEM:opaco HASH:0x375a5480
````

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

## 🔧 Acerca de la configuración y el historial del repositorio

**Aviso sobre la configuración de Git:**
Las primeras confirmaciones para este repositorio se realizaron bajo el nombre local de Git "kofdai", derivado del nombre de usuario de macOS del desarrollador. Este problema se solucionó el 24 de mayo de 2026 y todas las confirmaciones ahora se atribuyen correctamente a `@Ag3497120`. Este es un problema común al configurar su entorno de desarrollo y no es causado por un bot o una herramienta automatizada. Todas las contribuciones futuras se registrarán con el nombre correcto del autor.

---

## 💡 Preguntas y respuestas y apelación (funciones experimentales)

Actualmente, puede iniciar **Verantyx Agent** presionando la tecla "Control" tres veces.

<p align="centro">
  <img src="assets/verantyx_agent_v2.png" alt="Interfaz del agente Verantyx" width="600" style="border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
</p>

Este modo se creó como campo de pruebas para los distintos modos IDE que se encuentran en aplicaciones anteriores. Para revisar todo el proyecto y centrarnos en el "modo guardián" que realmente se necesita, hemos consolidado las funciones experimentales para el comportamiento del agente que hemos creado hasta ahora en **Verantyx Agent**.

Las principales características del agente incluidas en versiones anteriores son:

* **Sistema de auditoría Dual Twin**: para evitar el problema de las herramientas de llamada de IA y la negligencia, hemos introducido un mecanismo en el que TwinB audita la validez de las llamadas a herramientas de TwinA inyectando JCross internamente.
* **Introducción de Visual Anchor**: Pasamos de controlar habilidades e instrucciones solo con indicaciones a un método híbrido de inyección de imágenes e indicaciones utilizando Visual Anchor.
* **Construcción del mapa de activos del sistema operativo L3.5**: En el agente iniciado con Control×3, el mapa interno de la computadora llamado "L3.5" se mantiene solo localmente. Inculcamos a los agentes la conciencia de que los activos de sus computadoras están conectados a su propia inteligencia.
* **Operación GUI de alta precisión usando AX API**: Hemos pasado de la operación GUI existente usando grabación de pantalla a una operación confiable y de alta precisión usando el árbol API del sistema operativo (API de accesibilidad).
* **Compresión de topología kanji**: al inyectar un mapa L3.5 en un contexto, genere una imagen y utilícela como mensaje para evitar que el contexto se hinche. Al asociar un formato de compresión único llamado "Topología Kanji" con datos reales, nos aseguramos de que solo se inserten los datos necesarios según corresponda.
* **Expansión del modo agente**: Se agregaron dos tipos: "Modo automático" y "Modo avanzado".
* **Modo de prioridad de conocimiento interno**: para los usuarios avanzados que utilizan modelos de eliminación de restricciones, hemos implementado un modo que les permite utilizar plenamente la IA local no solo como orquestador sino también como principal modelo de pensamiento y fuente de conocimiento.
* **Línea de memoria dedicada L3.5**: Para evitar que la memoria del mapa L3.5 se vuelva compleja y grande, hemos creado una línea de memoria que está completamente separada de la memoria de conversación normal.
* **Aplicación al ajuste fino**: Hemos implementado una función que se puede utilizar como punto de apoyo para extraer datos de identidad del usuario de las memorias de L1 a L3.5 y realizar ajustes finos en cualquier modelo (logrando una optimización que no es posible con un sistema de memoria solo).
* **Adopción de la estructura de zona FAR**: Basado en la filosofía de "organizar recuerdos sin eliminarlos", hemos adoptado una estructura que registra el proceso de transición, como el paquete de tareas y el título, cuando se completa una tarea, y lo coloca en una nueva capa llamada "zona FAR". Esto garantiza que los recuerdos importantes, como el proceso de trabajo, se conserven incluso después de finalizar la tarea.

Estas son sólo algunas de las funciones que se están agregando actualmente.
Una actualización reciente introdujo la orquestación (Blind Commander Architecture) utilizando una versión parcialmente cuantificada de `talkie-1930:13b` publicada en HuggingFace. Aprovechando la limitación de "tener sólo conocimientos de 1930", utilizamos un intermediario basado en reglas para ejecutar comandos y tenemos la función de convertir el mensaje del usuario en expresiones figurativas de la época. Se están agregando características adicionales que encarnan la filosofía "experimental" del proyecto.

### 🔄 Hoja de ruta futura y desafíos de gran tamaño

Este modo de agente y guardián están conectados actualmente en la misma área de almacenamiento, pero en el futuro planeamos implementar una función que permitirá separarlos y ajustarlos.

Actualmente, el desarrollo de este agente ha alcanzado un hito temporal. Como soy estudiante, una vez que este agente sea capaz de manejar completamente las tareas asignadas en Teams, etc. (tareas como ``Crear y enviar las tareas 〇〇 más recientes''), me gustaría comenzar el desarrollo a gran escala del ``Modo Gatekeeper'', en el que estoy trabajando actualmente como un plan de mejora. Gracias a todos los que habéis dado una estrella. Espere un momento.

Por último, me gustaría hablaros del gran desafío que tenemos preparado como culminación de este proyecto.

1. **Migración a la versión de Windows (basada en Rust)**: esta tarea consiste en reescribir la implementación escrita actualmente en el lenguaje Swift para macOS a una versión basada en Rust, de modo que los usuarios de Windows también puedan experimentar la misma función de guardián.
2. **Romper completamente con la dependencia de la nube**: convertirse en un agente que pueda continuar el desarrollo de forma autónoma utilizando solo un LLM local sin pagar costosas tarifas de API. Nos gustaría utilizar un modelo de clase 20B que se ejecute en una MacBook (como el reciente `qwen3.6:27b`, que se dice que es comparable al modelo de gama más alta bajo ciertas condiciones), operar un agente de codificación cercano al nivel de la nube y continuar con el proyecto realizando mejoras de forma autónoma.