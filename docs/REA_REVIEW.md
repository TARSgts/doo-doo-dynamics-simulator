# REA identity, installation and limits

The user explicitly selected **[morluto/rea — Reverse Engineer Anything](https://github.com/morluto/rea)** after a name collision with `mytechnotalent/rea` was identified. The latter was not installed.

## Evidence inspected

- Repository metadata reports a public, non-fork project with homepage `https://rea.tools` and MIT licensing.
- Repository LICENSE and package metadata identify MIT and the `rea-agents` npm package; the npm package points back to the same GitHub repository.
- Source checkout inspected at commit `50822e1eff99136c5e5f7b1b1d3351c898937983`. Reviewed README, installation guide, package manifest, CLI entry point and prepare script. This was a bounded review, not a complete security audit, and the checkout is not claimed to be the published package's exact source revision.
- Installed published version `6.8.0`, compatible with the existing Node `24.22.1` runtime.
- npm's registry integrity value for the REA tarball is `sha512-9QDeRnGqEDzABZyr04eLnBXBv/c6I9/TWu/6M0MD4pEfkySI/BIgwTODIbAReX3C1x6hjw9+Jlx4A2yUSPZ9ww==`.
- `npm audit signatures` verified registry signatures for 176 installed packages and provenance attestations for 38. A registry signature is evidence about registry distribution, not a guarantee that package behavior is safe.

## Dependency adjustment

The published package pins Zod `4.4.3`. npm audit reported [GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5), patched in `4.6.6`. The local wrapper explicitly overrides Zod to `4.6.7`; the resulting locked install reports zero known npm audit vulnerabilities. The version command and doctor execute with this override. Full REA feature compatibility has not been tested.

The installed CLI is at `.tools/rea/node_modules/rea-agents/scripts/rea.mjs`. npm lifecycle scripts were disabled during installation. The repository source itself was not built or executed.

## Installation instructions

Upstream's standard guided command is `npx rea-agents@6.8.0 setup`. Because that bypasses this project's dependency override, use the project's reviewed wrapper when reproducing this installation:

```powershell
npm ci --prefix tools/rea --ignore-scripts --registry=https://registry.npmjs.org
npm audit --prefix tools/rea
npm audit signatures --prefix tools/rea
node tools/rea/node_modules/rea-agents/scripts/rea.mjs --version
node tools/rea/node_modules/rea-agents/scripts/rea.mjs setup --client codex --skill=false --dry-run --json
```

This installs the CLI under `tools/rea/node_modules` in a new checkout; the original working installation remains under `.tools/rea`. Both use the same reviewed manifest and lock. Do not use floating `@latest` for repeatable installation. Use an official Node runtime satisfying the package's `engines` requirement and an existing npm installation. The bundled runtime was used here; no system Node upgrade was made.

Only a setup **dry run** was performed. Its plan would add a Codex MCP registration and create a backup; it was not applied. REA's doctor confirms the runtime works but reports missing native-analysis providers and missing assistant registrations. No Ghidra, Hopper or IDA was installed, no Ansys installation was accessed, and native reverse-engineering capability is not configured. Those tools are unnecessary for the clean-room simulation workflow.
