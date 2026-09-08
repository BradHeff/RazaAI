---
razaai_context: false
---

# RazaAI Curated Project Knowledge

Put operator-maintained Markdown reference files in this directory.

Examples:

- `FortiGate.md`
- `School-Network.md`
- `FortiClient-EMS.md`
- `Document-Standards.md`
- `Policies.md`

Optional frontmatter:

```text
---
razaai_context: true
scope: networking
priority: 80
---
```

`scope` can be any useful label. Common values include `branding`,
`documents`, `organisation`, `networking`, `cybersecurity`, `policy`,
`microsoft`, `linux`, and `general`.

Higher `priority` values make the document more likely to be included when
multiple local references match.

For document branding, create a local `BRANDING.md` in the project root and set the organisation name and colours. This file is ignored by Git.
