using System.Globalization;

namespace FoundryLab;

public sealed class Options
{
    public string Target { get; set; } = "aoai";
    public string Scenario { get; set; } = "preflight";
    public string Config { get; set; } = Path.Combine(AppContext.BaseDirectory, "config.example.json");
    public string Out { get; set; } = "runs";
    public string MockAxis { get; set; } = "rpm";
    public bool Live { get; set; }
    public int Requests { get; set; } = 6;
    public int Concurrency { get; set; } = 6;
    public int MaxAttempts { get; set; } = 3;
    public int AttemptBudget { get; set; } = 18;
    public int OutputLimit { get; set; } = 128;
    public int InputEstimate { get; set; } = 128;
    public int PromptRepeat { get; set; } = 1;
    public int TokenBudget { get; set; }
    public int InputBudget { get; set; }
    public int OutputBudget { get; set; }
    public double Deadline { get; set; } = 30;
    public double ClientRpm { get; set; } = 60;
    public double MockWindow { get; set; } = 2;
    public int Count => Scenario == "preflight" ? 1 : Requests;
    public int Workers => Scenario is "preflight" or "baseline" ? 1 : Concurrency;
    public int Attempts => Scenario is "retry" or "paced" or "guarded" ? MaxAttempts : 1;
    public double Rpm => Scenario is "baseline" or "paced" or "guarded" ? ClientRpm : 0;
    public Dictionary<string, int> Costs => new() { ["tokens"] = InputEstimate + OutputLimit, ["input"] = InputEstimate, ["output"] = OutputLimit };
    public Dictionary<string, int> Limits => Scenario == "guarded"
        ? new Dictionary<string, int> { ["tokens"] = TokenBudget, ["input"] = InputBudget, ["output"] = OutputBudget }.Where(x => x.Value > 0).ToDictionary()
        : new();

    public void Validate()
    {
        if (!new[] { "aoai", "claude", "mai", "image" }.Contains(Target)
            || !new[] { "preflight", "baseline", "burst", "retry", "paced", "guarded" }.Contains(Scenario)
            || !new[] { "rpm", "tpm", "itpm", "otpm", "capacity" }.Contains(MockAxis)
            || Requests is < 1 or > 200 || Concurrency is < 1 or > 20 || MaxAttempts is < 1 or > 5
            || AttemptBudget is < 1 or > 1000 || OutputLimit is < 1 or > 32768
            || InputEstimate is < 1 or > 1000000 || PromptRepeat is < 1 or > 200
            || TokenBudget < 0 || InputBudget < 0 || OutputBudget < 0
            || !double.IsFinite(Deadline) || Deadline is < 1 or > 600
            || !double.IsFinite(ClientRpm) || ClientRpm <= 0
            || !double.IsFinite(MockWindow) || MockWindow is < .1 or > 60)
            throw new ArgumentException("Parameters are outside the lab limits");
    }

    public static Options Parse(string[] args)
    {
        var options = new Options();
        for (int i = 0; i < args.Length; i++)
        {
            var key = args[i];
            if (key == "--live") { options.Live = true; continue; }
            if (++i >= args.Length) throw new ArgumentException("Missing option value");
            var value = args[i];
            int Int() => int.Parse(value, CultureInfo.InvariantCulture);
            double Double() => double.Parse(value, CultureInfo.InvariantCulture);
            switch (key)
            {
                case "--target": options.Target = value; break;
                case "--scenario": options.Scenario = value; break;
                case "--config": options.Config = value; break;
                case "--out": options.Out = value; break;
                case "--mock-axis": options.MockAxis = value; break;
                case "--requests": options.Requests = Int(); break;
                case "--concurrency": options.Concurrency = Int(); break;
                case "--max-attempts": options.MaxAttempts = Int(); break;
                case "--attempt-budget": options.AttemptBudget = Int(); break;
                case "--output-limit": options.OutputLimit = Int(); break;
                case "--input-estimate": options.InputEstimate = Int(); break;
                case "--prompt-repeat": options.PromptRepeat = Int(); break;
                case "--client-token-budget": options.TokenBudget = Int(); break;
                case "--client-input-budget": options.InputBudget = Int(); break;
                case "--client-output-budget": options.OutputBudget = Int(); break;
                case "--deadline": options.Deadline = Double(); break;
                case "--client-rpm": options.ClientRpm = Double(); break;
                case "--mock-window": options.MockWindow = Double(); break;
                default: throw new ArgumentException("Unknown option");
            }
        }
        options.Validate();
        return options;
    }
}
