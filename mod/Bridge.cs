using System;
using System.IO;
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
    public const int Protocol = 1;

    private static readonly TimeSpan ConnectTimeout = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan AnswerTimeout = TimeSpan.FromSeconds(30);

    public static readonly string? PortArgument = CommandLineHelper.GetValue("slay-the-human-agent-port");

    private static TcpClient? _client;
    private static StreamReader? _reader;
    private static StreamWriter? _writer;
    private static int _lastId;

    public static bool IsOn => PortArgument is not null;

    /// <summary>Connects to the agent and checks its protocol version, the first time it is called in a run.</summary>
    public static async Task EnsureConnectedAsync(CancellationToken ct)
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
    public static async Task<int> AskAsync(JsonObject state, JsonArray actions, CancellationToken ct)
    {
        var id = ++_lastId;
        await SendAsync(new JsonObject { ["type"] = "decision", ["id"] = id, ["state"] = state, ["actions"] = actions });
        var answer = await ReceiveAsync(AnswerTimeout, ct);
        if ((string?)answer["type"] != "action")
        {
            throw new BridgeException($"expected action from the agent, got {answer["type"]?.ToJsonString() ?? "nothing"}");
        }
        if (answer["id"] is not JsonValue idValue || !idValue.TryGetValue<int>(out var answeredId) || answeredId != id)
        {
            throw new BridgeException($"the agent answered decision {answer["id"]?.ToJsonString()}, not {id}");
        }
        if (answer["index"] is not JsonValue indexValue || !indexValue.TryGetValue<int>(out var index) || index < 0 ||
            index >= actions.Count)
        {
            throw new BridgeException(
                $"the agent chose action {answer["index"]?.ToJsonString()}, not one of the {actions.Count} listed");
        }
        return index;
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
