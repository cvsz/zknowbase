# Agent System Rules

## Language & Communication Guidelines
- **Primary Response Language:** Always communicate, explain, and write documentation/comments in **Thai** (ภาษาไทย).
- **Code & Configuration:** All source code, terminal commands, configuration files (JSON, YAML, ENV, etc.), variable names, and code syntax MUST remain in **English**.
- **Technical Terms:** Keep standard software architecture and programming jargon in English (e.g., *refactor*, *middleware*, *dependency injection*) to maintain accuracy.

## Response Behavior
1. **Explanations:** Provide all explanations, step-by-step guidance, and trade-off analyses in **Thai**.
2. **Code Blocks:** Write clean, executable code entirely in **English**. Do not translate programming keywords, variables, or API routes into Thai.
3. **Inline Comments:** Write comments within code blocks in **Thai** if they explain logic to the developer, but keep the code itself standard English.

## Repository Safety Baseline
- Preserve repository-specific architecture and existing instructions.
- Prefer the smallest safe diff and repository-native validation commands.
- Never commit secrets, credentials, private keys, production tokens, sensitive data, or secret-bearing artifacts.
- Never disable tests, security checks, lint/type checks, branch protection, or policy gates merely to make CI pass.
- Verify relevant checks before claiming completion and keep production-readiness claims evidence-based.
- Do not force-push, rewrite shared history, or merge failing changes unless explicitly authorized and permitted by repository policy.
