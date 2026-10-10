"""The agent's side of the bridge to the game. docs/protocol.md defines the messages."""

import json
import socket

PROTOCOL = 2


class BridgeError(Exception):
    """The game broke the protocol, or the connection ended before the run did."""


class Bridge:
    """Listens on 127.0.0.1 for the game's one connection, then answers its decisions."""

    def __init__(self, accept_timeout: float = 120.0) -> None:
        self._server = socket.create_server(("127.0.0.1", 0))
        self._server.settimeout(accept_timeout)
        self.port: int = self._server.getsockname()[1]
        self._file = None

    def accept(self) -> None:
        """Waits for the game to connect and checks it speaks the same protocol version."""
        try:
            conn, _ = self._server.accept()
        except TimeoutError as e:
            raise BridgeError(f"the game did not connect within {self._server.gettimeout():g} seconds") from e
        finally:
            self._server.close()
        # No read timeout: the game spends minutes outside combat between decisions. If it hangs, tools/run.sh stops
        # it, and the closed connection ends the run here.
        conn.settimeout(None)
        self._file = conn.makefile("rw", encoding="utf-8", newline="\n")
        self._send({"type": "hello", "protocol": PROTOCOL})
        hello = self._receive()
        if hello.get("type") != "hello":
            raise BridgeError(f"expected hello, got {hello.get('type')!r}")
        if hello.get("protocol") != PROTOCOL:
            raise BridgeError(f"protocol mismatch: the game speaks {hello.get('protocol')}, the agent {PROTOCOL}")

    def run(self, choose) -> dict:
        """Answers each decision with choose(decision) until the run ends, and returns the run_end message.

        choose returns an index into the decision's actions, or for a card_select decision a list of indices into
        its cards. The game, not the agent, checks the answer is legal.
        """
        while True:
            message = self._receive()
            kind = message.get("type")
            if kind == "run_end":
                self._file.close()
                return message
            if kind != "decision":
                raise BridgeError(f"expected decision or run_end, got {kind!r}")
            answer = choose(message)
            key = "indices" if isinstance(answer, list) else "index"
            self._send({"type": "action", "id": message["id"], key: answer})

    def _send(self, message: dict) -> None:
        try:
            self._file.write(json.dumps(message) + "\n")
            self._file.flush()
        except OSError as e:
            raise BridgeError(f"lost the connection to the game: {e}") from e

    def _receive(self) -> dict:
        try:
            line = self._file.readline()
        except OSError as e:
            # A dropped connection shows up as a reset on Windows, not as end of file.
            raise BridgeError(f"the game closed the connection before the run ended: {e}") from e
        if not line:
            raise BridgeError("the game closed the connection before the run ended")
        try:
            message = json.loads(line)
        except json.JSONDecodeError as e:
            raise BridgeError(f"the game sent a line that is not JSON: {line[:200]!r}") from e
        if not isinstance(message, dict):
            raise BridgeError(f"the game sent a message that is not an object: {line[:200]!r}")
        return message
