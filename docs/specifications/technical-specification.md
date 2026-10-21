**Proyecto Integrador**

# Especificación técnica

Visualizador y laboratorio experimental de evaluación lazy

**Proyecto:** Visualizador y laboratorio experimental de evaluación lazy para una minilengua funcional

**Carrera:** Ingeniería en Computación

**Versión:** 1.1 — revisión técnica y editorial

**Fecha:** 9 de octubre de 2026

Este documento fija las decisiones técnicas necesarias para implementar, validar y evaluar la propuesta. Los detalles expresamente señalados como ajustables podrán definirse durante la implementación sin modificar el contrato semántico.

## Contenido

La especificación se organiza en los siguientes bloques.

1. Propósito y alcance

2. Definición de la minilengua

3. Frontend y representaciones

4. Arquitectura del sistema

5. Máquina abstracta y semántica Core

6. Modelo de runtime

7. Garbage collection y análisis de memoria

8. Representación y máquina STG-like

9. Resultado y observación

10. Métricas

11. Validación y tests

12. Diseño experimental

13. Visualizador y experiencia de uso

14. Invariantes y criterios de aceptación

15. Bibliografía inicial

## 1 Propósito y alcance

La Propuesta B define el sistema completo: una minilengua funcional, tres máquinas Core para call-by-value, call-by-name y call-by-need, un runtime instrumentado, garbage collector mark-sweep, análisis pasivo de reachability y lifetime, una representación STG-like ejecutable y un laboratorio de experimentos reproducibles. El visualizador debe explicar tanto las diferencias entre estrategias como la relación entre código fuente, Core, STG, heap y stack.

| **Área** | **Alcance** |
| --- | --- |
| Estrategias | CBV, CBN y CBNeed |
| Memoria | Heap explícito, stack abstracto, GC, reachability y lifetime |
| Representaciones | Surface, Core y STG-like |
| Evaluación | Visualización interactiva y suite E01 a E10 |
| Implementación | Motor Python, FastAPI y React TypeScript |

### Objetivos técnicos

- Definir una semántica small-step determinista que permita inspeccionar cada transición.

- Representar explícitamente entornos, closures, thunks, constructores, stack frames e indirecciones.

- Separar el estado semántico de la instrumentación para impedir que las métricas o la interfaz alteren la ejecución.

- Producir resultados y métricas reproducibles, con unidades y limitaciones documentadas.

- Distinguir validación de la herramienta de los experimentos utilizados para responder preguntas de investigación.

- Mostrar cómo STG vuelve explícitas las clausuras, la demanda y la actualización.

- Estudiar el efecto del GC, la alcanzabilidad y el tiempo de vida de los objetos.

### Principios de diseño

- Una transición representa una sola aplicación de regla, aunque pueda producir varios efectos atómicos relacionados.

- La evaluación es determinista y de izquierda a derecha donde el lenguaje exige un orden.

- El visualizador es pasivo; la única observación activa es la materialización explícita del resultado.

- Las direcciones del heap son ObjectId lógicos, estables y nunca reutilizados.

- Las unidades de memoria son slots abstractos, no bytes de CPython ni del sistema operativo.

- Las comparaciones cuantitativas estrictas se realizan entre ejecuciones dentro del mismo modelo de medición.

## 2 Definición de la minilengua

La minilengua es pura y tiene sintaxis inspirada en Haskell. Incluye enteros arbitrarios, booleanos, listas, funciones de orden superior, recursión mutua y evaluación explícita mediante seq. No incluye IO, concurrencia, excepciones del usuario, typeclasses ni inferencia estática de tipos. Los errores de tipo se detectan cuando se demanda una operación incompatible.

### Construcciones y ejemplo

| **Categoría** | **Construcciones** |
| --- | --- |
| Valores | Enteros, True, False, NIL y CONS |
| Funciones | Lambda, aplicación unaria y parámetros múltiples como azúcar |
| Control | if then else, case de listas, let secuencial y let rec |
| Operadores | Negación, \*, +, -, :, ==, \< y \<= |
| Demanda | seq con exactamente dos argumentos; no es parcialmente aplicable |

```text
map f xs =
  case xs of
    []   -> []
    x:xt -> f x : map f xt
double x = x * 2
main = map double [1, 2, 3]
```

Las definiciones globales forman un grupo mutuamente recursivo. main es una entrada especial, sin parámetros y no referenciable desde expresiones. Debe aparecer exactamente una vez. El programa anterior produce \[2, 4, 6\] cuando se materializa completamente.

### Léxico y precedencia

