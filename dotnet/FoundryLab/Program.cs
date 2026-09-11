using FoundryLab;

try
{
    if (args.Length == 0 || args[0] is "--help" or "-h")
    {
        Console.WriteLine("Foundry throttling lab (.NET 10). No --live means local HTTP simulation.\n" +
            "run [--target aoai|claude|mai|image] [--scenario preflight|baseline|burst|retry|paced|guarded]\n" +
            "    [--config PATH] [--live] [--out runs] [--requests 6] [--concurrency 6]\n" +
            "    [--client-rpm 60] [--max-attempts 3] [--attempt-budget 18] [--deadline 30]\n" +
            "    [--output-limit 128] [--input-estimate 128] [--prompt-repeat 1]\n" +
            "    [--client-token-budget N] [--client-input-budget N] [--client-output-budget N]\n" +
            "    [--mock-axis rpm|tpm|itpm|otpm|capacity] [--mock-window 2]\n" +
            "compare RUN-DIRECTORIES... [--out comparison.md]");
        return 0;
    }
    if (args[0] == "run") await Runner.RunAsync(Options.Parse(args[1..]));
    else if (args[0] == "compare")
    {
        var paths = new List<string>();
        var output = "comparison.md";
        for (int i = 1; i < args.Length; i++)
            if (args[i] == "--out" && i + 1 < args.Length) output = args[++i];
            else if (args[i].StartsWith("--")) throw new ArgumentException("Unknown option");
            else paths.Add(args[i]);
        Evidence.Compare(paths.ToArray(), output);
    }
    else throw new ArgumentException("Unknown command");
    return 0;
}
catch (Exception error) when (error is ArgumentException or InvalidOperationException or KeyNotFoundException
    or IOException or UnauthorizedAccessException or System.Text.Json.JsonException or FormatException or OverflowException)
{
    Console.Error.WriteLine("Lab configuration or file error. Check arguments, config, environment variables, and output permissions.");
    return 2;
}
