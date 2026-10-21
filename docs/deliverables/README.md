# Deliverables

Formal deliverable documents for the AI use-case programme, in the same
shape as the other workstream D playbooks.

| File | Deliverable |
|---|---|
| `D23-Playbook-AI-Bid-Analyser.docx` | D23. Playbook for Implemented AI Use-Cases, AI Bid Analyser |

## Regenerating

The document is generated, not hand-edited, so it can be rebuilt after a
change rather than drifting. Content and layout live in `doc.js`;
`build.js` holds the formatting helpers.

```bash
cd docs/deliverables
npm install docx          # only if require('docx') fails
node doc.js
```

If someone edits the .docx by hand, fold the change back into `doc.js`
or the next regeneration will silently drop it.

## Note on section 6

The equivalent section in the Water Demand playbook covers MLflow runs,
registered model versions and training metrics. This use case has none
of those: the comparison is deterministic and there is no trained model.
Section 6 says so plainly and covers what actually governs the output,
which is a set of named thresholds plus the guardrails on the two
language-model features. It is a deliberate departure from the template
rather than an omission.