- identifier es un token ASCII con patrón \[a-z\_\]\[A-Za-z0-9\_'\]\*, excluyendo palabras reservadas y el token aislado \_. integer es una secuencia no vacía de dígitos decimales sin signo. EOF indica fin de archivo.

- Palabras reservadas: main, let, rec, in, if, then, else, case, of, seq, True y False. El token \_ se admite únicamente como patrón comodín.

- Los comentarios de línea comienzan con --. Se rechazan tabulaciones; el layout usa espacios. Se reconoce primero el operador más largo, por ejemplo \<= antes de \< y -\> antes de -.

- La aplicación asocia a izquierda; \*, + y - asocian a izquierda; : asocia a derecha; las comparaciones no se encadenan. La precedencia está fijada por la gramática.

- f (-1) aplica f a un entero negativo; f - 1 es una resta. Los argumentos complejos de una aplicación o de seq se escriben entre paréntesis.

### Gramática completa después del layout

Notación EBNF: las comillas indican terminales, \[X\] una parte opcional y {X} cero o más repeticiones. Todos los no terminales se definen a continuación; identifier, integer y EOF son los tokens léxicos definidos arriba. Las llaves entre comillas son tokens del lenguaje. Dentro de un terminal entre comillas, dos barras invertidas representan una sola barra invertida.

```text
program       ::= "{" definition { ";" definition } [";"] "}" EOF
definition    ::= binding | "main" "=" expression
binding       ::= identifier { identifier } "=" expression
bindingGroup  ::= "{" binding { ";" binding } [";"] "}"
alternativeGroup ::= "{" alternative
                     { ";" alternative } [";"] "}"
alternative   ::= pattern "->" expression
pattern       ::= "[" "]" | identifier ":" identifier | "_"
expression    ::= lambda | letExpr | ifExpr | caseExpr | comparison
lambda        ::= "\\" identifier { identifier } "->" expression
letExpr       ::= "let" ["rec"] bindingGroup "in" expression
ifExpr        ::= "if" expression "then" expression
                  "else" expression
caseExpr      ::= "case" expression "of" alternativeGroup
comparison    ::= consExpr [ compareOp consExpr ]
compareOp     ::= "==" | "<" | "<="
consExpr      ::= sumExpr [ ":" consExpr ]
sumExpr       ::= product { addOp product }
addOp         ::= "+" | "-"
product       ::= unary { "*" unary }
unary         ::= "-" unary | application
application   ::= atom { atom } | "seq" atom atom
atom          ::= integer | "True" | "False" | identifier
                | listLiteral | "(" expression ")"
listLiteral   ::= "[" [ expression { "," expression } ] "]"
```

### Contrato del layout

El parser consume una secuencia con llaves y separadores, explícitos o insertados por la etapa de layout. Un archivo sin llaves exteriores recibe un bloque virtual. Después de let, let rec y of, la columna del primer elemento abre un bloque virtual cuando no hay una llave explícita. Una nueva línea en la misma columna inserta un separador; una dedentación cierra el bloque. Las líneas vacías y los comentarios no producen separadores.

in cierra el bloque virtual del let correspondiente aunque aparezca en la misma línea. EOF cierra los bloques virtuales abiertos. Las continuaciones de un cuerpo deben quedar a mayor indentación que su definición; una indentación incompatible produce un diagnóstico de layout. Las llaves explícitas suspenden la inserción de separadores dentro de ese bloque. No se implementa el algoritmo completo de layout de Haskell.

```text
{ main = let { x = 1 + 2 } in x + x }
```

Esta forma explícita es equivalente a main = let x = 1 + 2 in x + x. Las pruebas del frontend deben cubrir ambas formas y el cierre de un case anidado dentro de un let.

### Alcance de nombres y errores

- El shadowing está permitido. Cada binder recibe un SymbolId único; dos usos del mismo nombre pueden resolver a símbolos diferentes.

- En un let secuencial, un RHS ve los bindings anteriores y el entorno exterior, pero no su propio binder ni los siguientes. En let rec, todos los RHS ven todo el grupo.

- Se rechazan globals duplicados, main ausente o duplicado, parámetros repetidos, binders duplicados en un mismo grupo y patrones h:h. La referencia a un nombre no ligado impide iniciar la ejecución.

- case admite \[\], h:t y \_. Las alternativas se prueban en orden. Un patrón duplicado o posterior a \_ es inalcanzable y genera un diagnóstico; la falta de cobertura se advierte y solo falla si se alcanza un valor sin alternativa.

- La condición de if exige un booleano. Los operadores aritméticos y de orden exigen enteros; == compara enteros o booleanos del mismo tipo. No hay igualdad estructural implícita de listas o funciones.

- Los patrones \[\] y h:t exigen un constructor de lista; \_ acepta cualquier WHNF. Una cola de CONS incompatible produce un error cuando la ejecución o la materialización exige que sea lista; no se fuerza para comprobarla al construirla en una estrategia lazy.

## 3 Frontend y representaciones

```text
SourceText → Lexer → Layout → Parser → SurfaceAST
Resolver → CoreAST → Validador
lowerToStg → STG
```

Los errores del lexer, layout, parser, resolución o validación impiden crear un ExecutionState. Las advertencias no bloquean la ejecución.

### Metadatos y trazabilidad

```text
NodeMetadata {
  nodeId
  sourceSpan
  origin
}
```

- Los IDs se separan por espacio de nombres, por ejemplo surface:s14 y core:c27.

- Los SourceSpan usan posiciones semiabiertas y conservan línea, columna y offset.

- origin registra si un nodo fue parseado, desazucarado, generado o bajado a otra IR.

- La relación de origen permite sincronizar las vistas de fuente, Core y STG.

### SurfaceAST

SurfaceAST preserva las formas cómodas para el usuario: parámetros múltiples, aplicación agrupada, operadores infijos, listas literales y grupos de bindings. Globales y locales reutilizan SurfaceBinding; el contexto determina si el símbolo es GLOBAL o LOCAL. main conserva un nodo propio por sus restricciones especiales.

| **Nodo** | **Información principal** |
| --- | --- |
| SurfaceProgram | globalBindings y mainDefinition |
| SurfaceBinding | binder, parameters, body y metadata |
| Lambda y Application | Lista de parámetros o argumentos superficiales |
| Let | Flag recursive, bindings y body |
| Case | Scrutinee y alternativas con patrones de lista |
| ListLiteral y BinaryOperation | Azúcar que desaparecerá en Core |

### Resolución de nombres

El resolver trabaja antes del desazucarado. Cada binder recibe un SymbolId y cada uso de variable referencia ese ID, mientras que displayName queda en la SymbolTable para la interfaz. Esta decisión evita ambigüedades por shadowing y permite que los nodos generados ya nazcan resueltos.

### CoreAST y desazucarado

- Las lambdas y aplicaciones son siempre unarias.

- f x y se transforma en Application(Application(f, x), y).

- \[1, 2\] se transforma en Cons(1, Cons(2, Nil)).

- Los operadores se transforman en Primitive con aridad validada.

- Los let múltiples no recursivos se transforman en Let anidados.

- let rec se transforma en un único CoreLetRec.

- if y seq permanecen como nodos Core propios.

| **Constructor interno** | **Aridad** | **Representación superficial** |
| --- | --- | --- |
| NIL | 0 | \[\] |
| CONS | 2 | : |

### Contrato mínimo de los nodos

SurfaceBinding representa una ecuación de definición global o local. SurfaceDefinition no es un segundo tipo paralelo. SurfaceMainDefinition conserva las restricciones de la entrada. La distinción GLOBAL o LOCAL pertenece al símbolo resuelto y al contexto del binding.

| **Representación** | **Nodos necesarios** |
| --- | --- |
| Surface | Program, Binding, MainDefinition, Integer, Boolean, Variable, Lambda, Application, Let, If, Case, ListLiteral, Cons, UnaryOperation, BinaryOperation y Seq |
| Core | Program, Binding, Integer, Boolean, Variable, Lambda, Application, Let, LetRec, If, Case, Constructor, Primitive y Seq |
| Patrones | NilPattern, ConsPattern(headBinder, tailBinder) y WildcardPattern |
| Símbolos | SymbolId, displayName, scopeKind y metadata del binder |

CoreProgram contiene globalBindings y entryExpression. Cada CoreBinding contiene el SymbolId y el RHS. CoreLambda conserva un solo parámetro; CoreApplication una función y un argumento. CoreConstructor usa tag NIL con cero campos o CONS con dos campos. CoreCase conserva el scrutinee y las alternativas; CorePrimitive conserva opcode y operandos. Todos los nodos llevan NodeMetadata.

SourceSpan tiene inicio incluido y fin excluido; los offsets cuentan caracteres del texto normalizado, las líneas y columnas empiezan en 1. Un nodo generado conserva uno o más IDs de origen, sin inventar una posición nueva. El cálculo de variables libres excluye globals de las capturas y respeta los ámbitos de lambda, patrones y grupos recursivos.

El validador comprueba aridades de primitivas y constructores, unicidad de IDs, símbolos resueltos, alcance de binders y validez de metadatos. Compilar dos veces el mismo texto con la misma versión debe producir el mismo artefacto lógico.

## 4 Arquitectura del sistema

React y TypeScript envían comandos por HTTP y JSON a FastAPI. FastAPI invoca la biblioteca Python del motor y devuelve estados y diagnósticos serializados.

El motor se implementará como una biblioteca Python independiente de FastAPI. Los tests, la CLI y los experimentos podrán importarlo directamente; FastAPI será una capa de transporte para la aplicación React. En una instalación local, FastAPI puede servir tanto la API como el build de React desde localhost. En un despliegue web, el motor corre en el mismo servidor o contenedor que FastAPI.

| **Módulo** | **Responsabilidad** |
| --- | --- |
| language | Lexer, layout, parser, AST, resolución y validación |
| engine | Máquinas Core y reglas small-step |
| runtime | Heap, stack, referencias, controles y estados |
| instrumentation | Eventos, métricas, historial y materialización |
| experiments | Programas, parámetros, repeticiones y RunRecord |
| api | FastAPI y serialización versionada |
| web | React, TypeScript, editor, grafos y vistas |
| stg | lowerToStg, IR, validador y máquina STG-like |
| gc | Mark-sweep, reachability y lifetime |

### Operaciones de aplicación

- Compilar código y devolver diagnósticos y artefactos.

- Crear una ejecución con configuración y parámetros fijados antes del inicio.

- Ejecutar un step o un batch acotado de transiciones.

- Recuperar el estado actual o un estado histórico disponible.

- Elegir el modo final de resultado y exportar o importar RunRecord.

- Solicitar GC manual en una ejecución interactiva.

El frontend no implementa semántica ni calcula métricas. Puede colorear sintaxis, pero los diagnósticos oficiales y los estados ejecutables provienen del backend.

La CLI importa el motor y puede correr en la máquina local sin levantar un servidor. En la aplicación web, el parsing, la resolución de nombres y la ejecución ocurren en Python en el backend; el navegador dibuja los datos recibidos. Una sesión tiene su propio heap, configuración y estado, y no comparte objetos semánticos con otras sesiones.

Los parámetros se cargan desde la interfaz antes de crear la ejecución y quedan congelados en RunRecord. Esos campos son editables por el usuario, pero no equivalen a read o entrada interactiva durante la evaluación. La API ejecuta batches acotados para que pause pueda actuar entre batches; cancelar una sesión es una operación del controlador.

## 5 Máquina abstracta y semántica Core

La semántica es small-step. La función step recibe un estado y una configuración, aplica una única regla y devuelve un TransitionResult con el siguiente estado, ruleId, eventos y efectos. Los estados son conceptualmente inmutables; la implementación puede usar copy-on-write, snapshots y deltas.

```text
step(state, config) → TransitionResult
```

### Estrategias

| **Estrategia** | **Regla principal** | **Consecuencia** |
| --- | --- | --- |
| CBV | Evalúa el argumento antes de aplicar la función | Pasa el argumento evaluado |
| CBN | Sustituye mediante suspensiones sin actualización | Cada demanda reevalúa el cuerpo |
| CBNeed | Difiere el argumento y actualiza el resultado | Comparte la primera evaluación |

### Controles y fases

| **Elemento** | **Valores** |
| --- | --- |
| CoreControl | EvaluateCore, Return, Force e InitializeCoreBindings |
| ExecutionPhase | INITIALIZATION, EVALUATION, RESULT\_MATERIALIZATION y GARBAGE\_COLLECTION |
| ExecutionStatus | RUNNING, COMPLETED, BLACKHOLE\_DETECTED, CYCLIC\_INITIALIZATION\_DETECTED, STEP\_LIMIT\_REACHED, RESULT\_LIMIT\_REACHED y RUNTIME\_ERROR |

COMPLETED es un status y no una fase. Los estados terminales preservan el último control, stack, heap y fase para permitir su inspección. Pause, play y selección de snapshots pertenecen al controlador de interfaz.

### Reglas principales

| **Construcción** | **Comportamiento** |
| --- | --- |
| Literales | Retornan una referencia inmediata. |
| Lambda | Asigna una Closure que captura solamente variables libres locales. |
| Aplicación | Evalúa primero la función; CBV evalúa el argumento y CBN o CBNeed lo difieren. |
| Variable | Lookup y Force son transiciones separadas; almacenar o pasar una referencia no la fuerza. |
| Let | CBV evalúa el RHS; CBN crea Suspension y CBNeed crea Thunk, salvo aliases directos. |
| Primitiva | Evalúa operandos de izquierda a derecha y registra una reducción solamente si tiene éxito. |
| If | Demanda la condición y evalúa solo la rama seleccionada. |
| Constructor | CBV evalúa campos; CBN y CBNeed los difieren. Construir no es una reducción semántica. |
| Case | Demanda el scrutinee a WHNF y liga referencias de campos sin forzarlas. |
| Seq | Demanda el primer argumento a WHNF y continúa con el segundo. |

### defer y sharing

```text
defer(expr, env, strategy):
  literal  → referencia inmediata
  variable → alias a la misma referencia, sin forzar
  CBN      → Suspension(expr, freeVariableEnvironment)
  CBNeed   → Thunk(expr, freeVariableEnvironment)
```

En CBNeed, la primera demanda cambia el thunk de UNEVALUATED a EVALUATING, apila UpdateFrame y evalúa el cuerpo. Al retornar WHNF, reemplaza la dirección original por Indirection(result). Una demanda posterior de esa dirección cuenta como sharedResultHit.

### Recursión y errores cíclicos

- let rec reserva todas las direcciones antes de construir el entorno recursivo.

- Las lambdas se instalan como closures directas en todas las estrategias.

- En CBV, un ciclo durante inicialización estricta produce CYCLIC\_INITIALIZATION\_DETECTED.

- En CBNeed, reingresar a un thunk EVALUATING produce BLACKHOLE\_DETECTED.

- En CBN, x = x continúa hasta alcanzar el step limit porque no existe actualización ni blackhole.

### Reglas y eventos

ruleId identifica la regla de la máquina aplicada en una transición, por ejemplo CORE\_NEED\_ENTER\_THUNK. semanticEvent describe un hecho de interés semántico, por ejemplo ThunkForced o FunctionApplied. Una regla puede producir varios eventos y efectos; un mismo evento puede producirse en distintas máquinas. El reducer de métricas usa eventos documentados y no deduce hechos a partir del nombre de la regla.

```text
TransitionResult {
  previousStateId, nextState
  ruleId, transitionKind, phaseBefore, phaseAfter
  semanticEvents[], heapEffects[], stackEffects[]
  sourceOrigins[]
}
```

Una aplicación unaria efectiva emite FunctionApplied y BetaReduced en la misma transición. Incrementa functionApplications y betaReductions en uno, y aporta una reducción a semanticReductions. Las tres cifras describen el mismo hecho; sumarlas duplicaría trabajo. Una llamada superficial f x y puede producir dos aplicaciones unarias después del desazucarado.

### Qué hace Force

| **Referencia u objeto** | **Efecto de Force** |
| --- | --- |
| Inmediato | Devuelve el entero o booleano sin allocation. |
| Closure o Constructor | Devuelve esa misma referencia en WHNF; no recorre campos. |
| Indirection | Sigue el destino en otra transición, sin compresión de caminos. |
| Thunk UNEVALUATED | Lo marca EVALUATING, apila UpdateFrame y pasa a evaluar su cuerpo. |
| Thunk EVALUATING | Termina con BLACKHOLE\_DETECTED. |
| Reserved en CBV | Demanda la inicialización pendiente; detecta reentrada en una inicialización activa. |
| Suspension CBN | Evalúa el cuerpo con su entorno en cada demanda; no actualiza la celda. |

Force se usa en puntos de demanda: una variable evaluada, la posición de función, los operandos de primitivas, condiciones, scrutinees, seq y campos solicitados por el consumidor. Pasar o ligar una referencia no la fuerza por sí mismo. La evaluación de un thunk puede requerir muchas transiciones; UpdateFrame queda pendiente hasta que todo ese cálculo retorna WHNF.

### Inicialización recursiva

Primero se reservan todas las direcciones y se construye el entorno del grupo. Las lambdas se instalan como closures que capturan ese entorno; no se ejecutan sus cuerpos. En CBV se inicializan los demás RHS en orden de fuente, con demanda de una celda pendiente si otro RHS la necesita. Si la celda ya está INITIALIZING, la ejecución termina con CYCLIC\_INITIALIZATION\_DETECTED. Una celda completada apunta al valor mediante Indirection.

En CBNeed, los RHS no lambda del grupo se instalan como thunks. Un alias recursivo se conserva como cálculo diferido para que x = x pueda detectarse por reentrada, en vez de fabricar una cadena de indirecciones sin fin. La inicialización global sigue esta misma política; main comienza cuando el grupo está instalado. Las inicializaciones se muestran bajo INITIALIZATION; las de let rec dentro de main conservan la fase de evaluación actual.

En CBN, los RHS no lambda se instalan como suspensiones sin memoización. Un ciclo demandado continúa hasta el límite del evaluador; no se clasifica como blackhole porque esa estrategia no tiene estado EVALUATING para una suspensión.

No existe un status HALTED en el contrato final. COMPLETED significa que se satisfizo la política de resultado y no quedan transiciones pendientes. STEP\_LIMIT\_REACHED, RESULT\_LIMIT\_REACHED y las categorías de fallo preservan el estado para inspección; un límite no demuestra divergencia.

## 6 Modelo de runtime

### Referencias, entornos y heap

```text
RuntimeRef = ImmediateInteger | ImmediateBoolean | HeapReference(ObjectId)
Environment = Map<SymbolId, RuntimeRef>
```

Los enteros y booleanos son inmediatos: no reciben ObjectId ni ocupan slots. Los ObjectId son direcciones lógicas crecientes, propias de la sesión y nunca reutilizadas. El lookup devuelve la referencia exacta almacenada; no sigue indirecciones ni fuerza objetos.

| **Objeto** | **Uso** |
| --- | --- |
| Closure | Función, cuerpo y entorno de variables libres |
| Thunk | Cálculo CBNeed con estado UNEVALUATED o EVALUATING |
| Suspension | Cálculo CBN que nunca se actualiza |
| Constructor | Tag y referencias a campos |
| Indirection | Referencia al resultado actualizado |
| Reserved | Dirección reservada durante inicialización recursiva |

### Slots abstractos

- Closure, Suspension o Thunk: 1 slot de cabecera más una referencia por variable libre capturada.

- Constructor: 1 slot de cabecera más una referencia por campo.

- El cuerpo AST, nombres y metadatos no cuentan como memoria simulada.

- allocatedSlots permanece fijo aunque el objeto cambie de representación.

- Actualizar Thunk a Indirection no reduce currentHeapSlots; solamente el GC puede hacerlo.

### Stack de la máquina abstracta

- ApplyFunctionFrame y ApplyArgumentFrame

- LetFrame e IfFrame

- PrimitiveFrame y ConstructorFrame

- CaseFrame y SeqFrame

- UpdateFrame y RecursiveInitializationFrame

- Frames internos de materialización

Las métricas representan frames de la máquina abstracta, no bytes ni frames del stack nativo de Python. Cada frame conserva únicamente expresiones, referencias, entornos y progreso necesarios para continuar.

### ExecutionState e instrumentación

```text
ExecutionState {
  stateId, sessionId, transitionIndex
  machineState
  instrumentationState
}
```

MachineState contiene status, phase, control, stack, heap y globalEnvironment. InstrumentationState contiene métricas, ObjectHistory y datos de análisis. La máquina no consulta la instrumentación para decidir su próxima transición. El GC no trata el historial ni la selección visual como raíces.

### Trazas

| **Modo** | **Persistencia** |
| --- | --- |
| FULL | Conserva todos los estados para navegación interactiva. |
| EVENTS | Conserva eventos, deltas y checkpoints periódicos. |
| METRICS\_ONLY | Conserva el estado actual y métricas, descartando estados anteriores. |

### Estado y configuración de ejecución

```text
MachineState {
  machineKind, strategy, status, phase
  control, localEnvironment, globalEnvironment
  heap, stack, resultState, nextObjectId
}
ExecutionConfig {
  machineKind, strategy, resultPolicy
  executionStepLimit, resultNodeLimit, traceMode
}
```

La configuración de B añade gcPolicy y thresholdSlots; MachineState añade gcState opcional. Las combinaciones válidas son Core con CBV, CBN o CBNeed y STG con CBNeed. Solicitar STG con otra estrategia produce un diagnóstico de configuración antes de iniciar.

resultPolicy se elige antes del run y resolvedResultMode registra la elección efectiva. ASK\_AT\_WHNF es una política del controlador: la máquina permanece RUNNING a la espera de la selección y no consume transiciones mientras espera. resultState conserva la referencia de salida y el progreso del consumidor, por separado del valor canónico ya construido.

transitionIndex cuenta todas las transiciones del motor. evaluatorTransitions cuenta solo las del evaluador y es el reloj del executionStepLimit; las transiciones administrativas del consumidor y las del GC tienen sus propios contadores. Un step exitoso crea un nuevo estado lógico. La retención física de ese estado depende de FULL, EVENTS o METRICS\_ONLY; el renderer no tiene que dibujar después de cada step.

### Payloads de continuaciones y reserva de memoria

| **Familia de frame** | **Datos que debe conservar** |
| --- | --- |
| Aplicación | Argumento y entorno pendientes, o función ya evaluada |
| Let y recursión | Binder, cuerpo, entorno y cursor de inicialización |
| If y case | Ramas o alternativas y entorno de continuación |
| Primitiva y constructor | Operación o tag, valores obtenidos y campos pendientes |
| Seq | Segundo argumento y entorno |
| Update | ObjectId original del thunk y contexto de retorno |
| Consumidor | Referencia demandada, campo pendiente y camino del resultado |

El tamaño de una reserva se fija antes de instalar su contenido: una lambda reserva 1 + número de capturas; un thunk o una suspensión, la cabecera más sus capturas; una celda CBV que contendrá una indirección reserva un slot. Reserved cambia de contenido conservando su ObjectId y allocatedSlots. Completar una reserva o actualizar un thunk no constituye una nueva allocation.

NIL es un constructor de cero campos y cuesta un slot cuando se asigna; CONS cuesta tres. No se introduce un singleton oculto ni una optimización de representación diferente por estrategia. Las referencias inmediatas ocupan un campo en un objeto que las guarda, aunque no tengan objeto propio en el heap. La memoria del AST, los mapas del host, la traza y los valores canónicos quedan fuera del heap simulado.

## 7 Garbage collection y análisis de memoria

La Propuesta B incluye un collector mark-sweep, stop-the-world y ejecutado paso a paso. Sus transiciones son visibles y no consumen el límite de pasos del evaluador. El GC no fuerza thunks, no cambia reducciones semánticas y debe preservar el resultado observable.

### Política de activación

- El GC automático se dispara solamente después de una transición del programa que haya asignado al menos un objeto.

- La condición es currentHeapSlots mayor que thresholdSlots.

- Terminar un ciclo todavía por encima del threshold no dispara otro inmediatamente; debe ocurrir una nueva allocation.

- La interfaz puede solicitar GC manual, pero los experimentos no realizan intervenciones manuales.

- Durante GC, phase es GARBAGE\_COLLECTION; resumePhase solo guarda la fase interrumpida.

### Raíces y aristas

| **Raíces** | **No son raíces** |
| --- | --- |
| Control y entorno actual | Trace y ObjectHistory |
| Stack y globalEnvironment | Métricas y selección visual |
| Resultado y materialización pendiente | Buffer canónico del host |
| Reserved y referencias protegidas | Objetos solo visibles por historial |

Las aristas provienen de entornos capturados, campos de constructores, destinos de Indirection y referencias de Reserved. El mark procesa un objeto por transición en orden determinista; el sweep inspecciona un ObjectId por transición.

### Reachability y lifetime

El análisis pasivo de reachability se recalcula después de cada transición y nunca modifica el heap. ObjectHistory registra creación, cambios, primera y última demanda del programa, inalcanzabilidad y recolección. Los accesos del visualizador, GC o analizador no cuentan como accesos del programa.

- Un objeto puede estar inalcanzable pero continuar en el heap hasta un GC.

- La fecha de recolección es distinta de la fecha de primera inalcanzabilidad.

- Las métricas de lifetime se expresan en transiciones, no en segundos.

### Estado del collector e invariantes

```text
GcState {
  stage: MARK | SWEEP
  resumePhase, pendingObjects, markedObjectIds
  sweepObjectIds, sweepCursor, cycleId
}
```

Comenzar GC captura las raíces y congela la máquina del programa. MARK recorre referencias con una cola determinista y evita visitas duplicadas. SWEEP inspecciona direcciones en orden creciente y elimina las no marcadas. La transición que completa el ciclo restaura resumePhase; resume no es una quinta fase ni un valor adicional de stage. Las referencias a celdas Reserved y a resultados pendientes deben aparecer en las raíces antes del primer mark.

La política GC OFF conserva todo lo asignado; AUTO usa el umbral de slots; MANUAL responde a un comando registrado. gcTransitions no consume executionStepLimit. El controlador limita el tamaño de cada batch, y mark y sweep terminan porque trabajan sobre un heap finito congelado. Los picos se actualizan en el estado posterior a cada transición, también durante INITIALIZATION y RESULT\_MATERIALIZATION.

El trigger consulta el tamaño del heap semántico y la política de GC, sin leer el acumulador de métricas. currentHeapSlots es una medición de ese mismo tamaño, pero la instrumentación no decide las transiciones. Cambiar el modo de traza o la vista no cambia el punto de activación del collector.

### Historia de objetos y medidas censuradas

ObjectHistory conserva creación, tipo inicial, allocation site, cambios de representación, primera y última demanda del programa, última alcanzabilidad y recolección. Consultar un objeto desde el visualizador o recorrerlo desde mark no cuenta como demanda. Una referencia guardada en una raíz o en otro objeto puede mantenerlo vivo aunque nunca se demande.

Para lifetime se registra explícitamente el reloj utilizado: índice de transición y contador de transiciones del evaluador. Así, la duración de un ciclo GC no se interpreta como trabajo adicional del programa. El tiempo hasta primera demanda es firstDemand − creation; la permanencia tras última demanda es collection − lastDemand cuando ambos extremos existen. Un objeto no recolectado al terminar tiene una observación censurada; no se informa duración cero ni una vida completa inventada.

El análisis pasivo informa reachableObjects, unreachableObjects, reachableSlots y sus picos con las mismas raíces del collector. Una fase MARK o SWEEP parcial no se usa como aproximación de alcanzabilidad. La herramienta distingue memoria asignada, memoria alcanzable y memoria efectivamente recuperada.

## 8 Representación y máquina STG

STG-like es una representación didáctica inspirada en la Spineless Tagless G-machine. No pretende reproducir el STG exacto de GHC ni sus calling conventions, registros, tipos unboxed, info tables o backend Cmm. Su objetivo es mostrar visualmente por qué una representación basada en clausuras, puntos explícitos de demanda y actualizaciones resulta útil para implementar evaluación lazy.

### Alcance de la IR

```text
Atom = Variable | Integer | Boolean
Expr = Atom | Apply | Primitive | Construct | Let | LetRec | Case | Raise
Rhs  = AtomAlias | ClosureForm | ConstructorForm
```

Las funciones son unarias. Los argumentos complejos se convierten en bindings y todas las demandas introducidas por primitivas, if y seq quedan expresadas mediante case. lowerToStg es determinista, no realiza optimizaciones y conserva mapas de origen hacia Core y fuente.

### Clausura uniforme

```text
StgClosure {
  freeVariableRefs
  globalReferences
  parameter
  body
  updateMode: REENTRANT | UPDATABLE
  evaluationState
}
```

| **Forma** | **Parámetro** | **Modo** | **Estado inicial** |
| --- | --- | --- | --- |
| Función | Uno | REENTRANT | READY |
| Thunk | Ninguno | UPDATABLE | UNEVALUATED |

Funciones y thunks son configuraciones distintas de una misma clausura. SINGLE\_ENTRY se omite porque no es necesario para los objetivos del trabajo. Las referencias globales son estáticas y no ocupan slots de captura; las variables libres locales sí.

### Máquina ejecutable

```text
EvaluateStg(expression, environment) | Enter(reference) | Return(reference)
```

| **Regla** | **Comportamiento** |
| --- | --- |
| Enter immediate o constructor | Retorna el mismo valor en WHNF. |
| Enter Indirection | Continúa con el destino sin compresión de caminos. |
| Enter REENTRANT | Retorna la función; un StgApplyFrame ejecuta el cuerpo cuando hay argumento. |
| Enter UPDATABLE | Marca EVALUATING, apila StgUpdateFrame y evalúa el cuerpo. |
| Update | Reemplaza la dirección por Indirection(result), sin liberar slots. |
| Enter EVALUATING | Termina con BLACKHOLE\_DETECTED. |
| Case | Demanda el scrutinee y liga campos sin forzar. |
| Construct | Resuelve átomos y asigna el constructor sin demandar campos. |

### LetRec y globals

LetRec reserva direcciones para todo el grupo, construye el entorno recursivo e inicializa un binding por transición. AtomAlias se prohíbe directamente dentro de LetRec y se normaliza como clausura actualizable. Los globals forman un grupo recursivo y main se baja como entryExpression separado.

### Equivalencia

```text
observableOutcome(runCoreNeed(program), mode)
  = observableOutcome(runStgNeed(lowerToStg(program)), mode)
```

La propiedad se comprueba para programas válidos, deterministas, terminantes y con resultados de primer orden. Se comparan valores canónicos, categorías públicas de error y blackholes; no se exige igualdad de transiciones, allocations, heaps, stacks o métricas. Los límites artificiales producen un resultado inconcluso.

### Contrato de lowerToStg

lowerToStg recibe un CoreProgram validado y devuelve un StgProgram y mapas de origen. El recorrido es determinista en orden de fuente; crea nombres frescos sin colisiones y calcula capturas por SymbolId. El IR y el runtime son distintos de Core, aunque ambos produzcan el mismo esquema de valores canónicos. No se aplican inlining, constant folding, análisis de strictness ni eliminación de bindings.

| **Forma Core** | **Transformación STG** |
| --- | --- |
| Literal o variable | Átomo; leer una variable no introduce una copia del valor |
| Lambda | ClosureForm unaria REENTRANT con capturas explícitas |
| Aplicación | Apply con función y argumento atómicos; un argumento complejo se liga como clausura UPDATABLE |
| Constructor | Construct con campos atómicos; los campos complejos reciben bindings diferidos |
| Let | AtomAlias para RHS atómico no recursivo; closure para función o cálculo diferido |
| LetRec | Grupo recursivo; aliases se normalizan como clausuras UPDATABLE |
| Primitive | Cases anidados que demandan operandos en orden y luego aplican el opcode |
| If y seq | Case explícito para demandar condición o primer argumento |
| Case | Conserva demanda del scrutinee y patrones de campos sin demanda adicional |

```text
Core:  let x = 1 + 2 in x + x
STG:   let x = UPDATABLE {} () ->
         case 1 of a ->
           case 2 of b -> primitive ADD a b
       in case x of u ->
            case x of v -> primitive ADD u v
```

El ejemplo es notación explicativa del IR, no código de la minilengua. Los cases generados incluyen validación del tipo requerido; Raise representa una categoría de fallo interno, no una excepción que pueda escribir el usuario. Un case de seq acepta cualquier WHNF sin recorrer sus campos. Un case de if selecciona True o False y conserva un fallo de tipo para otro valor.

### Validador y continuidad del runtime

StgProgram contiene globalBindings y entryExpression. ClosureForm conserva capturas, referencias globales, parámetro opcional, body y updateMode. Las referencias globales no se duplican en las capturas. AtomAlias se permite solo fuera de grupos recursivos; ConstructorForm valida NIL y CONS. El validador exige argumentos atómicos, scope válido, capturas completas sin duplicados, aridades correctas y origen trazable.

La máquina STG usa StgApplyFrame, StgCaseFrame, StgUpdateFrame y continuaciones de inicialización y resultado. Comparte RuntimeRef, ObjectId, tamaños de slots, GC, límites y consumidores canónicos con Core, pero tiene controles y ruleId propios. La entrada en una clausura UPDATABLE puede ocupar muchos steps antes de su actualización; la cadena activa se refleja en los frames de actualización.

La equivalencia se comprueba al observar el resultado de cada máquina con la misma demanda. observe es una operación de prueba y materialización, no una transformación del programa. lowerToStg transforma código antes de ejecutar. WHNF\_ONLY compara enteros, booleanos o tag y aridad; MATERIALIZE\_COMPLETE\_VALUE compara la estructura finita de primer orden. La coincidencia de nombres del esquema canónico no supone igualdad de heaps ni de costes.

## 9 Resultado y observación

El visualizador inspecciona snapshots sin ejecutar el programa. La observación activa se denomina materialización del resultado y solo comienza después de que main alcanza WHNF.

| **Modo** | **Observación** |
| --- | --- |
| WHNF\_ONLY | Enteros y booleanos completos; constructor limitado a tag y aridad; función opaca. |
| MATERIALIZE\_COMPLETE\_VALUE | Demanda recursivamente los campos de constructores y produce un valor canónico completo. |
| ASK\_AT\_WHNF | Política interactiva que pausa el controlador y solicita elegir uno de los dos modos anteriores. |

Las transiciones administrativas del consumidor no cuentan como trabajo del programa. Las transiciones del evaluador provocadas por demandar campos sí cuentan y se clasifican bajo RESULT\_MATERIALIZATION. executionStepLimit limita trabajo del evaluador; resultNodeLimit limita nodos materializados.

```text
CanonicalValue = Integer | Boolean | ConstructorWHNF
               | Constructor(tag, fields) | OpaqueFunction
```

Core y STG comparten el mismo esquema canónico. Los resultados funcionales se muestran como opacos, pero quedan fuera de las pruebas automáticas de equivalencia estructural.

### Condiciones de finalización

En WHNF\_ONLY, la salida de CONS tiene tag y aridad, aunque sus campos sigan diferidos. En MATERIALIZE\_COMPLETE\_VALUE, el consumidor recorre campos de izquierda a derecha y en profundidad, pide al evaluador la WHNF necesaria y construye un árbol canónico. Cada aparición en el árbol cuenta como nodo; el sharing del heap no se identifica con igualdad de subárboles ni se convierte en memoria simulada del resultado.

Los resultados infinitos o cíclicos no tienen una materialización completa finita. El consumidor usa resultNodeLimit y el evaluador executionStepLimit, devuelve la categoría de límite que se alcance y conserva el prefijo disponible como parcial. Una función se representa como OpaqueFunction; no se compara extensión de funciones. ASK\_AT\_WHNF nunca se usa sin resolver en una corrida experimental.

Demanda y visualización son operaciones diferentes. Expandir un nodo, consultar métricas o mover el cursor histórico no ejecuta Force. El usuario elige materializar de forma explícita y ve un aviso que explica que esa elección puede evaluar campos, crear objetos y aumentar métricas bajo RESULT\_MATERIALIZATION. No se materializa después de cada transición.

## 10 Métricas

Las métricas se actualizan mediante un reducer puro a partir de TransitionResult. phase y transitionKind se mantienen separados: la fase indica dónde ocurre el trabajo y el tipo distingue EVALUATOR, RESULT\_CONSUMER y GC. La interfaz puede combinarlos para presentación sin perder la información original.

### Trabajo semántico

```text
semanticReductions = suma de los seis contadores definidos abajo
```

- functionApplications y betaReductions describen el mismo hecho desde métricas diferentes; no deben sumarse entre sí.

- variableLookups cuenta evaluaciones de variables, no lecturas internas del visualizador.

- Los totales se desglosan opcionalmente por fase, nodo fuente y tipo de evento.

- El wall time es auxiliar y se reporta como mediana y dispersión de repeticiones.

### Memoria y stack

| **Grupo** | **Métricas** |
| --- | --- |
| Allocations | totalAllocations, allocationsByType, allocationsBySite |
| Heap | currentHeapSlots, peakHeapSlots y additionalPeakOverBaseline |
| Stack | pushes, pops, currentFrames, peakFrames y desglose por frame |
| Materialización | resultDemandEvaluatorTransitions, resultConsumerTransitions y resultNodes |

### Métricas de estrategia

| **Área** | **Métricas principales** |
| --- | --- |
| CBNeed | thunksCreated, thunkDemands, thunksForced, thunksUpdated, sharedResultHits, blackholes, thunksNeverForced y maxThunkChainLength |
| CBN | suspensionsCreated, suspensionDemands, suspensionReevaluations y suspensionsNeverDemanded |
| GC | cycles, objectsMarked, objectsCollected, slotsReclaimed y transiciones por ciclo |
| Lifetime | creación, última demanda, primera inalcanzabilidad y recolección |
| STG | entries, closure allocations, applications, updates, indirection traversals, shared hits y max update depth |

No se construirá un puntaje compuesto de trabajo. Las comparaciones utilizarán deltas o ratios por métrica, siempre indicando unidad, fases incluidas y limitaciones. Cada panel tendrá una explicación accesible mediante un control de información.

### Definiciones y ecuaciones de contabilización

| **Métrica** | **Evento o criterio** |
| --- | --- |
| evaluatorTransitions | Una transición con transitionKind EVALUATOR, incluida inicialización |
| betaReductions | Entrada al cuerpo de una aplicación unaria efectiva |
| letReductions | Activación de un Let o grupo LetRec; no cada celda interna |
| primitiveReductions | Una operación primitiva exitosa, incluida negación |
| conditionalReductions | Selección de una rama válida de if |
| caseReductions | Selección de una alternativa válida de case |
| seqReductions | Primer argumento en WHNF y continuación con el segundo |
| variableLookups | Lectura de una Variable evaluada; lookup interno de defer no cuenta |
| totalAllocations | Nuevo ObjectId; reserva cuenta una vez, update no cuenta |
| currentFrames | Número de frames presentes en el stack actual |

```text
semanticReductions = betaReductions + letReductions
  + primitiveReductions + conditionalReductions
  + caseReductions + seqReductions
currentHeapSlots = sum(obj.allocatedSlots for obj in heap)
peakHeapSlots = max(currentHeapSlots en todos los estados)
additionalPeakOverBaseline = max(0, peakHeapSlots - baselineSlots)
currentFrames = pushes - pops
peakFrames = max(currentFrames en todos los estados)
```

baselineSlots es el heap al terminar la inicialización global, antes de main. peakHeapSlots incluye toda la corrida; se ofrece también el pico posterior al baseline para interpretar crecimiento adicional. El campo sourceOrigins permite atribuir eventos a código fuente sin duplicar el total cuando un evento tiene varios orígenes. Un fallo no suma una reducción primitiva exitosa.

### Demanda y reutilización

| **Métrica CBNeed** | **Definición** |
| --- | --- |
| thunksCreated | Celdas que llegan a contener un thunk, incluidas reservas instaladas |
| thunkDemands | Demandas a una celda que es thunk o resultado de su update |
| thunksForced | Inicio UNEVALUATED → EVALUATING; como máximo una vez por thunk |
| thunksUpdated | Actualizaciones exitosas a Indirection con WHNF |
| sharedResultHits | Demanda posterior que reutiliza una celda actualizada por un thunk |
| blackholes | Reentrada demandada en un thunk EVALUATING |
| thunksNeverForced | Creados cuyo conteo de inicio de evaluación sigue en cero |
| maxThunkChainLength | Máximo de updates de thunk pendientes simultáneamente |

Una Indirection de un alias o de inicialización CBV no cuenta como sharedResultHit. El historial distingue el origen de cada celda y conserva los contadores aunque se recolecte. Una demanda fallida cuenta como demanda, pero no como actualización. Las cadenas de indirecciones y la profundidad de evaluación pendiente se muestran por separado.

En CBN, suspensionDemands cuenta cada inicio de reevaluación; suspensionReevaluations cuenta los inicios posteriores al primero para la misma celda; suspensionsNeverDemanded cuenta las creadas sin inicio. En STG se presentan entries, applications, updates, indirection traversals, shared hits y profundidad de updates junto con los contadores comunes. Los cases introducidos por lowering se identifican como demanda generada; no se atribuyen a un case que el usuario haya escrito.

### Comparaciones y unidades

CBV work, CBN work y CBNeed work no son nuevas unidades ni un índice ponderado. Se elige una métrica concreta: transiciones del evaluador, reducciones semánticas o aplicaciones, y se expresa un delta o ratio. Un ratio M\_A / M\_B se informa solo si el denominador es positivo y ambos resultados permiten la comparación; con denominador cero se informa el par de valores y el delta.

Se pueden comparar estrategias, tamaños, modos de resultado o políticas de GC diferentes si la diferencia se declara como factor del experimento. Para aislar el efecto de la estrategia se mantienen iguales el programa, los parámetros y la demanda. Los límites producen mediciones truncadas y no se comparan como costes completos. Los slots abstractos, las reducciones y los frames no se equiparan a bytes, instrucciones o stack nativo de C o Haskell.

Wall time mide duración del motor con reloj monotónico, fuera de compilación, HTTP, exportación y renderizado. Se registran modo de traza e instrumentación activa, porque también añaden coste de host. Las ejecuciones para timing se separan de las trazas didácticas; la mediana y una medida de dispersión se calculan sobre repeticiones completadas y se informa también cuántas fallaron o alcanzaron límites.

## 11 Validación y tests

| **Nivel** | **Propósito** |
| --- | --- |
| Unitarios | Lexer, parser, layout, resolución, free variables, desazucarado y reducers. |
| Transición | Una regla, un estado inicial pequeño y efectos esperados exactos. |
| Integración | Programas completos, status, resultado y métricas relevantes. |
| Diferenciales | Consistencia entre estrategias donde deben coincidir y entre GC on u off. |
| Golden | Pocas trazas representativas y serializaciones versionadas. |
| API y UI | Contratos HTTP, navegación, controles y pasividad del visualizador. |

Los tests comprueban primero resultado y status, después eventos y métricas pertinentes. Para programas pequeños se admiten cantidades exactas; para casos complejos se prefieren invariantes y relaciones para evitar tests frágiles.

```text
let x = 1 + 2 in x + x
 
primitiveReductions: CBV = 2, CBN = 3, CBNeed = 2
CBNeed sharedResultHits = 1
CBN suspensionReevaluations = 1
```

Los tests diferenciales tienen un criterio de aprobación o rechazo: comprueban propiedades conocidas. Los experimentos, en cambio, miden diferencias intencionales y requieren interpretación; por eso viven en directorios y pipelines separados.

- GC activado o desactivado debe preservar observableOutcome.

- CoreNeed y STGNeed deben coincidir para resultados finitos de primer orden.

- La misma configuración debe producir una traza determinista salvo wall time.

- La cobertura se controla por ruleId, evento, objeto, frame, status e invariantes, además de líneas de código.

### Suite inicial con oráculos

| **Familia** | **Verificación** |
| --- | --- |
| Léxico y layout | Comentarios, negativos, \<=, tabs inválidos y equivalencia entre llaves e indentación |
| Parser | f x y a izquierda; 1:2:\[\] a derecha; precedencia; error en 1 \< 2 \< 3; seq incompleto |
| Resolver | Shadowing correcto; variable no ligada; main duplicado; grupo recursivo; captura libre exacta |
| Aritmética | main = 1 + 2 \* 3 produce Integer(7) |
| Funciones | main = (\\x -\> x + 1) 4 produce Integer(5) |
| Sharing | let x = 1 + 2 in x + x produce Integer(6) y contadores indicados arriba |
| Demanda evitada | main = (\\x -\> 7) (1 + 2): CBV hace la suma; CBNeed no la demanda |
| Mutua recursión | even/odd para entradas pequeñas producen booleanos esperados |
| Ciclo demandado | let rec x = x in x: CBV ciclo de inicialización; CBNeed blackhole |
| Observación | CONS con un campo pendiente: WHNF\_ONLY no lo fuerza; materialización sí |
| Límites | Recursión y salida infinita preservan prefijo/estado y categoría de límite |
| Pasividad | Consultar vistas, métricas e historial no cambia siguiente transición |
| CBN | Sharing retorna 6 con tres primitivas; ciclo recursivo alcanza step limit |
| GC | Cadena, ciclo inalcanzable, roots en frames, Reserved e Indirection; ninguna raíz eliminada |
| STG | IR válida y mismo outcome que CoreNeed para ambas demandas y fallos públicos |

El oráculo primario es el valor canónico o la categoría pública de terminación. Métricas exactas se verifican solo cuando son parte del contrato del caso pequeño; los tests diferenciales no exigen costes iguales entre estrategias. Un programa que termine en Need y alcance un límite en CBV no es una prueba fallida de equivalencia: pertenece a una propiedad de demanda distinta.

Las pruebas de escala pequeñas comprueban que la herramienta maneja tamaños acotados y mantiene invariantes. La búsqueda de tendencias de tiempo, heap o stack con tamaños crecientes pertenece a los experimentos. Compartir un programa entre ambos conjuntos no cambia sus objetivos ni permite usar una medición como único oráculo de corrección.

## 12 Diseño experimental

| **ID** | **Experimento** | **Objetivo** |
| --- | --- | --- |
| E01 | Argumento no utilizado | Mostrar trabajo evitado por evaluación no estricta. |
| E02 | Sharing | Contrastar reevaluación y reutilización del resultado. |
| E03 | Pipeline finito | Medir take, map y generación de listas finitas. |
| E04 | Estructura infinita | Mostrar productividad lazy con from y take. |
| E05 | Foldr | Comparar combinadores estrictos y no estrictos. |
| E06 | Foldl lazy | Observar acumulación de thunks y crecimiento de stack o heap. |
| E07 | Foldl estricto | Usar seq para controlar acumulación. |
| E08 | Métodos recursivos | Comparar patrones recursivos y contrastar con C y Haskell. |
| E09 | Garbage collection | Estudiar threshold, ciclos, heap máximo y reclamación. |
| E10 | Lifetime | Observar bindings no usados, inalcanzabilidad y recolección. |

### Metodología común

- Los parámetros se eligen antes de la ejecución; la minilengua no tiene entrada interactiva durante el run.

- Cada programa, prelude, configuración y conjunto de parámetros queda versionado.

- Las métricas lógicas se obtienen en una ejecución determinista y se verifican con tests.

- El tiempo de pared se mide en repeticiones separadas y no incluye HTTP, serialización ni renderizado web.

- El modo de resultado se fija y registra; no se comparan runs con políticas de materialización distintas como si fueran equivalentes.

- Las comparaciones usan escalamiento por tamaños de entrada y reportan status terminal además de métricas.

- En experimentos de estrategias, GC automático permanece desactivado y reachability puede calcularse pasivamente; GC solo varía cuando es un factor declarado.

### Experimento E08

E08 compara recursión lineal simple, recursión con acumulador, recursión sobre listas y, opcionalmente, un caso con reutilización de resultados. Dentro de la minilengua se comparan métricas abstractas entre estrategias. C y Haskell se compilan y miden por separado con sus propias herramientas; la comparación cruzada es principalmente explicativa y no equipara reducciones abstractas con instrucciones o bytes nativos.

| **Entorno** | **Mediciones** |
| --- | --- |
| Minilengua | CBV y CBNeed: reducciones, allocations, peak heap y peak stack |
| C | Tiempo, stack y allocations cuando la herramienta lo permita |
| Haskell | Tiempo, allocations, stack y perfilado RTS cuando corresponda |

### RunRecord

```text
RunRecord {
  schemaVersion, engineVersion, languageVersion
  sourceHash, parameters, executionConfig
  finalStatus, observableOutcome, finalMetrics
  traceMode, traceReference, commandLog
}
```

### Programas base de la suite

Los siguientes programas fijan una base reproducible. n y k son metavariables del manifiesto experimental, sustituidas por literales no negativos antes de compilar; no son variables libres del lenguaje. Cada corrida incluye únicamente las definiciones transitivamente necesarias del prelude, para evitar introducir globals estrictos ajenos al experimento.

```text
range n = if n <= 0 then [] else n : range (n - 1)
from n = n : from (n + 1)
map f xs = case xs of { [] -> []; h:t -> f h : map f t }
take n xs = if n <= 0 then [] else
  case xs of { [] -> []; h:t -> h : take (n - 1) t }
foldr f z xs = case xs of
  { [] -> z; h:t -> f h (foldr f z t) }
foldl f z xs = case xs of
  { [] -> z; h:t -> foldl f (f z h) t }
foldlStrict f z xs = case xs of
  { [] -> z; h:t -> let { z1 = f z h } in
      seq z1 (foldlStrict f z1 t) }
add a b = a + b
double x = x * 2
sumTo n = if n <= 0 then 0 else n + sumTo (n - 1)
sumAcc n a = if n <= 0 then a else sumAcc (n - 1) (a + n)
ignore a b = a
```

range n construye \[n,n−1,...,1\]. from 1 construye \[1,2,...\] de forma productiva en estrategias lazy. Las definiciones del prelude pertenecen a la minilengua; no se implementan como primitivas especiales en Python.

#### E01 Programa y demanda

```text
main = (\x -> 7) (sumTo n)
```

Parámetros: n. Demanda: WHNF\_ONLY. Resultado 7. Comparar reducciones y trabajo del argumento; lazy evita demandarlo.

#### E02 Programa y demanda

```text
main = let { x = sumTo n } in x + x
```

Parámetros: n. Demanda: WHNF\_ONLY. Resultado n\*(n+1). En B, CBN permite observar reevaluación; Need comparte y CBV evalúa una vez.

#### E03 Programa y demanda

```text
main = take k (map double (range n))
```

Parámetros: n, k ≤ n. Demanda: MATERIALIZE\_COMPLETE\_VALUE. Prefijo de k valores. Contrastar trabajo sobre toda la lista con producción demandada, allocations y picos.

#### E04 Programa y demanda

```text
main = take k (map double (from 1))
```

Parámetros: k. Demanda: MATERIALIZE\_COMPLETE\_VALUE. Lista \[2,4,...,2k\] en estrategias lazy; CBV alcanza un límite al construir la fuente infinita.

#### E05 Programa y demanda

```text
main = foldr ignore 0 (range n)
```

Parámetros: n. Demanda: WHNF\_ONLY. Resultado n para n\>0. Variante estricta: foldr add 0 (range n). El combinador determina demanda de la cola.

#### E06 Programa y demanda

```text
main = foldl add 0 (range n)
```

Parámetros: n. Demanda: WHNF\_ONLY. Resultado n\*(n+1)/2. Observar acumulación de cálculos del acumulador y costo de demandar el escalar final.

#### E07 Programa y demanda

```text
main = foldlStrict add 0 (range n)
```

Parámetros: n. Demanda: WHNF\_ONLY. Mismo escalar que E06. Comparar thunks, reducciones, frames y slots bajo demanda explícita con seq.

#### E08 Programa y demanda

```text
main = sumTo n
```

Parámetros: n. Demanda: WHNF\_ONLY. Comparar con sumAcc n 0 y folds sobre range n, y contrastar equivalentes C/Haskell.

#### E09 Programa y demanda

```text
main = sumAcc n 0
```

Parámetros: n, thresholdSlots. Demanda: WHNF\_ONLY. Conservar resultado con GC OFF/AUTO y medir slots recuperados, objetos retenidos y ciclos.

#### E10 Programa y demanda

```text
main = let { unused = sumTo n } in sumAcc n 0
```

Parámetros: n. Demanda: WHNF\_ONLY. Distinguir allocation, demanda, alcanzabilidad y recolección. La interpretación depende de la estrategia.

### Matriz de ejecución y calibración

La suite de A ejecuta E01–E08 en Core CBV y Core CBNeed. En B, E01–E07 se ejecutan además en Core CBN; E08 mantiene la comparación principal CBV frente a CBNeed acordada con el profesor. E09 y E10 agregan los factores GC y alcanzabilidad. STGNeed se usa para equivalencia y demostración; sus costes se presentan por separado de los de Core.

Para los pilotos se propone n ∈ {10, 100, 1000} y k ∈ {1, 10, 100}, filtrando k ≤ n en E03. Estos valores son una cuadrícula inicial ajustable, no un resultado ni un acuerdo irreversible. Los pilotos fijan límites suficientes y una cuadrícula definitiva antes de medir; se versiona cualquier cambio. E04 usa el mismo límite en la comparación truncada y no informa un coste CBV completo.

En E09 se parte de GC OFF y se exploran umbrales en slots por encima y por debajo del heap observado en el piloto. Un umbral se registra en términos absolutos y respecto al baseline. E10 usa historial por objeto, porcentajes nunca demandados y duración censurada; no diagnostica automáticamente un space leak.

### Protocolo de E08 y comparación externa

Casos obligatorios de E08: recursión lineal con sumTo, acumulador con sumAcc y recursión sobre listas con folds. La variante de reutilización usa un let compartido y se conserva como caso opcional. Se verifica primero igualdad matemática del resultado. La minilengua mide reducciones, allocations, peakHeapSlots y peakFrames; CBNeed añade thunks y sharedResultHits.

C y Haskell reciben entradas equivalentes y deben producir el resultado escalar antes de detener el cronómetro. Se fija una política de desbordamiento y se usan tamaños cuyo resultado cabe en el tipo entero elegido en C; los enteros arbitrarios de la minilengua no se confunden con ese costo nativo. La construcción de listas se mide de forma explícita o separada, igual en las variantes externas que se comparen.

Se registran compilador, versión, flags, sistema, arquitectura, comando, repeticiones y política de GC nativo. En Haskell, allocations y máxima residencia requieren estadísticas del RTS; perfiles de thunks o stack se etiquetan como evidencia indirecta cuando corresponda. En C, allocations, peak heap y stack solo se informan si se dispone de un método de medición definido. La máxima residencia de GHC no se llama peak heap abstracto.

La comparación cuantitativa estricta se hace dentro de la minilengua y dentro de las implementaciones C/Haskell por separado, indicando sus modelos distintos. La comparación cruzada es explicativa. Las optimizaciones, eliminación de recursión de cola y representación numérica del compilador se registran porque también afectan el resultado; no se atribuye toda diferencia temporal a CBV frente a lazy.

### Datos mínimos y repetibilidad

RunRecord debe contener el texto o referencia íntegra del programa y prelude, sourceHash, versiones, parámetros, configuración, demanda efectiva, resultado completo o parcial, status y motivo de terminación, métricas con unidades, modo de traza y comandos relevantes. Un registro externo añade herramientas, flags y entorno. El hash por sí solo no permite reconstruir el programa y no reemplaza el texto o el artefacto versionado.

Las métricas lógicas se obtienen una vez por configuración determinista. El timing usa calentamiento y repeticiones cuyo número se fija tras el piloto, sin mezclar muestras perfiladas con muestras de tiempo normal. Cada tabla informa tamaño de entrada, resultado o status y número de muestras válidas. La exportación usa JSON para el registro íntegro y CSV para métricas tabulares.

## 13 Visualizador y experiencia de uso

| **Vista** | **Contenido** |
| --- | --- |
| Editor | Código, diagnósticos, estrategia, parámetros y configuración de ejecución. |
| Ejecución | Fuente, Core, control, fase, status, stack, heap, regla actual y métricas. |
| Grafo | AST o IR y grafo vivo de memoria con nodos, referencias, raíces y cambios. |
| Comparación | Resultados y métricas de ejecuciones independientes por estrategia. |
| Experimentos | Selección, parámetros, ejecución, tablas, gráficos y exportación. |
| STG | Fuente, Core y STG sincronizados con closures, demandas y actualizaciones. |

### Grafo de memoria

- Nodos para closures, thunks, suspensions, constructores, Reserved e Indirection.

- Aristas para entornos capturados, campos y destinos de indirecciones.

- Raíces provenientes de globals, control y stack.

- Resaltado de objetos asignados, modificados o eliminados en la última transición.

- Modo tabla para inspección exacta y modo grafo para comprensión visual.

- Colores de reachability y visualización de mark y sweep durante GC.

### Divulgación progresiva

La vista inicial muestra resultado, status, reducciones, allocations, peak heap, peak stack y métricas específicas. Los desgloses por fase, tipo, frame y fuente quedan detrás de controles expandibles. Los iconos de información consultan un catálogo versionado de MetricDescriptor y ConceptDescriptor con definición, unidad, motivación y limitaciones.

### Persistencia

- Las ejecuciones interactivas pueden mantenerse temporalmente en memoria.

- Los resultados experimentales se persisten y exportan con versiones.

- JSON es suficiente para la primera implementación; SQLite puede incorporarse si se necesita consultar muchas ejecuciones.

- ManualGcRequested y ResultModeSelected se registran como comandos relevantes; navegación y selección visual no se registran como efectos semánticos.

Cada descriptor de métrica incluye nombre, definición, unidad, eventos que la incrementan, fases incluidas y limitaciones. El control de información explica también por qué se eligió esa medición, por ejemplo: “La métrica representa frames de la máquina abstracta, no bytes ni frames del stack nativo de Python”. El desglose permanece opcional mediante un control expandible.

Volver a un estado histórico mueve el cursor de lectura. Continuar la ejecución usa el último estado vivo; editar el código o reiniciar crea una nueva corrida. En METRICS\_ONLY la interfaz informa que no hay navegación completa disponible. Los grafos se derivan del snapshot y no constituyen una estructura de memoria adicional de la máquina.

## 14 Invariantes y criterios de aceptación

- Mismo programa, configuración y comandos producen la misma secuencia lógica, excepto wall time.

- Solo RUNNING admite otra transición; un estado terminal permanece inspeccionable.

- Toda HeapReference válida apunta a un objeto existente.

- Los ObjectId nunca cambian ni se reutilizan.

- allocatedSlots permanece fijo durante la vida del objeto.

- Inspeccionar el visualizador nunca demanda una referencia.

- Un thunk CBNeed se evalúa como máximo una vez y actualiza su dirección original.

- Las métricas no intervienen en las decisiones de la máquina.

- Una suspensión CBN nunca se actualiza.

- El GC solo elimina objetos inalcanzables y preserva observableOutcome.

- CoreNeed y STGNeed coinciden en el dominio de equivalencia definido.

### Aceptación

- La gramática, resolver y desazucarado aceptan los programas de la suite y rechazan los casos inválidos definidos.

- Las máquinas Core ejecutan correctamente las estrategias incluidas y producen resultados canónicos.

- Sharing, blackholes, ciclos estrictos, materialización y límites cuentan con tests explícitos.

- Las métricas satisfacen sus ecuaciones e invariantes y muestran unidades y alcance.

- La aplicación permite step, play, pause, back, reset y exportación sin modificar la semántica desde la vista.

- La suite experimental produce RunRecord reproducibles.

- El resultado se preserva con GC on y off.

- lowerToStg produce IR válida y la máquina STG supera las pruebas de equivalencia.

### Detalles ajustables durante implementación

| **Tema** | **Decisión diferida** |
| --- | --- |
| API | Nombres exactos de rutas y payloads, manteniendo las operaciones definidas. |
| Editor | Monaco, CodeMirror u otra biblioteca equivalente. |
| Gráficos | Biblioteca para grafos interactivos y gráficos experimentales. |
| Trazas | Tamaño de batches y frecuencia de checkpoints. |
| Persistencia | JSON inicial y posible migración a SQLite. |
| Interfaz | Layout de paneles, colores finales y animaciones. |
| Runtime | Campos auxiliares de frames, catálogo completo de ruleId y optimizaciones internas. |

Estas decisiones pueden cambiar sin reabrir la especificación, siempre que se preserven la semántica, las métricas, los formatos conceptuales y los criterios de aceptación.

## 15 Bibliografía inicial

Launchbury, J. (1993). A natural semantics for lazy evaluation. POPL, pp. 144–154. DOI: 10.1145/158511.158618.

<https://doi.org/10.1145/158511.158618>

Peyton Jones, S. L. (1992). Implementing lazy functional languages on stock hardware: The Spineless Tagless G-machine. Journal of Functional Programming, 2(2), 127–202.

<https://www.microsoft.com/en-us/research/publication/implementing-lazy-functional-languages-on-stock-hardware-the-spineless-tagless-g-machine/>

Peyton Jones, S. L., y Lester, D. R. (1992). Implementing functional languages: A tutorial. Prentice Hall.

<https://www.microsoft.com/en-us/research/publication/implementing-functional-languages-a-tutorial/>

de Vries, E. (2017). Visualizing lazy evaluation. Well-Typed. Referencia del visualizador y de ejemplos de demanda, sharing y acumuladores.

<https://www.well-typed.com/blog/2017/09/visualize-cbn/>

Marlow, S. (ed.). (2010). Haskell 2010 Language Report. Referencia de sintaxis y lenguaje, sin adoptar su estándar completo.

<https://www.haskell.org/onlinereport/haskell2010/>

Glasgow Haskell Compiler Project. GHC User’s Guide, apartados de profiling y estadísticas del RTS. La edición exacta se fija con la versión de GHC usada en E08.

<https://downloads.haskell.org/ghc/latest/docs/users_guide/profiling.html>

Estas fuentes fundamentan el diseño y orientan los experimentos. Las reglas, unidades y límites de este documento pertenecen al modelo didáctico del PI y no se presentan como una reproducción exacta de GHC.

## 16\. Revisión de arquitectura y alcance — versión 2.0

**Fecha:** 21 de octubre de 2026<br>**Naturaleza:** revisión aditiva y registro histórico de decisiones de diseño posteriores a la especificación técnica v1.1.<br>**Estado:** decisiones arquitectónicas acordadas; algunas capacidades todavía no están implementadas.<br>**Ámbito:** Proyecto Integrador «Visualizador y laboratorio experimental de estrategias de evaluación para una mini-lengua funcional».

### 16.1. Motivación, autoridad y trazabilidad

Durante el diseño y la implementación de B02 (frontend, AST y Core) y B03 (infraestructura del runtime), se concretaron o revisaron supuestos de la especificación técnica inicial para reducir el alcance sintáctico, preservar comparabilidad experimental y separar representación, evaluación y observación. Esta sección conserva el registro histórico de esas modificaciones; no pretende que las decisiones de v1.1 hayan sido las vigentes desde el comienzo.

**Criterio de vigencia:** en los puntos expresamente revisados, la versión 2.0 prevalece sobre v1.1. Para el contrato detallado de sintaxis y semántica superficial rige la especificación actual de la mini-lengua; para decisiones arquitectónicas rigen los ADR aceptados. Toda diferencia no resuelta se registra expresamente, sin sustituir silenciosamente los requisitos históricos. La terminación de B03 no prueba la corrección operacional de CBV/CBN/CBNeed ni la validez de las métricas experimentales.

### 16.2. Ajustes al alcance de la mini-lengua y su representación

| **Aspecto** | **Diseño inicial v1.1** | **Revisión adoptada** | **Justificación e impacto** |
| --- | --- | --- | --- |
| Bindings locales | Distinción entre let secuencial y let rec | Único let { ... } in ... con bindings mutuamente recursivos, representado por CoreLetRec (ADR-001) | Simplifica Core y conserva recursión directa y mutua. |
| Sintaxis | Alcance más amplio, incluido layout por indentación | Definiciones superiores separadas por líneas; let con llaves y punto y coma; sin layout implícito en la versión inicial | Reduce complejidad del lexer y parser sin impedir los experimentos seleccionados. |
| Punto de entrada | main obligatorio/especial | main es un binding global ordinario y opcional; se selecciona por defecto si existe | Permite compilar programas sin entrada, y distinguir compilación de selección/ejecución. |
| Pattern matching | case como construcción superficial | Patrones acotados en ecuaciones de funciones; compilación a CoreCase; case superficial diferido (ADR-002) | Mantiene inspección de constructores y ejemplos como map sin ampliar la gramática inicial. |
| Operadores y datos | Subconjunto inicial | Se mantiene el subconjunto realmente especificado e implementado en B02, incluidos !=, \> y \>=; listas Nil/Cons | Se evita prometer características externas al contrato de v0.1. |
| Demanda explícita | seq contemplada originalmente, no incluida en la minilengua v0.1 | **Se incorpora seq** como extensión aprobada | Permite enseñar WHNF, distinguir evaluación de estructura y contenido, y expresar folds estrictos. |

La numeración **2.0** corresponde a la especificación técnica global; la **minilengua v0.1** mantiene su propia numeración hasta que se publique una revisión explícita de su gramática.

### 16.3. Resolución de nombres, entornos y closures

**DEC-2.0-03 — Captura selectiva de variables libres locales.** Se confirma el scoping léxico y la resolución dinámica de referencias por nombre mediante una cadena de entornos, sin reescribir CoreVar con SymbolId (ADR-004 y ADR-005). El frontend comprueba nombres en Surface antes del desugaring y en Core después de él. La resolución estática verifica visibilidad; el runtime resuelve el binding efectivo.

Las closures retienen solo las **referencias** a variables libres **locales** requeridas por su función, nunca todo el entorno de definición. El análisis automático de variables libres debe respetar parámetros ligados, lambdas anidadas, CoreLetRec mutuamente recursivos, alternativas CoreCase, shadowing y nombres globales. Los globals son accesibles por separado a través del entorno global. El análisis deberá ser iterativo para evitar regresiones con Core profundo. Capturar una referencia no implica demandar el objeto referenciado ni memoizarlo.

**Motivación:** preservar el alcance léxico, evitar retención de memoria artificial y producir mediciones representativas de las capturas efectivamente necesarias. La identificación estable de bindings para visualización, si se requiere, no se deducirá exclusivamente del nombre de la variable.

### 16.4. Política global y semántica local de CBV

**DEC-2.0-02 — Globals direccionables y evaluados bajo demanda.** Para **CBV, CBN y CBNeed**, todos los bindings del CoreProgram se hacen direccionables antes de seleccionar la expresión de entrada, conservando visibilidad mutua y referencias adelantadas. **No se evalúan anticipadamente todos sus RHS.** Cada global se activa cuando la computación lo demanda.

Esta política es independiente de la estrategia de aplicación de funciones. En CBV, los argumentos y los bindings locales activados mantienen su evaluación estricta; en CBN las demandas repetidas no deben introducir memoización accidental; en CBNeed se implementará sharing con actualización de thunks en el hito correspondiente. No se presupone que las tres estrategias representen del mismo modo los globales pendientes.

Un global divergente no demandado no impide ejecutar un main independiente:

```text
loop = loop
main = 42
```

**DEC-2.0-04 — let local estricto en CBV.** Al ingresar en un CoreLetRec bajo CBV, se establece primero el alcance recursivo completo. Las lambdas se representan como valores funcionales sin ejecutar sus cuerpos; los demás RHS locales se inicializan estrictamente según una política determinista documentada por el evaluador, con detección de dependencias cíclicas activas. Bajo CBN/CBNeed, los bindings locales mantienen la semántica no estricta y sus reglas propias de reutilización.

**Motivación:** aislar la diferencia entre estrategias de evaluación de una política arbitraria de inicialización global; conservar ejemplos que contrasten un argumento o un binding local no utilizado en CBV frente a CBN/CBNeed. La detección detallada de ciclos/blackholes y las transiciones de actualización pertenecen a los hitos previstos para ello.

### 16.5. seq como primitiva de primera clase

**DEC-2.0-01 / DEC-2.0-05 — Incorporación y aplicación parcial de seq.** seq será un valor primitivo incorporado, **curried y de primera clase**, con comportamiento análogo en el subconjunto soportado a seq :: a -\> b -\> b de Haskell. Se admiten tanto seq a b como la aplicación parcial seq a, y el resultado parcial puede pasarse o almacenarse como función.

La regla semántica es: cuando una aplicación completa de seq deba producir su resultado, se demanda su **primer argumento hasta WHNF** y, satisfecha esa demanda, se continúa con el segundo. No se fuerza recursivamente el contenido de Cons ni el cuerpo de una closure por el mero hecho de llevarla a WHNF. Si el primer argumento diverge o falla, el resultado no llega al segundo. Bajo CBV, la evaluación estricta ordinaria de argumentos sigue aplicándose y puede demandar más trabajo que bajo las estrategias no estrictas.

**Representación recomendada:** seq se tratará como un identificador predefinido aceptado por la comprobación de nombres, y como un valor de función primitiva reconocido por el runtime. El frontend podrá producir CoreVar("seq"); **no se requiere ni se presupone CoreSeq como única representación**, ya que tal transformación de aplicaciones saturadas por sí sola no soportaría aplicaciones parciales ni su uso como argumento de orden superior. La introducción posterior de una instrucción Core interna optimizada queda abierta y requeriría preservar equivalencia semántica. El identificador predefinido seguirá las reglas ordinarias de shadowing léxico, sujetas a las reglas de nombres/bindings del lenguaje.

**Impacto técnico:** la extensión exige actualizar el contrato de nombres predefinidos, representación de funciones primitivas, aplicación curried, forcing a WHNF y tests de aplicación parcial, constructor WHNF, divergencia y comparación entre estrategias. La extensión mínima de frontend/Core se registrará dentro de las horas de reserva del Gantt vigente; las reglas que dependan de thunks/updates/sharing se completarán con los hitos que implementen esas estructuras. foldlStrict, foldrStrict y otros folds se expresarán como programas del lenguaje, no como operadores opacos del motor.

### 16.6. Infraestructura del runtime consolidada en B03

La implementación B03 introdujo RuntimeRef con valores inmediatos para enteros y booleanos y referencias a celdas con ObjectId estable; heap explícito con reserva de slots abstractos, reemplazos sin cambio de capacidad y lectura pasiva; entornos léxicos persistentes; closures con capturas locales; stack explícito de continuaciones; controles tipados; MachineState, InstrumentationState y ExecutionState; snapshots independientes para estructuras mutables; y la interfaz step(state, config) -\> TransitionResult con reglas auxiliares para los literales Core.

Los contadores operacionales de límites de ejecución pertenecen al estado de la máquina, mientras que las métricas experimentales se mantendrán separadas. Los modos de tracing no deben alterar la semántica. Un Return sin frames constituye solo un límite provisional de observación en B03, no la finalización canónica del programa.

El motor Core ejecutará las tres estrategias previstas. La máquina STG-like tendrá su IR y reglas propias, reutilizará infraestructura compatible y ejecutará CBNeed dentro del alcance del PI. Su implementación corresponde a B09–B10 y no se infiere de la existencia del enum MachineKind.STG.

### 16.7. Asuntos abiertos y su ubicación en el plan

| **Tema** | **Estado / hito previsto** |
| --- | --- |
| Inicialización recursiva completa, aplicación de closures, evaluación Core y observación canónica | B04 |
| Thunks, suspensión de cómputos, forcing repetido, sharing, updates y blackholes | B05, sin adelantar su implementación en B04 |
| Constructores, CoreCase, recursión sobre listas y matching sobre valores no-lista | B06; especificar el caso de error/default antes de implementar sus reglas |
| Métricas, distinción entre trabajo de fuente y administración del compilador, y procedencia | B07 y los hitos experimentales posteriores |
| Historial completo, checkpoints y replay | B08 |
| Lowering a STG-like y ejecución STG | B09–B10 |
| Contrato de entrada de estados externos y validación en el límite de API | Hito de integración de aplicación, antes de aceptar estados no confiables |

Las auditorías b02.8-audit.md y b03-audit.md se preservan como registros fechados. Los hallazgos resueltos se actualizan mediante follow-ups sin reescribir el estado histórico original. Las especificaciones y ADR vigentes deben corregir enlaces y referencias obsoletas en una tarea documental separada.

### 16.8. Impacto documental y de planificación

Esta revisión no altera de inmediato el Gantt B01–B19. La extensión seq se cubrirá provisionalmente con horas de reserva semanales y su costo real se registrará para una futura revisión solicitada por los docentes. La planificación sigue delimitando B04 como primer evaluador y observación canónica, y B05 como infraestructura de thunks, sharing y blackholes.

La especificación de la mini-lengua y los documentos vigentes deben actualizarse para incorporar seq, las reglas de globals y las restricciones de alcance; este anexo no sustituye por sí solo los tests ni la validación de los contratos. En el informe final, la motivación y las consecuencias experimentales de estas decisiones se desarrollarán en el capítulo de diseño/metodología y se relacionarán con las evidencias de ejecución.
