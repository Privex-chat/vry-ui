import json
import logging
from websocket_server import WebsocketServer
from src.constants import version

logging.getLogger('websocket_server.websocket_server').disabled = True

class Server:
    def __init__(self, log, Error):
        self.Error = Error
        self.log = log
        self.lastMessages = {}
        self.server = None
        self.current_theme = "dark"
        self.loadouts_data = None

    def start_server(self):
        try:
            with open("config.json", "r") as conf:
                config = json.load(conf)
                port = config.get("port", 1100)
                self.current_theme = config.get("theme", "dark").lower()
                
            self.server = WebsocketServer(host="0.0.0.0", port=port)
            self.server.set_fn_new_client(self.handle_new_client)
            self.server.run_forever(threaded=True)
        except Exception as e:
            self.Error.PortError(port)

    def stop_server(self):
        if self.server:
            try:
                self.server.shutdown_gracefully()
                self.log("WebSocket server stopped gracefully")
            except Exception as e:
                self.log(f"Error stopping server: {e}")
            finally:
                self.server = None

    def handle_new_client(self, client, server):
        self.send_payload("version", {
            "core": version
        })
        
        self.send_payload("theme", {
            "theme": self.current_theme
        })
        
        if self.loadouts_data:
            self.send_payload("loadouts", self.loadouts_data)
            
        for key in self.lastMessages:
            if key not in ["chat", "version", "theme", "loadouts"]:
                self.send_message(self.lastMessages[key])

    def send_message(self, message):
        if self.server:
            self.server.send_message_to_all(message)

    def send_payload(self, type, payload):
        payload["type"] = type
        msg_str = json.dumps(payload)
        self.lastMessages[type] = msg_str
        if self.server:
            self.server.send_message_to_all(msg_str)
    
    def update_theme(self, theme_name):
        self.current_theme = theme_name.lower()
        self.send_payload("theme", {
            "theme": self.current_theme
        })
    
    def update_loadouts(self, loadouts_data):
        self.loadouts_data = loadouts_data
        self.send_payload("loadouts", loadouts_data)