# Adapter Template

A ready-to-copy template is available at:

```text
templates/adapter_template.py
```

There is also a non-registered example at:

```text
qlf_core/adapters/example_adapter.py
```

To create a new adapter:

1. Copy `templates/adapter_template.py` into `qlf_core/adapters/<name>.py`.
2. Rename `MyAdapter` and set `name`, `description`, and `source_scope`.
3. Implement `detect()` first.
4. Register it in `qlf_core/adapters/registry.py`.
5. Test with `python qlf.py adapters` and `python qlf.py sources --instance ...`.
6. Add `extract()` and `inject()` only after real test data exists.

Do not add adapters for general mod language files. That belongs to MLF, not QLF.
