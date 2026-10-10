"""The agent's side of the bridge to the game. docs/protocol.md defines the messages."""

import json
import socket

PROTOCOL = 4


class BridgeError(Exception):
    """The game broke the protocol, or the connection ended."""


class Bridge:
    """Listens on 127.0.0.1 for one game's connection, which lasts for the game process: the agent starts each run."""

    def __init__(self, accept_timeout: float = 120.0) -> None:
        self._server = socket.create_server(("127.0.0.1", 0))
        self._server.settimeout(accept_timeout)
        self.port: int = self._server.getsockname()[1]
        self._conn = None
        self._file = None
        self.hello: dict = {}

    def accept(self) -> dict:
        """Waits for the game to connect, checks it speaks the same protocol version, and returns its hello."""
        try:
            conn, _ = self._server.accept()
        except TimeoutError as e:
            raise BridgeError(f"the game did not connect within {self._server.gettimeout():g} seconds") from e
        finally:
            self._server.close()
        self._conn = conn
        self._file = conn.makefile("rw", encoding="utf-8", newline="\n")
        self._send({"type": "hello", "protocol": PROTOCOL})
        hello = self.receive()
        if hello.get("type") != "hello":
            raise BridgeError(f"expected hello, got {hello.get('type')!r}")
        if hello.get("protocol") != PROTOCOL:
            raise BridgeError(f"protocol mismatch: the game speaks {hello.get('protocol')}, the agent {PROTOCOL}")
        self.hello = hello
        return hello

    def start(self, seed: str | None, character: str, timeout: float | None = None) -> None:
        """Waits for the game to be ready at the main menu, then starts a run."""
        ready = self.receive(timeout)
        if ready.get("type") != "ready":
            raise BridgeError(f"expected ready, got {ready.get('type')!r}")
        self._send({"type": "start", "seed": seed, "character": character})

    def answer(self, decision: dict, answer: int | list[int]) -> None:
        """Answers a decision: an index into its actions, or for a card_select a list of indices into its cards."""
        key = "indices" if isinstance(answer, list) else "index"
        self._send({"type": "action", "id": decision["id"], key: answer})

    def next(self, timeout: float | None = None) -> dict:
        """The run's next message: a decision, or run_end."""
        message = self.receive(timeout)
        if message.get("type") not in ("decision", "run_end"):
            raise BridgeError(f"expected decision or run_end, got {message.get('type')!r}")
        return message

    def play(self, choose, timeout: float | None = None) -> dict:
        """Answers each decision with choose(decision) until the run ends, and returns the run_end message."""
        while (message := self.next(timeout))["type"] == "decision":
            self.answer(message, choose(message))
        return message

    def close(self) -> None:
        """Closes the connection; the game quits when it next reaches the main menu."""
        if self._file:
            self._file.close()
            self._conn.close()
            self._file = None

    def receive(self, timeout: float | None = None) -> dict:
        """One message. timeout in seconds, None to wait as long as it takes; a timeout raises TimeoutError."""
        self._conn.settimeout(timeout)
        try:
            line = self._file.readline()
        except TimeoutError:
            raise
        except OSError as e:
            # A dropped connection shows up as a reset on Windows, not as end of file.
            raise BridgeError(f"the game closed the connection: {e}") from e
        if not line:
            raise BridgeError("the game closed the connection")
        try:
            message = json.loads(line)
        except json.JSONDecodeError as e:
            raise BridgeError(f"the game sent a line that is not JSON: {line[:200]!r}") from e
        if not isinstance(message, dict):
            raise BridgeError(f"the game sent a message that is not an object: {line[:200]!r}")
        return message

    def _send(self, message: dict) -> None:
        try:
            self._file.write(json.dumps(message) + "\n")
            self._file.flush()
        except OSError as e:
            raise BridgeError(f"lost the connection to the game: {e}") from e
