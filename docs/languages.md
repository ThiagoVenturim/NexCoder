# Programming Language Support: Grammars and AST Parsers

Real-world enterprise systems are rarely written in a single language. They combine modern microservices (Python, Go, TypeScript), legacy core monoliths (Delphi, Object Pascal, Java, C++), and enterprise business systems.

`faccoder-code-intel` features a modular AST parser architecture capable of extracting symbols, signatures, call graphs, and UI bindings across multiple languages.

---

## Supported Language Grammars

| Language | Parser Technology | Symbols Extracted | Specific Capabilities |
|---|---|---|---|
| **Python** | Tree-sitter | Modules, classes, methods, functions, decorators, imports | Async/await, type annotations, enclosing class context |
| **TypeScript / JavaScript** | Tree-sitter | Classes, interfaces, methods, arrow functions, exports | Type aliases, JSX/TSX components, default exports |
| **Go** | Tree-sitter | Packages, structs, interfaces, methods, functions | Receiver types, struct tags, goroutine invocations |
| **Java** | Tree-sitter | Packages, classes, interfaces, records, methods, annotations | Generic type parameters, Spring/Jakarta annotations |
| **C / C++** | Tree-sitter | Namespaces, classes, structs, functions, templates | Header/implementation separation, macros |
| **Rust** | Tree-sitter | Modules, structs, traits, impl blocks, functions, macros | Trait implementations, visibility qualifiers |
| **Object Pascal / Delphi** | Custom Lexer & AST | Units, interfaces, implementations, classes, methods, DFM forms | DFM component bindings, Win1252 strings, memory leak audit |

---

## The Abstract Symbol Model

Regardless of source language, `faccoder-code-intel` maps parsed entities into a unified `Symbol` model:

```python
class Symbol(BaseModel):
    id: str  # Unique fully-qualified symbol identifier
    name: str  # Symbol identifier name (e.g. "charge_card")
    symbol_type: SymbolType  # FUNCTION, METHOD, CLASS, INTERFACE, ENUM, VARIABLE
    file_path: str  # Relative file path inside repository
    line_start: int  # 1-indexed start line
    line_end: int  # 1-indexed end line
    signature: str  # Parameter list, return types, qualifiers
    enclosing_symbol: str | None  # Parent class or module ID
    docstring: str | None  # Extracted documentation or comment header
    language: str  # Standard language identifier
```

This unified representation enables cross-language RAG, GraphRAG community detection, and consistent agent reasoning.

---

## Dedicated Delphi / Object Pascal Parser

Legacy systems written in Delphi (e.g. Delphi 7, Delphi 2007, modern RAD Studio) present unique parsing challenges that standard off-the-shelf parsers fail to handle:
- **Interface vs Implementation Separation**: Method declarations in the `interface` section must be correlated with implementations in the `implementation` section.
- **DFM Form Bindings**: Event handlers (e.g. `Button1Click`) are declared in code but wired to buttons, grids, and queries inside binary or text `.dfm` form definition files.
- **Case-Insensitive Syntax**: Object Pascal is case-insensitive, requiring normalized symbol IDs.

`faccoder-code-intel` includes a specialized parser:

```python
from faccoder_code_intel.parsers import DelphiParser

parser = DelphiParser()
symbols = parser.parse_file("uBillingService.pas", dfm_content=dfm_text)

for sym in symbols:
    print(f"[{sym.symbol_type.value}] {sym.name} (Lines {sym.line_start}-{sym.line_end})")
    if sym.ui_bindings:
        print(f"  Bound to UI components: {sym.ui_bindings}")
```

---

## Adding a New Language Grammar

To add support for a new language:
1. Implement the `BaseParser` interface in `faccoder_code_intel.parsers`.
2. Map the language's Tree-sitter grammar node types to `SymbolType`.
3. Extract enclosing context and typed signatures.
4. Register the parser in `ParserRegistry`.
