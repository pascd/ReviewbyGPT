# Security Policy

## Supported Versions

ReviewbyGPT is a small, actively-maintained project currently at its first public release. Only the
latest release (and the `master` branch) receive security fixes.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅        |
| < 0.1   | ❌        |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, report it privately by emailing **pedro.afonso.cardoso.dias@gmail.com** with:

- A description of the vulnerability and its potential impact.
- Steps to reproduce it (a minimal PDF/config that triggers it, if applicable).
- Any suggested fix or mitigation, if you have one.

You should expect an acknowledgement within a few days. Once the issue is confirmed, a fix will be
prioritized and a new release published; you'll be credited in the fix's changelog entry unless you
ask not to be.

## Scope

ReviewbyGPT parses PDFs and untrusted LLM responses, and executes local file/Excel operations based on
that content. Reports involving PDF parsing, response-parsing regexes, or file-path handling are all in
scope. Reports about a third-party LLM backend you've chosen to point ReviewbyGPT at (e.g. Ollama itself)
should go to that project instead.
