using System.Diagnostics;

namespace FoundryLab;

public sealed class AdmissionException(string outcome) : Exception(outcome);

public sealed class Gate
{
    private readonly object sync = new();
    private readonly Queue<double> history = new();
    private readonly double rpm, window;
    private readonly Dictionary<string, int> limits, costs;
    private readonly int budget;
    private int sent;
    private double next;
    private readonly Func<double> clock;
    public Gate(double rpm, Dictionary<string, int> limits, Dictionary<string, int> costs, int budget, double window = 60, Func<double>? clock = null)
    {
        if (limits.Any(x => costs.GetValueOrDefault(x.Key) > x.Value)) throw new ArgumentException("Estimated request exceeds local token budget");
        this.rpm = rpm; this.limits = limits; this.costs = costs; this.budget = budget; this.window = window;
        var watch = Stopwatch.StartNew();
        this.clock = clock ?? (() => watch.Elapsed.TotalSeconds);
    }
    public async Task<double> AcquireAsync(double deadline, CancellationToken cancellation = default)
    {
        var began = clock();
        while (true)
        {
            double delay;
            lock (sync)
            {
                var now = clock();
                if (now >= deadline) throw new AdmissionException("deadline");
                if (sent >= budget) throw new AdmissionException("attempt_budget");
                while (history.Count > 0 && now - history.Peek() >= window) history.Dequeue();
                delay = Math.Max(0, next - now);
                if (history.Count > 0 && limits.Any(x => (long)(history.Count + 1) * costs.GetValueOrDefault(x.Key) > x.Value))
                    delay = Math.Max(delay, history.Peek() + window - now);
                if (delay <= 0)
                {
                    sent++; history.Enqueue(now);
                    if (rpm > 0) next = now + 60 / rpm;
                    return now - began;
                }
                if (now + delay >= deadline) throw new AdmissionException("deadline");
            }
            await Task.Delay(TimeSpan.FromSeconds(Math.Min(delay, .05)), cancellation);
        }
    }
}
