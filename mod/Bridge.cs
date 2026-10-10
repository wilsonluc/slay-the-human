using System;
using System.IO;
using System.Linq;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using MegaCrit.Sts2.Core.Helpers;
using MegaCrit.Sts2.Core.Logging;

namespace SlayTheHuman;

/// <summary>
/// The mod's side of the bridge to the Python agent. docs/protocol.md defines the messages. On only when the game was
/// launched with --slay-the-human-agent-port=&lt;port&gt;.
/// </summary>
internal static class Bridge
{
    /// <summary>The protocol version in docs/protocol.md. tools/test.sh checks the agent uses the same.</summary>
    public const int Protocol = 3;

    private static readonly TimeSpan ConnectTimeout = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan AnswerTimeout = TimeSpan.FromSeconds(30);

    public static readonly string? PortArgument = CommandLineHelper.GetValue("slay-the-human-agent-port");

    private static TcpClient? _client;
    private static StreamReader? _reader;
    private static StreamWriter? _writer;
    private static int _lastId;
    private static readonly SemaphoreSlim Turn = new(1, 1);

    public static bool IsOn => PortArgument is not null;

    /// <summary>Connects to the agent and checks its protocol version, at the run's first decision.</summary>
    private static async Task EnsureConnectedAsync(CancellationToken ct)
    {
        if (_client is not null)
        {
            return;
        }
        if (!int.TryParse(PortArgument, out var port))
        {
            throw new BridgeException($"--slay-the-human-agent-port is not a port number: '{PortArgument}'");
        }
        var client = new TcpClient();
        using (var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct))
        {
            timeout.CancelAfter(ConnectTimeout);
            try
            {
                await client.ConnectAsync("127.0.0.1", port, timeout.Token);
            }
            catch (Exception e) when (e is SocketException || (e is OperationCanceledException && !ct.IsCancellationRequested))
            {
                client.Dispose();
                throw new BridgeException($"could not connect to the agent on port {port}: {e.Message}");
            }
        }
        _client = client;
        var stream = client.GetStream();
        _reader = new StreamReader(stream, new UTF8Encoding(false));
        _writer = new StreamWriter(stream, new UTF8Encoding(false)) { NewLine = "\n", AutoFlush = true };
        await SendAsync(new JsonObject { ["type"] = "hello", ["protocol"] = Protocol });
        var hello = await ReceiveAsync(ConnectTimeout, ct);
        if ((string?)hello["type"] != "hello")
        {
            throw new BridgeException($"expected hello from the agent, got {hello["type"]?.ToJsonString() ?? "nothing"}");
        }
        var theirs = hello["protocol"]?.ToJsonString();
        if (theirs != Protocol.ToString())
        {
            throw new BridgeException($"protocol mismatch: the agent speaks {theirs}, the mod {Protocol}");
        }
        Log.Info($"[{ModEntry.Id}] connected to the agent on port {port}");
    }

    /// <summary>Sends a decision and returns the agent's answer, an index checked to be within the actions.</summary>
    public static async Task<int> AskIndexAsync(string kind, JsonObject state, JsonArray actions, CancellationToken ct)
    {
        var answer = await AskAsync(kind, state, actions, ct);
        if (answer["index"] is not JsonValue indexValue || !indexValue.TryGetValue<int>(out var index) || index < 0 ||
            index >= actions.Count)
        {
            throw new BridgeException(
                $"the agent chose action {answer["index"]?.ToJsonString()}, not one of the {actions.Count} listed");
        }
        return index;
    }

    /// <summary>
    /// Sends a card_select decision and returns the agent's answer: distinct indices into the cards, checked to number
    /// between min and max.
    /// </summary>
    public static async Task<int[]> AskIndicesAsync(JsonObject state, int cards, int min, int max, CancellationToken ct)
    {
        var answer = await AskAsync("card_select", state, new JsonArray(), ct);
        int[] indices;
        try
        {
            indices = (answer["indices"] as JsonArray)?.Select(node => node!.GetValue<int>()).ToArray()
                ?? throw new BridgeException("the agent answered a card_select without indices");
        }
        catch (Exception e) when (e is InvalidOperationException or FormatException or NullReferenceException)
        {
            throw new BridgeException($"the agent's indices are not whole numbers: {answer["indices"]?.ToJsonString()}");
        }
        if (indices.Any(i => i < 0 || i >= cards) || indices.Distinct().Count() != indices.Length ||
            indices.Length < min || indices.Length > max)
        {
            throw new BridgeException(
                $"the agent selected cards {answer["indices"]?.ToJsonString()}, not {min} to {max} distinct of the {cards} offered");
        }
        return indices;
    }

    /// <summary>
    /// One question and its answer. The game can ask for a choice while another is waiting (a relic's card selection
    /// when a room opens, for example), so questions take turns: the protocol has one question in flight at a time.
    /// </summary>
    private static async Task<JsonObject> AskAsync(string kind, JsonObject state, JsonArray actions, CancellationToken ct)
    {
        await Turn.WaitAsync(ct);
        try
        {
            await EnsureConnectedAsync(ct);
            var id = ++_lastId;
            await SendAsync(new JsonObject
            {
                ["type"] = "decision", ["id"] = id, ["kind"] = kind, ["state"] = state, ["actions"] = actions,
            });
            var answer = await ReceiveAsync(AnswerTimeout, ct);
            if ((string?)answer["type"] != "action")
            {
                throw new BridgeException($"expected action from the agent, got {answer["type"]?.ToJsonString() ?? "nothing"}");
            }
            if (answer["id"] is not JsonValue idValue || !idValue.TryGetValue<int>(out var answeredId) || answeredId != id)
            {
                throw new BridgeException($"the agent answered decision {answer["id"]?.ToJsonString()}, not {id}");
            }
            return answer;
        }
        finally
        {
            Turn.Release();
        }
    }

    /// <summary>Tells the agent how the run ended and closes the connection. Does nothing when not connected.</summary>
    public static void SendRunEnd(bool isVictory, int floor)
    {
        if (_writer is null)
        {
            return;
        }
        try
        {
            _writer.WriteLine(new JsonObject
            {
                ["type"] = "run_end", ["outcome"] = isVictory ? "win" : "loss", ["floor"] = floor,
            }.ToJsonString());
        }
        catch (IOException e)
        {
            Log.Error($"[{ModEntry.Id}] could not send run_end to the agent: {e.Message}");
        }
        _client?.Dispose();
        _client = null;
        _writer = null;
        _reader = null;
    }

    private static async Task SendAsync(JsonObject message)
    {
        try
        {
            await _writer!.WriteLineAsync(message.ToJsonString());
        }
        catch (IOException e)
        {
            throw new BridgeException($"lost the connection to the agent: {e.Message}");
        }
    }

    private static async Task<JsonObject> ReceiveAsync(TimeSpan timeout, CancellationToken ct)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        deadline.CancelAfter(timeout);
        string? line;
        try
        {
            line = await _reader!.ReadLineAsync(deadline.Token);
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            throw new BridgeException($"the agent did not answer within {timeout.TotalSeconds:g} seconds");
        }
        catch (IOException e)
        {
            throw new BridgeException($"lost the connection to the agent: {e.Message}");
        }
        if (line is null)
        {
            throw new BridgeException("the agent closed the connection");
        }
        try
        {
            return JsonNode.Parse(line) as JsonObject
                ?? throw new BridgeException($"the agent sent a message that is not an object: {Shorten(line)}");
        }
        catch (JsonException)
        {
            throw new BridgeException($"the agent sent a line that is not JSON: {Shorten(line)}");
        }
    }

    private static string Shorten(string line) => line.Length <= 200 ? line : line[..200] + "...";
}

/// <summary>The agent or the connection broke the protocol. It ends the run as an error.</summary>
internal sealed class BridgeException(string message) : Exception(message);
