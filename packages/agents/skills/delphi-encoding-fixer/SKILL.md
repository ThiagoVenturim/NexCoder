---
name: delphi-encoding-fixer
description: String encoding and character set compatibility rules for legacy Delphi applications operating with CP1252 and UTF-8.
user-invocable: true
---

# Delphi Encoding Fixer

Rules for maintaining string encoding integrity, preventing mojibake, and handling UTF-8 / CP1252 conversions in Delphi 2007 and legacy Object Pascal.

## Guidelines
1. **AnsiString vs. UTF-8**:
   Delphi 2007 defaults to Windows-1252 ANSI strings. When interfacing with external REST APIs, JSON endpoints, or UTF-8 databases:
   - Use explicit conversion routines: `Utf8ToAnsi()` and `AnsiToUtf8()`.
   - Never perform double encoding conversions on text payloads.
2. **Database String Parameters**:
   - Ensure string parameters passed into ADO queries respect the destination database collation.
   - For NVARCHAR / WideString database columns, bind parameters as `ftWideString` to avoid byte truncation.
