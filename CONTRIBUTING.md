# Contributing

Use **US English** for documentation, code comments, examples, prompts, CLI help, console messages, and reports.

Keep provider-specific claims linked to Microsoft documentation. Distinguish documented behavior, local implementation choices, and measured results. Label local HTTP mock data clearly and do not present it as a Foundry benchmark.

Before submitting a change, run:

```powershell
python -B -m unittest discover -s python/tests -v
python -B python/lab.py run --config python/config.example.json --scenario preflight
dotnet test dotnet/FoundryLab.Tests
dotnet run --project dotnet/FoundryLab -- run --scenario preflight
```

Do not commit credentials, local configuration, real incident data, or new live run artifacts. Update relative document links when renaming a file.
