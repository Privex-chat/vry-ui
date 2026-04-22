import re
import websockets
import websockets.client
import ssl
import base64
import json
import asyncio
from colr import color


class Ws:
    def __init__(self, lockfile, Requests, cfg, colors, hide_names, server, rpc=None):
        self.lockfile = lockfile
        self.Requests = Requests
        self.ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        self.id_seen = []
        self.cfg = cfg
        self.player_data = {}
        self.messages = 0
        self.colors = colors
        self.hide_names = hide_names
        self.message_history = []
        self.up = "\033[A"
        self.chat_limit = cfg.chat_limit
        self.server = server
        self.rpc = rpc if self.cfg.get_feature_flag("discord_rpc") else None

        # Cancellation support
        self._shutdown = False
        self._current_websocket = None

    def set_player_data(self, player_data):
        self.player_data = player_data

    def request_shutdown(self):
        """Signal the websocket to close gracefully"""
        self._shutdown = True
        if self._current_websocket:
            try:
                asyncio.create_task(self._current_websocket.close())
            except Exception:
                pass

    async def recconect_to_websocket(self, initial_game_state):
        """Connect to websocket with proper cancellation handling"""
        self._shutdown = False
        local_headers = {
            'Authorization': 'Basic ' + base64.b64encode(
                ('riot:' + self.lockfile['password']).encode()
            ).decode()
        }
        url = f"wss://127.0.0.1:{self.lockfile['port']}"

        try:
            async with websockets.connect(
                url,
                ssl=self.ssl_context,
                extra_headers=local_headers,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
            ) as websocket:
                self._current_websocket = websocket

                await websocket.send('[5, "OnJsonApiEvent_chat_v4_presences"]')
                if self.cfg.get_feature_flag("game_chat"):
                    await websocket.send('[5, "OnJsonApiEvent_chat_v6_messages"]')

                while not self._shutdown:
                    try:
                        response = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=2.0
                        )
                        result = self.handle(response, initial_game_state)
                        if result is not None:
                            return result
                    except asyncio.TimeoutError:
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        if self._shutdown:
                            return initial_game_state
                        raise
                    except asyncio.CancelledError:
                        return initial_game_state

                return initial_game_state

        except asyncio.CancelledError:
            return initial_game_state
        except Exception as e:
            if self._shutdown:
                return initial_game_state
            raise
        finally:
            self._current_websocket = None

    def handle(self, m, initial_game_state):
        if len(m) <= 10:
            return None

        try:
            resp_json = json.loads(m)
        except json.JSONDecodeError:
            return None

        uri = resp_json[2].get("uri") if len(resp_json) > 2 else None

        if uri == "/chat/v4/presences":
            return self._handle_presence(resp_json, initial_game_state)
        elif uri == "/chat/v6/messages":
            self._handle_message(resp_json)

        return None

    def _get_session_state(self, private_data):
        """Extract sessionLoopState from either nested or flat presence format."""
        match_data = private_data.get("matchPresenceData")
        if match_data and "sessionLoopState" in match_data:
            return match_data["sessionLoopState"]
        return private_data.get("sessionLoopState")

    def _handle_presence(self, resp_json, initial_game_state):
        try:
            presence = resp_json[2]["data"]["presences"][0]
            if presence['puuid'] != self.Requests.puuid:
                return None

            # Skip if League of Legends
            if presence.get("championId") is not None or presence.get("product") == "league_of_legends":
                return None

            private_data = json.loads(base64.b64decode(presence['private']))

            # Handle both nested (matchPresenceData.sessionLoopState) and
            # flat (sessionLoopState) presence API formats.
            state = self._get_session_state(private_data)
            if state is None:
                return None

            if self.rpc:
                self.rpc.set_rpc(private_data)

            if state != initial_game_state:
                self.messages = 0
                self.message_history = []
                return state

        except (KeyError, IndexError, json.JSONDecodeError):
            pass

        return None

    def _handle_message(self, resp_json):
        try:
            message = resp_json[2]["data"]["messages"][0]

            if "ares-coregame" not in message["cid"]:
                return
            if message["id"] in self.id_seen:
                return

            # Find ally team
            ally_team = None
            for player in self.player_data:
                if player == self.Requests.puuid:
                    ally_team = self.player_data[player]["team"]
                    break

            # Determine color
            if message["puuid"] == self.Requests.puuid:
                clr = (221, 224, 41)
            elif message["puuid"] in self.player_data and self.player_data[message["puuid"]]["team"] == ally_team:
                clr = (76, 151, 237)
            else:
                clr = (238, 77, 77)

            chat_indicator = message["cid"].split("@")[0].rsplit("-", 1)[1]
            chat_prefix = color("[Team]", fore=(116, 162, 214)) if chat_indicator == "blue" else "[All]"

            puuid = message["puuid"]
            agent = ""
            streamer_mode = False

            if puuid in self.player_data:
                agent = self.colors.get_agent_from_uuid(self.player_data[puuid]['agent'].lower())
                streamer_mode = self.player_data[puuid].get('streamer_mode', False)

            name = f"{message['game_name']}#{message['game_tag']}"

            if streamer_mode and self.hide_names and puuid not in self.player_data.get("ignore", []):
                self.print_message(f"{chat_prefix} {color(self.colors.escape_ansi(agent), clr)}: {message['body']}")
                self.server.send_payload("chat", {
                    "time": message["time"],
                    "puuid": puuid,
                    "self": puuid == self.Requests.puuid,
                    "group": re.sub(r"\[|\]", "", self.colors.escape_ansi(chat_prefix)),
                    "agent": self.colors.escape_ansi(agent),
                    "text": message['body']
                })
            else:
                agent_str = f" ({agent})" if agent else ""
                self.print_message(f"{chat_prefix} {color(name, clr)}{agent_str}: {message['body']}")
                self.server.send_payload("chat", {
                    "time": message["time"],
                    "puuid": puuid,
                    "self": puuid == self.Requests.puuid,
                    "group": re.sub(r"\[|\]", "", self.colors.escape_ansi(chat_prefix)),
                    "player": name,
                    "agent": self.colors.escape_ansi(agent),
                    "text": message['body']
                })

            self.id_seen.append(message['id'])

        except (KeyError, IndexError):
            pass

    def print_message(self, message):
        self.messages += 1
        if self.messages > self.chat_limit:
            print(self.up * self.chat_limit, end="")
            for i in range(len(self.message_history) - self.chat_limit + 1, len(self.message_history)):
                prev_len = len(self.colors.escape_ansi(self.message_history[i-1]).encode('utf8'))
                curr_len = len(self.colors.escape_ansi(self.message_history[i]).encode('utf8'))
                print(self.message_history[i] + " " * max(0, prev_len - curr_len))
            prev_len = len(self.colors.escape_ansi(self.message_history[-1]).encode('utf8'))
            curr_len = len(self.colors.escape_ansi(message).encode('utf8'))
            print(message + " " * max(0, prev_len - curr_len))
        else:
            print(message)
        self.message_history.append(message)

    def close(self):
        """Clean up websocket resources"""
        self._shutdown = True
        try:
            if self.rpc:
                self.rpc.close()
        except Exception:
            pass