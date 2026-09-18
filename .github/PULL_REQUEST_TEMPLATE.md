## What changes and why

<!-- One paragraph. What problem does this solve for someone using the lab? -->

## Type of change

- [ ] Documentation or slides
- [ ] Python engine
- [ ] C# / .NET engine
- [ ] Browser UI or local server
- [ ] Container or infrastructure
- [ ] CI

## Validation

<!-- Paste the commands you ran and their result. -->

```
python -B -m unittest discover -s python/tests
dotnet test dotnet/FoundryLab.Tests --configuration Release
node --test demo/test_ui.cjs
python scripts/validate_parity.py
```

## Checklist

- [ ] US English in documentation, code comments, CLI help and console messages
- [ ] Provider specific claims are linked to Microsoft documentation, and `docs/SOURCES.md` is updated if a new one is used
- [ ] Local simulator data is labeled as synthetic and not presented as a Foundry benchmark
- [ ] No credentials, endpoints, request IDs, real incident data or live run artifacts are committed
- [ ] Both engines still produce comparable evidence, if the change touches either one
- [ ] Relative document links still resolve, if files were renamed or moved
