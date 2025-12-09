"""
VRY - UI v2.14
Fixed: Event loop crash, optimized for lightweight usage
"""

import asyncio
import os
import socket
import sys
import time
import traceback
import json
import threading
from pathlib import Path
from io import StringIO
import re
from collections import OrderedDict
from functools import lru_cache

ANSI_RGB_RE = re.compile(r'\x1B\[38;2;(\d+);(\d+);(\d+)m')
ANSI_ANY_RE = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')

import requests
import urllib3
from colr import color as colr
from InquirerPy import inquirer

try:
    from PySide6.QtCore import (Qt, QUrl, Signal, QThread, QTimer, 
                                QSettings, QObject, QDateTime)
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, 
                                  QVBoxLayout, QHBoxLayout, QStackedWidget,
                                  QPushButton, QTextEdit, QLabel, QTabWidget,
                                  QSplitter, QStatusBar, QMenuBar,
                                  QGroupBox, QGridLayout, QCheckBox, QMessageBox, 
                                  QLineEdit, QTableWidget, QTableWidgetItem,
                                  QHeaderView, QComboBox, QColorDialog, QDialog,
                                  QDialogButtonBox, QSpinBox)
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtGui import QFont, QIcon, QTextCursor, QPalette, QColor, QKeySequence, QAction
    USING_PYSIDE6 = True
except ImportError as e:
    print("Please install PySide6-Essentials:")
    print("pip install PySide6-Essentials")
    sys.exit(1)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    from src.webview import MatchLoadoutsContainer
    OPTIMIZED_WEBVIEW_AVAILABLE = True
except ImportError:
    OPTIMIZED_WEBVIEW_AVAILABLE = False

from src.colors import Colors
from src.config import Config
from src.configurator import configure
from src.constants import *
from src.content import Content
from src.errors import Error
from src.Loadouts import Loadouts
from src.logs import Logging
from src.names import Names
from src.player_stats import PlayerStats
from src.presences import Presences
from src.rank import Rank
from src.requestsV import Requests
from src.rpc import Rpc
from src.server import Server
from src.states.coregame import Coregame
from src.states.menu import Menu
from src.states.pregame import Pregame
from src.stats import Stats
from src.table import Table
from src.websocket import Ws
from src.os import get_os
from src.account_manager.account_manager import AccountManager
from src.account_manager.account_config import AccountConfig
from src.account_manager.account_auth import AccountAuth

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class LRUCache:
    """Simple LRU cache for API responses"""
    def __init__(self, maxsize=128, ttl=300):
        self.cache = OrderedDict()
        self.maxsize = maxsize
        self.ttl = ttl  # seconds
    
    def get(self, key):
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                self.cache.move_to_end(key)
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value):
        if key in self.cache:
            del self.cache[key]
        elif len(self.cache) >= self.maxsize:
            self.cache.popitem(last=False)
        self.cache[key] = (value, time.time())
    
    def invalidate(self, key=None):
        if key:
            self.cache.pop(key, None)
        else:
            self.cache.clear()


class Theme:
    def __init__(self, name, background, text, border, alternate, selection, header, 
                 table_bg, table_text, table_grid, status_bg, accent):
        self.name = name
        self.background = background
        self.text = text
        self.border = border
        self.alternate = alternate
        self.selection = selection
        self.header = header
        self.table_bg = table_bg
        self.table_text = table_text
        self.table_grid = table_grid
        self.status_bg = status_bg
        self.accent = accent


THEMES = {
    "Dark": Theme("Dark", "#1a1a1a", "#e0e0e0", "#333333", "#252525", "#3d3d3d", 
                  "#2b2b2b", "#1e1e1e", "#ffffff", "#2a2a2a", "#007acc", "#007acc"),
    "Light": Theme("Light", "#f5f5f5", "#333333", "#cccccc", "#e8e8e8", "#d0e3ff",
                   "#e0e0e0", "#ffffff", "#000000", "#dddddd", "#0078d4", "#0078d4"),
    "Midnight": Theme("Midnight", "#0d1117", "#c9d1d9", "#30363d", "#161b22", "#1f6feb",
                      "#010409", "#0d1117", "#c9d1d9", "#21262d", "#1f6feb", "#58a6ff"),
    "Valorant": Theme("Valorant", "#0f1923", "#ffffff", "#ff4655", "#1b2838", "#ff4655",
                      "#111111", "#0f1923", "#ffffff", "#ff4655", "#ff4655", "#ff4655")
}


class VRYWorkerThread(QThread):
    
    output_signal = Signal(str)
    error_signal = Signal(str)
    table_update_signal = Signal(list, dict)
    table_row_signal = Signal(dict, dict)
    status_signal = Signal(str, str)
    
    def __init__(self, verbose_level=0):
        super().__init__()
        self.running = False
        self.initialized = False
        self.game_state = None
        self.firstTime = True
        self.verbose_level = verbose_level
        self.loop = None
        self.freeze_table = False
        
        # Caching
        self.player_cache = LRUCache(maxsize=64, ttl=60)
        self.pregame_players_cache = {}  # Cache pregame data for ingame reuse
        self.last_match_id = None
        
        # Shutdown coordination
        self._shutdown_event = threading.Event()
        
    def set_freeze_state(self, frozen):
        self.freeze_table = frozen
        
    def initialize_vry(self):
        try:
            self.Logging = Logging()
            self.log = self.Logging.log
            
            if self.verbose_level > 0:
                self.output_signal.emit(f"OS: {get_os()}\n")
            
            self.acc_manager = AccountManager(self.log, AccountConfig, AccountAuth, NUMBERTORANKS)
            self.ErrorSRC = Error(self.log, self.acc_manager)
            
            Requests.check_version(version, Requests.copy_run_update_script)
            Requests.check_status()
            self.Requests = Requests(version, self.log, self.ErrorSRC)
            
            self.cfg = Config(self.log)
            self.content = Content(self.Requests, self.log)
            
            self.rank = Rank(self.Requests, self.log, self.content, before_ascendant_seasons)
            self.pstats = PlayerStats(self.Requests, self.log, self.cfg)
            self.namesClass = Names(self.Requests, self.log)
            self.presences = Presences(self.Requests, self.log)
            
            self.menu = Menu(self.Requests, self.log, self.presences)
            self.pregame = Pregame(self.Requests, self.log)
            self.coregame = Coregame(self.Requests, self.log)
            
            self.Server = Server(self.log, self.ErrorSRC)
            self.Server.start_server()
            
            self.agent_dict = self.content.get_all_agents()
            
            map_info = self.content.get_all_maps()
            self.map_urls = self.content.get_map_urls(map_info)
            self.map_splashes = self.content.get_map_splashes(map_info)
            
            self.current_map = self.coregame.get_current_map(self.map_urls, self.map_splashes)
            
            self.colors = Colors(hide_names, self.agent_dict, AGENTCOLORLIST)
            
            self.loadoutsClass = Loadouts(self.Requests, self.log, self.colors, 
                                         self.Server, self.current_map)
            self.table = Table(self.cfg, self.log)
            self.stats = Stats()
            
            self.rpc = Rpc(self.map_urls, gamemodes, self.colors, self.log) if self.cfg.get_feature_flag("discord_rpc") else None
            
            self.Wss = Ws(self.Requests.lockfile, self.Requests, self.cfg, 
                         self.colors, hide_names, self.Server, self.rpc)
            
            # Cache static API data
            self.valoApiSkins = requests.get("https://valorant-api.com/v1/weapons/skins", timeout=10)
            self.gameContent = self.content.get_content()
            self.seasonID = self.content.get_latest_season_id(self.gameContent)
            self.previousSeasonID = self.content.get_previous_season_id(self.gameContent)
            self.seasonActEp = self.content.get_act_episode_from_act_id(self.seasonID)
            self.previousSeasonActEp = self.content.get_act_episode_from_act_id(self.previousSeasonID)
            
            self.initialized = True
            self.output_signal.emit(f"VRY Mobile - {self.get_ip()}:{self.cfg.port}")
            
        except Exception as e:
            self.error_signal.emit(f"Init error: {str(e)}")
            if self.verbose_level > 1:
                self.log(traceback.format_exc())
    
    def log(self, message):
        if self.verbose_level > 1:
            self.output_signal.emit(f"[DEBUG] {message}")
            
    def get_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0)
            s.connect(("10.254.254.254", 1))
            IP = s.getsockname()[0]
            s.close()
            return IP
        except Exception:
            return "127.0.0.1"
    
    def send_heartbeat(self, heartbeat_data):
        try:
            if hasattr(self, 'Server') and self.Server:
                self.Server.send_payload("heartbeat", heartbeat_data)
        except Exception:
            pass
    
    def run(self):
        self.running = True
        self._shutdown_event.clear()
        
        # Create dedicated event loop for this thread
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            if not self.initialized:
                self.initialize_vry()
                
            if not self.initialized:
                self.error_signal.emit("Failed to initialize VRY")
                return
            
            while self.running and not self._shutdown_event.is_set():
                try:
                    self.process_game_state()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if self.verbose_level > 0:
                        self.error_signal.emit(f"Processing error: {str(e)}")
                    if self.verbose_level > 1:
                        self.log(traceback.format_exc())
                
                # Interruptible sleep
                for _ in range(20):
                    if not self.running or self._shutdown_event.is_set():
                        break
                    self.msleep(100)
                    
        except Exception as e:
            self.error_signal.emit(f"Thread error: {str(e)}")
        finally:
            self._cleanup_loop()
    
    def _cleanup_loop(self):
        """Safely cleanup the event loop"""
        if self.loop and not self.loop.is_closed():
            try:
                # Cancel pending tasks
                pending = asyncio.all_tasks(self.loop)
                for task in pending:
                    task.cancel()
                
                # Give tasks time to cancel
                if pending:
                    self.loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                    
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
                self.loop.close()
            except Exception:
                pass
            finally:
                self.loop = None
                
    def process_game_state(self):
        if self._shutdown_event.is_set():
            return
            
        try:
            if self.firstTime:
                self._wait_for_initial_presence()
                self.firstTime = False
            else:
                self._wait_for_state_change()
            
            if self.freeze_table or self._shutdown_event.is_set():
                return
            
            presence = self.presences.get_presence()
            priv_presence = self.presences.get_private_presence(presence)
            
            if not priv_presence:
                return
            
            gamemode = self._get_gamemode(priv_presence)
            
            table_data = []
            metadata = {"state": self.game_state, "mode": gamemode}
            heartbeat_data = {
                "time": int(time.time()),
                "state": self.game_state,
                "mode": gamemode,
                "puuid": self.Requests.puuid,
                "players": {},
            }
            
            try:
                if self.game_state == "INGAME":
                    table_data, metadata, heartbeat_data = self.process_ingame_state(presence, heartbeat_data)
                elif self.game_state == "PREGAME":
                    table_data, metadata, heartbeat_data = self.process_pregame_state(presence, heartbeat_data)
                elif self.game_state == "MENUS":
                    table_data, metadata, heartbeat_data = self.process_menu_state(presence, heartbeat_data)
                    # Clear pregame cache when back in menus
                    self.pregame_players_cache.clear()
            except Exception as e:
                self.error_signal.emit(f"Error processing {self.game_state}: {str(e)}")
                if self.verbose_level > 1:
                    self.log(traceback.format_exc())
            
            self.status_signal.emit(self.game_state, gamemode)
            
            if table_data:
                self.table_update_signal.emit(table_data, metadata)
                
            self.send_heartbeat(heartbeat_data)
                
        except Exception as e:
            if self.verbose_level > 0:
                self.error_signal.emit(f"State error: {str(e)}")

    def _wait_for_initial_presence(self):
        """Wait for initial Valorant presence"""
        while self.running and not self._shutdown_event.is_set():
            presence = self.presences.get_presence()
            private_presence = self.presences.get_private_presence(presence)
            
            if private_presence:
                if self.rpc:
                    self.rpc.set_rpc(private_presence)
                self.game_state = self.presences.get_game_state(presence)
                if self.game_state:
                    self.log(f"Initial state: {self.game_state}")
                    return
            
            for _ in range(20):
                if not self.running or self._shutdown_event.is_set():
                    return
                self.msleep(100)

    def _wait_for_state_change(self):
        """Wait for game state change via websocket"""
        if not self.loop or self.loop.is_closed():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        
        previous_state = self.game_state
        
        try:
            self.game_state = self.loop.run_until_complete(
                self.Wss.recconect_to_websocket(self.game_state)
            )
        except asyncio.CancelledError:
            return
        except RuntimeError as e:
            if "Event loop stopped" in str(e) or "Event loop is closed" in str(e):
                return
            raise
        except Exception as e:
            self.log(f"Websocket error: {e}")
            return
        
        if previous_state != self.game_state:
            self.log(f"State change: {previous_state} -> {self.game_state}")
            if self.game_state == "MENUS":
                self.rank.invalidate_cached_responses()
                self.player_cache.invalidate()

    def _get_gamemode(self, priv_presence):
        if priv_presence["provisioningFlow"] == "CustomGame" or \
           priv_presence["partyPresenceData"]["partyState"] == "CUSTOM_GAME_SETUP":
            return "Custom Game"
        return gamemodes.get(priv_presence["queueId"], "Unknown")

    def _get_cached_player_data(self, puuid):
        """Get cached player data if available"""
        return self.player_cache.get(puuid)
    
    def _cache_player_data(self, puuid, data):
        """Cache player data"""
        self.player_cache.set(puuid, data)

    def process_ingame_state(self, presence, heartbeat_data):
        table_data = []
        metadata = {"state": "INGAME", "clear_table": True}
        
        coregame_stats = self.coregame.get_coregame_stats()
        if not coregame_stats:
            return table_data, metadata, heartbeat_data
        
        self.table_update_signal.emit([], metadata)
        
        Players = coregame_stats["Players"]
        match_id = self.coregame.get_coregame_match_id()
        
        # Check if this is same match as pregame
        reuse_pregame = (self.last_match_id == match_id and self.pregame_players_cache)
        
        partyMembers = self.menu.get_party_members(self.Requests.puuid, presence)
        partyMembersList = [a["Subject"] for a in partyMembers]
        
        # Set up player data for websocket
        players_data = {"ignore": partyMembersList}
        for player in Players:
            if player["Subject"] == self.Requests.puuid and self.rpc:
                self.rpc.set_data({"agent": player["CharacterID"]})
            players_data[player["Subject"]] = {
                "team": player["TeamID"],
                "agent": player["CharacterID"],
                "streamer_mode": player["PlayerIdentity"]["Incognito"]
            }
        self.Wss.set_player_data(players_data)
        
        self.presences.wait_for_presence(self.namesClass.get_players_puuid(Players))
        names = self.namesClass.get_names_from_puuids(Players)
        
        # Get loadouts
        try:
            loadouts_arr = self.loadoutsClass.get_match_loadouts(
                match_id, Players, self.cfg.weapon, self.valoApiSkins, names, state="game"
            )
            loadouts = loadouts_arr[0]
            loadouts_data = loadouts_arr[1] if len(loadouts_arr) > 1 else {}
        except Exception as e:
            self.log(f"Loadouts error: {e}")
            loadouts, loadouts_data = {}, {}
        
        # Sort: by level desc, then by team (allies first)
        allyTeam = None
        for p in Players:
            if p["Subject"] == self.Requests.puuid:
                allyTeam = p["TeamID"]
                break
        
        # Keep original API order within teams but group by team
        ally_players = [p for p in Players if p["TeamID"] == allyTeam]
        enemy_players = [p for p in Players if p["TeamID"] != allyTeam]
        Players = ally_players + enemy_players
        
        partyOBJ = self.menu.get_party_json(self.namesClass.get_players_puuid(Players), presence)
        partyIcons = {}
        partyCount = 0
        
        heartbeat_data["map"] = self.map_urls.get(coregame_stats["MapID"].lower(), "")
        
        for player in Players:
            if not self.running or self.freeze_table:
                break
            
            puuid = player["Subject"]
            
            # Party icon
            party_icon, partyNum = "", 0
            for party in partyOBJ:
                if puuid in partyOBJ[party]:
                    if party not in partyIcons:
                        partyIcons[party] = PARTYICONLIST[partyCount]
                        partyCount += 1
                    party_icon = partyIcons[party]
                    partyNum = partyCount
            
            agent_name = self.agent_dict.get(player["CharacterID"].lower(), "Unknown")
            
            # Try to reuse pregame data for allies
            cached_data = self.pregame_players_cache.get(puuid) if reuse_pregame and player["TeamID"] == allyTeam else None
            
            if cached_data:
                playerRank = cached_data["rank_data"]
                previousPlayerRank = cached_data["prev_rank_data"]
                ppstats = cached_data["stats"]
            else:
                playerRank = self.rank.get_rank(puuid, self.seasonID)
                previousPlayerRank = self.rank.get_rank(puuid, self.previousSeasonID)
                ppstats = self.pstats.get_stats(puuid)
            
            row_data = self._build_row_data(
                player, names, party_icon, agent_name, loadouts,
                playerRank, previousPlayerRank, ppstats,
                partyMembersList, allyTeam
            )
            
            if not self.freeze_table:
                self.table_row_signal.emit(row_data, metadata)
            
            table_data.append(row_data)
            
            # Build heartbeat player data
            heartbeat_data["players"][puuid] = self._build_heartbeat_player(
                player, names, partyNum, playerRank, ppstats, loadouts_data
            )
            
            # Save stats
            self.stats.save_data({
                puuid: {
                    "name": names[puuid],
                    "agent": agent_name,
                    "map": self.current_map,
                    "rank": playerRank["rank"],
                    "rr": playerRank["rr"],
                    "match_id": match_id,
                    "epoch": time.time()
                }
            })
        
        return table_data, metadata, heartbeat_data

    def process_pregame_state(self, presence, heartbeat_data):
        table_data = []
        metadata = {"state": "PREGAME", "clear_table": True}
        
        pregame_stats = self.pregame.get_pregame_stats()
        if not pregame_stats:
            return table_data, metadata, heartbeat_data
        
        # Cache match ID for ingame reuse
        self.last_match_id = self.pregame.get_pregame_match_id()
        
        if self.cfg.get_feature_flag("starting_side"):
            team_id = pregame_stats.get("AllyTeam", {}).get("TeamID")
            if team_id:
                metadata["starting_side"] = "Attacker" if team_id == "Red" else "Defender"
        
        self.table_update_signal.emit([], metadata)
        
        Players = pregame_stats["AllyTeam"]["Players"]
        self.presences.wait_for_presence(self.namesClass.get_players_puuid(Players))
        names = self.namesClass.get_names_from_puuids(Players)
        
        partyMembers = self.menu.get_party_members(self.Requests.puuid, presence)
        partyMembersList = [a["Subject"] for a in partyMembers]
        partyOBJ = self.menu.get_party_json(self.namesClass.get_players_puuid(Players), presence)
        
        partyIcons = {}
        partyCount = 0
        
        teams = pregame_stats.get("Teams", [])
        team_id = teams[0]["TeamID"] if teams else None
        
        # Clear and rebuild pregame cache
        self.pregame_players_cache.clear()
        
        for player in Players:
            if not self.running or self.freeze_table:
                break
            
            puuid = player["Subject"]
            
            party_icon, partyNum = "", 0
            for party in partyOBJ:
                if puuid in partyOBJ[party]:
                    if party not in partyIcons:
                        partyIcons[party] = PARTYICONLIST[partyCount]
                        partyCount += 1
                    party_icon = partyIcons[party]
                    partyNum = partyCount
            
            agent_name = self.agent_dict.get(player["CharacterID"].lower(), "Unknown")
            
            playerRank = self.rank.get_rank(puuid, self.seasonID)
            previousPlayerRank = self.rank.get_rank(puuid, self.previousSeasonID)
            ppstats = self.pstats.get_stats(puuid)
            
            # Cache for ingame reuse
            self.pregame_players_cache[puuid] = {
                "rank_data": playerRank,
                "prev_rank_data": previousPlayerRank,
                "stats": ppstats,
                "name": names[puuid]
            }
            
            row_data = {
                "puuid": puuid,
                "party": party_icon,
                "agent": agent_name,
                "agent_state": player["CharacterSelectionState"],
                "name": names[puuid],
                "incognito": player["PlayerIdentity"]["Incognito"],
                "team": team_id,
                "is_self": puuid == self.Requests.puuid,
                "is_party": puuid in partyMembersList,
                "skin": "",
                "rank": NUMBERTORANKS[playerRank["rank"]],
                "rank_number": playerRank["rank"],
                "rank_act": self.seasonActEp.get("act"),
                "rank_ep": self.seasonActEp.get("episode"),
                "rr": playerRank["rr"],
                "peak_rank": NUMBERTORANKS[playerRank["peakrank"]],
                "peak_rank_number": playerRank["peakrank"],
                "peak_act": playerRank.get("peakrankact"),
                "peak_ep": playerRank.get("peakrankep"),
                "previous_rank": NUMBERTORANKS[previousPlayerRank["rank"]],
                "previous_act": self.previousSeasonActEp.get("act"),
                "previous_ep": self.previousSeasonActEp.get("episode"),
                "leaderboard": playerRank["leaderboard"],
                "hs": ppstats["hs"],
                "kd": ppstats["kd"],
                "wr": playerRank["wr"],
                "games": playerRank['numberofgames'],
                "level": player["PlayerIdentity"].get("AccountLevel"),
                "hide_level": player["PlayerIdentity"]["HideAccountLevel"],
                "earned_rr": ppstats.get("RankedRatingEarned", "N/A"),
                "afk_penalty": ppstats.get("AFKPenalty", "N/A")
            }
            
            if not self.freeze_table:
                self.table_row_signal.emit(row_data, metadata)
            
            table_data.append(row_data)
            
            heartbeat_data["players"][puuid] = {
                "name": names[puuid],
                "partyNumber": partyNum if party_icon else 0,
                "agent": agent_name,
                "rank": playerRank["rank"],
                "peakRank": playerRank["peakrank"],
                "peakRankAct": f"{playerRank.get('peakrankep', '')}a{playerRank.get('peakrankact', '')}",
                "level": player["PlayerIdentity"].get("AccountLevel", 0),
                "rr": playerRank["rr"],
                "kd": ppstats["kd"],
                "headshotPercentage": ppstats["hs"],
                "winPercentage": f"{playerRank['wr']} ({playerRank['numberofgames']})",
            }
        
        return table_data, metadata, heartbeat_data

    def process_menu_state(self, presence, heartbeat_data):
        table_data = []
        metadata = {"state": "MENUS", "clear_table": True}
        
        self.table_update_signal.emit([], metadata)
        
        Players = self.menu.get_party_members(self.Requests.puuid, presence)
        names = self.namesClass.get_names_from_puuids(Players)
        
        seen = set()
        for player in Players:
            puuid = player["Subject"]
            if puuid in seen or self.freeze_table:
                continue
            seen.add(puuid)
            
            playerRank = self.rank.get_rank(puuid, self.seasonID)
            previousPlayerRank = self.rank.get_rank(puuid, self.previousSeasonID)
            ppstats = self.pstats.get_stats(puuid)
            
            row_data = {
                "puuid": puuid,
                "party": PARTYICONLIST[0],
                "agent": "",
                "name": names[puuid],
                "incognito": False,
                "is_self": puuid == self.Requests.puuid,
                "is_party": True,
                "skin": "",
                "rank": NUMBERTORANKS[playerRank["rank"]],
                "rank_number": playerRank["rank"],
                "rank_act": self.seasonActEp.get("act"),
                "rank_ep": self.seasonActEp.get("episode"),
                "rr": playerRank["rr"],
                "peak_rank": NUMBERTORANKS[playerRank["peakrank"]],
                "peak_rank_number": playerRank["peakrank"],
                "peak_act": playerRank.get("peakrankact"),
                "peak_ep": playerRank.get("peakrankep"),
                "previous_rank": NUMBERTORANKS[previousPlayerRank["rank"]],
                "previous_act": self.previousSeasonActEp.get("act"),
                "previous_ep": self.previousSeasonActEp.get("episode"),
                "leaderboard": playerRank["leaderboard"],
                "hs": ppstats["hs"],
                "kd": ppstats["kd"],
                "wr": playerRank["wr"],
                "games": playerRank['numberofgames'],
                "level": player["PlayerIdentity"].get("AccountLevel"),
                "hide_level": False,
                "earned_rr": ppstats.get("RankedRatingEarned", "N/A"),
                "afk_penalty": ppstats.get("AFKPenalty", "N/A")
            }
            
            if not self.freeze_table:
                self.table_row_signal.emit(row_data, metadata)
            
            table_data.append(row_data)
            
            heartbeat_data["players"][puuid] = {
                "name": names[puuid],
                "rank": playerRank["rank"],
                "peakRank": playerRank["peakrank"],
                "peakRankAct": f"{playerRank.get('peakrankep', '')}a{playerRank.get('peakrankact', '')}",
                "level": player["PlayerIdentity"].get("AccountLevel", 0),
                "rr": playerRank["rr"],
                "kd": ppstats["kd"],
                "headshotPercentage": ppstats["hs"],
                "winPercentage": f"{playerRank['wr']} ({playerRank['numberofgames']})",
            }
        
        return table_data, metadata, heartbeat_data

    def _build_row_data(self, player, names, party_icon, agent_name, loadouts,
                        playerRank, previousPlayerRank, ppstats, partyMembersList, allyTeam):
        puuid = player["Subject"]
        return {
            "puuid": puuid,
            "party": party_icon,
            "agent": agent_name,
            "name": names[puuid],
            "incognito": player["PlayerIdentity"]["Incognito"],
            "team": player["TeamID"],
            "ally_team": allyTeam,
            "is_self": puuid == self.Requests.puuid,
            "is_party": puuid in partyMembersList,
            "skin": loadouts.get(puuid, ""),
            "rank": NUMBERTORANKS[playerRank["rank"]],
            "rank_number": playerRank["rank"],
            "rank_act": self.seasonActEp.get("act"),
            "rank_ep": self.seasonActEp.get("episode"),
            "rr": playerRank["rr"],
            "peak_rank": NUMBERTORANKS[playerRank["peakrank"]],
            "peak_rank_number": playerRank["peakrank"],
            "peak_act": playerRank.get("peakrankact"),
            "peak_ep": playerRank.get("peakrankep"),
            "previous_rank": NUMBERTORANKS[previousPlayerRank["rank"]],
            "previous_act": self.previousSeasonActEp.get("act"),
            "previous_ep": self.previousSeasonActEp.get("episode"),
            "leaderboard": playerRank["leaderboard"],
            "hs": ppstats["hs"],
            "kd": ppstats["kd"],
            "wr": playerRank["wr"],
            "games": playerRank['numberofgames'],
            "level": player["PlayerIdentity"].get("AccountLevel"),
            "hide_level": player["PlayerIdentity"]["HideAccountLevel"],
            "earned_rr": ppstats.get("RankedRatingEarned", "N/A"),
            "afk_penalty": ppstats.get("AFKPenalty", "N/A")
        }

    def _build_heartbeat_player(self, player, names, partyNum, playerRank, ppstats, loadouts_data):
        puuid = player["Subject"]
        return {
            "puuid": puuid,
            "name": names[puuid],
            "partyNumber": partyNum,
            "agent": self.agent_dict.get(player["CharacterID"].lower(), "Unknown"),
            "rank": playerRank["rank"],
            "peakRank": playerRank["peakrank"],
            "peakRankAct": f"{playerRank.get('peakrankep', '')}a{playerRank.get('peakrankact', '')}",
            "rr": playerRank["rr"],
            "kd": ppstats["kd"],
            "headshotPercentage": ppstats["hs"],
            "winPercentage": f"{playerRank['wr']} ({playerRank['numberofgames']})",
            "level": player["PlayerIdentity"].get("AccountLevel", 0),
            "agentImgLink": loadouts_data.get("Players", {}).get(puuid, {}).get("Agent"),
            "team": loadouts_data.get("Players", {}).get(puuid, {}).get("Team"),
            "sprays": loadouts_data.get("Players", {}).get(puuid, {}).get("Sprays"),
            "title": loadouts_data.get("Players", {}).get(puuid, {}).get("Title"),
            "playerCard": loadouts_data.get("Players", {}).get(puuid, {}).get("PlayerCard"),
            "weapons": loadouts_data.get("Players", {}).get(puuid, {}).get("Weapons"),
        }
    
    def stop(self):
        """Gracefully stop the worker thread"""
        self.running = False
        self._shutdown_event.set()
        
        # Signal websocket to close
        if hasattr(self, "Wss") and self.Wss:
            self.Wss.request_shutdown()
        
        # Give websocket time to close gracefully
        time.sleep(0.5)
        
        # Cleanup resources
        try:
            if hasattr(self, "Wss") and self.Wss:
                self.Wss.close()
        except Exception:
            pass
        
        try:
            if hasattr(self, "Server") and self.Server:
                self.Server.stop_server()
        except Exception:
            pass
        
        try:
            if hasattr(self, "rpc") and self.rpc:
                self.rpc.close()
        except Exception:
            pass
        
        try:
            if hasattr(self, "loadoutsClass") and self.loadoutsClass:
                self.loadoutsClass.close()
        except Exception:
            pass


class VRYTableWidget(QTableWidget):
    
    def __init__(self):
        super().__init__()
        self.current_theme = THEMES["Dark"]
        self.is_frozen = False
        self.setup_table()
        
    def setup_table(self):
        self.setColumnCount(14)
        headers = ["Party", "Agent", "Name", "Skin", "Rank", "RR", 
                  "Peak", "Previous", "Pos.", "HS%", "WR%", "K/D", "Level", "ΔRR"]
        self.setHorizontalHeaderLabels(headers)
        
        self.horizontalHeader().setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        
        header = self.horizontalHeader()
        for col in range(self.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        for col in [2, 3, 4, 6, 7, 10]:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)

        self.setSortingEnabled(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.verticalHeader().setVisible(False)
        self.apply_theme(self.current_theme)

    def apply_theme(self, theme):
        self.current_theme = theme
        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {theme.table_bg};
                color: {theme.table_text};
                gridline-color: {theme.table_grid};
                border: none;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
            }}
            QTableWidget::item {{
                padding: 6px;
                border: none;
            }}
            QTableWidget::item:selected {{
                background-color: {theme.selection};
            }}
            QHeaderView::section {{
                background-color: {theme.header};
                color: {theme.table_text};
                padding: 8px;
                border: none;
                border-right: 1px solid {theme.table_grid};
                border-bottom: 2px solid {theme.accent};
                font-weight: bold;
            }}
        """)
    
    def freeze_table(self, freeze):
        self.is_frozen = freeze
    
    def add_row_streaming(self, row_data, metadata):
        if self.is_frozen:
            return
        if metadata.get("clear_table"):
            self.setRowCount(0)
        row_position = self.rowCount()
        self.insertRow(row_position)
        self._populate_row(row_position, row_data, metadata)
        
    def update_table(self, data, metadata):
        if self.is_frozen:
            return
        self.setRowCount(0)
        for row_data in data:
            row_position = self.rowCount()
            self.insertRow(row_position)
            self._populate_row(row_position, row_data, metadata)
        self._update_column_visibility(metadata)
    
    def _populate_row(self, row_position, row_data, metadata):
        def parse_ansi(raw):
            if raw is None:
                raw = ""
            raw_text = str(raw)
            m = ANSI_RGB_RE.search(raw_text)
            clean = ANSI_ANY_RE.sub("", raw_text)
            item = QTableWidgetItem(clean)
            if m:
                try:
                    r, g, b = map(int, m.groups())
                    item.setForeground(QColor(r, g, b))
                except Exception:
                    pass
            return item
        
        def format_rank(rank_text, act, ep):
            if not rank_text or "Unranked" in str(rank_text):
                return rank_text
            clean = ANSI_ANY_RE.sub("", str(rank_text))
            return f"{clean} {ep}A{act}" if act and ep else rank_text

        privacy = metadata.get('incognito_privacy', True)
        is_self = row_data.get("is_self", False)
        is_party = row_data.get("is_party", False)
        incognito = row_data.get("incognito", False)

        # Party
        item = parse_ansi(row_data.get("party", ""))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row_position, 0, item)

        # Agent
        item = parse_ansi(row_data.get("agent", ""))
        if "agent_state" in row_data:
            states = {"locked": (255, 255, 255), "selected": (128, 128, 128)}
            if row_data["agent_state"] in states:
                item.setForeground(QColor(*states[row_data["agent_state"]]))
            else:
                item.setForeground(QColor(54, 53, 51))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row_position, 1, item)

        # Name
        if incognito and privacy and not is_self and not is_party:
            item = QTableWidgetItem("Incognito")
            item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            item.setForeground(QColor(128, 0, 0))
        else:
            name = ("*" + str(row_data.get("name", ""))) if incognito and not privacy else str(row_data.get("name", ""))
            item = parse_ansi(name)
            if is_self:
                item.setForeground(QColor(255, 215, 0))
            elif is_party:
                item.setForeground(QColor(76, 151, 237))
            elif "team" in row_data and "ally_team" in row_data:
                if row_data["team"] == row_data.get("ally_team"):
                    item.setForeground(QColor(0, 255, 127))
                else:
                    item.setForeground(QColor(255, 69, 0))
        self.setItem(row_position, 2, item)

        # Skin
        self.setItem(row_position, 3, parse_ansi(row_data.get("skin", "")))

        # Rank
        rank_text = format_rank(row_data.get("rank", ""), row_data.get("rank_act"), row_data.get("rank_ep"))
        self.setItem(row_position, 4, parse_ansi(rank_text))

        # RR
        item = QTableWidgetItem(str(row_data.get("rr", 0)))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row_position, 5, item)

        # Peak
        peak_text = format_rank(row_data.get("peak_rank", ""), row_data.get("peak_act"), row_data.get("peak_ep"))
        self.setItem(row_position, 6, parse_ansi(peak_text))

        # Previous
        prev_text = format_rank(row_data.get("previous_rank", ""), row_data.get("previous_act"), row_data.get("previous_ep"))
        self.setItem(row_position, 7, parse_ansi(prev_text))

        # Leaderboard
        lb = row_data.get("leaderboard", 0)
        item = QTableWidgetItem(str(lb) if lb and lb > 0 else "")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row_position, 8, item)

        # HS%
        hs = row_data.get("hs", "N/A")
        item = QTableWidgetItem(f"{float(hs):.1f}%" if hs != "N/A" else "N/A")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row_position, 9, item)

        # WR%
        wr = row_data.get("wr", "N/a")
        games = row_data.get("games", 0)
        item = QTableWidgetItem(f"{wr}% ({games})" if wr != "N/a" else f"N/A ({games})")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row_position, 10, item)

        # K/D
        kd = row_data.get("kd", "N/A")
        item = QTableWidgetItem(f"{float(kd):.2f}" if kd != "N/A" else "N/A")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row_position, 11, item)

        # Level
        level = row_data.get("level", "")
        if row_data.get("hide_level") and not is_self and not is_party and privacy:
            level = ""
        item = QTableWidgetItem(str(level))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row_position, 12, item)

        # ΔRR
        earned = row_data.get("earned_rr", "N/A")
        afk = row_data.get("afk_penalty", "N/A")
        if earned != "N/A" and afk != "N/A":
            text = f"{earned:+d}" + (f" ({afk})" if afk != 0 else "")
            item = QTableWidgetItem(text)
            item.setForeground(QColor(0, 255, 0) if earned > 0 else QColor(255, 0, 0) if earned < 0 else QColor(255, 255, 255))
        else:
            item = QTableWidgetItem("")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row_position, 13, item)
    
    def _update_column_visibility(self, metadata):
        state = metadata.get("state", "")
        self.setColumnHidden(0, state == "MENUS")
        self.setColumnHidden(1, state == "MENUS")
        self.setColumnHidden(3, state in ("MENUS", "PREGAME"))


class VRYMainWindow(QMainWindow):
    
    def __init__(self):
        super().__init__()
        
        self.settings = QSettings("VRY", "VRY-UI-v2")
        self.current_theme = THEMES["Dark"]
        self.worker_thread = None
        self.player_table_data = []
        self.player_table_metadata = {}
        self.matchloadouts_web = None
        self.vtl_web = None
        
        self.config = Config(None)
        self.show_resource_warning = self.config.get_feature_flag("show_resource_warning")
        
        self.init_ui()
        self.load_settings()
        
        if PSUTIL_AVAILABLE and self.show_resource_warning:
            self.resource_timer = QTimer()
            self.resource_timer.timeout.connect(self.monitor_resources)
            self.resource_timer.start(60000)  # Check every minute
        
        QTimer.singleShot(100, self.start_vry)
    
    def monitor_resources(self):
        if not PSUTIL_AVAILABLE:
            return
        try:
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.1)
            if mem.percent > 90 or cpu > 95:
                QMessageBox.warning(self, "High Resource Usage",
                    f"Memory: {mem.percent:.1f}%\nCPU: {cpu:.1f}%")
        except Exception:
            pass
    
    def init_ui(self):
        self.setWindowTitle("VRY - UI v2.14")
        self.setGeometry(100, 100, 1400, 850)
        self.setWindowIcon(QIcon("icon.ico"))
        self.setFont(QFont("Segoe UI", 9))
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.create_menu_bar()
        
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        main_layout.addWidget(self.tabs)
        
        # VRY Tab
        vry_widget = QWidget()
        vry_layout = QVBoxLayout(vry_widget)
        vry_layout.setContentsMargins(10, 10, 10, 10)
        
        status_panel = QWidget()
        status_layout = QHBoxLayout(status_panel)
        status_layout.setContentsMargins(0, 0, 0, 10)
        
        self.status_label = QLabel("Status: Initializing...")
        self.status_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        
        self.freeze_btn = QPushButton("Freeze Table")
        self.freeze_btn.setCheckable(True)
        self.freeze_btn.setMaximumWidth(140)
        self.freeze_btn.clicked.connect(self.toggle_freeze)
        status_layout.addWidget(self.freeze_btn)
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setMaximumWidth(100)
        self.refresh_btn.clicked.connect(self.refresh_data)
        status_layout.addWidget(self.refresh_btn)
        
        vry_layout.addWidget(status_panel)
        
        self.player_table = VRYTableWidget()
        vry_layout.addWidget(self.player_table)
        
        self.tabs.addTab(vry_widget, "Players")
        
        # Console (hidden by default)
        self.console_widget = QWidget()
        console_layout = QVBoxLayout(self.console_widget)
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setFont(QFont("Consolas", 9))
        console_layout.addWidget(self.console_output)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
        self.apply_theme(self.current_theme)
    
    def toggle_freeze(self, checked):
        self.player_table.freeze_table(checked)
        if self.worker_thread:
            self.worker_thread.set_freeze_state(checked)
        
        self.freeze_btn.setText("Unfreeze Table" if checked else "Freeze Table")
        self.freeze_btn.setStyleSheet(
            "QPushButton { background-color: #4a90e2; color: white; font-weight: bold; }" if checked else ""
        )
        self.status_bar.showMessage(f"Table {'frozen' if checked else 'unfrozen'}", 3000)
    
    def create_menu_bar(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        refresh = QAction('Refresh Data', self)
        refresh.setShortcut('F5')
        refresh.triggered.connect(self.refresh_data)
        file_menu.addAction(refresh)
        
        file_menu.addSeparator()
        
        exit_action = QAction('Exit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # View menu
        view_menu = menubar.addMenu('View')
        
        theme_menu = view_menu.addMenu('Theme')
        self.theme_group = []
        for name in THEMES:
            action = QAction(name, self)
            action.setCheckable(True)
            action.triggered.connect(lambda c, t=name: self.change_theme(t))
            theme_menu.addAction(action)
            self.theme_group.append(action)
        
        view_menu.addSeparator()
        
        self.toggle_matchloadouts = QAction('Match Loadouts Tab', self)
        self.toggle_matchloadouts.setCheckable(True)
        self.toggle_matchloadouts.setChecked(True)
        self.toggle_matchloadouts.triggered.connect(self.toggle_matchloadouts_tab)
        view_menu.addAction(self.toggle_matchloadouts)
        
        self.toggle_vtl = QAction('VTL.lol Tab', self)
        self.toggle_vtl.setCheckable(True)
        self.toggle_vtl.triggered.connect(self.toggle_vtl_tab)
        view_menu.addAction(self.toggle_vtl)
        
        self.toggle_console = QAction('Console Tab', self)
        self.toggle_console.setCheckable(True)
        self.toggle_console.triggered.connect(self.toggle_console_tab)
        view_menu.addAction(self.toggle_console)
        
        view_menu.addSeparator()
        
        self.incognito_action = QAction('Incognito Privacy', self)
        self.incognito_action.setCheckable(True)
        self.incognito_action.setChecked(True)
        self.incognito_action.triggered.connect(self.on_incognito_changed)
        view_menu.addAction(self.incognito_action)
    
    def apply_theme(self, theme):
        self.current_theme = theme
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {theme.background}; color: {theme.text}; }}
            QTabWidget::pane {{ border: 1px solid {theme.border}; }}
            QTabBar::tab {{ background-color: {theme.header}; color: {theme.text}; padding: 10px 20px; margin-right: 2px; }}
            QTabBar::tab:selected {{ background-color: {theme.selection}; border-bottom: 3px solid {theme.accent}; }}
            QPushButton {{ background-color: {theme.selection}; color: {theme.text}; border: 1px solid {theme.border}; padding: 8px 16px; border-radius: 4px; }}
            QPushButton:hover {{ background-color: {theme.alternate}; border: 1px solid {theme.accent}; }}
            QStatusBar {{ background-color: {theme.status_bg}; color: white; }}
            QMenuBar {{ background-color: {theme.header}; color: {theme.text}; }}
            QMenu {{ background-color: {theme.background}; color: {theme.text}; border: 1px solid {theme.border}; }}
            QMenu::item:selected {{ background-color: {theme.selection}; }}
            QTextEdit {{ background-color: {theme.table_bg}; color: {theme.text}; border: 1px solid {theme.border}; }}
            QLineEdit {{ background-color: {theme.table_bg}; color: {theme.text}; border: 1px solid {theme.border}; padding: 5px; }}
        """)
        
        if hasattr(self, 'player_table'):
            self.player_table.apply_theme(theme)
    
    def change_theme(self, name):
        if name in THEMES:
            self.apply_theme(THEMES[name])
            self.settings.setValue("theme", name)
            for action in self.theme_group:
                action.setChecked(action.text() == name)
    
    def toggle_console_tab(self, checked):
        if checked:
            if self.tabs.indexOf(self.console_widget) == -1:
                self.tabs.addTab(self.console_widget, "Console")
        else:
            idx = self.tabs.indexOf(self.console_widget)
            if idx != -1:
                self.tabs.removeTab(idx)
        self.settings.setValue("show_console", checked)
    
    def toggle_matchloadouts_tab(self, checked):
        if checked and not self.matchloadouts_web:
            if OPTIMIZED_WEBVIEW_AVAILABLE:
                self.matchloadouts_web = MatchLoadoutsContainer()
            else:
                self.matchloadouts_web = QWebEngineView()
                self.matchloadouts_web.load(QUrl("https://vry-ui.netlify.app/matchLoadouts"))
            self.tabs.addTab(self.matchloadouts_web, "Match Loadouts")
        elif not checked and self.matchloadouts_web:
            idx = self.tabs.indexOf(self.matchloadouts_web)
            if idx != -1:
                self.tabs.removeTab(idx)
            if hasattr(self.matchloadouts_web, 'cleanup'):
                self.matchloadouts_web.cleanup()
            self.matchloadouts_web = None
        self.settings.setValue("show_matchloadouts", checked)
    
    def toggle_vtl_tab(self, checked):
        if checked and not self.vtl_web:
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            
            search_layout = QHBoxLayout()
            search_layout.setContentsMargins(10, 10, 10, 10)
            search_layout.addWidget(QLabel("Lookup:"))
            
            self.vtl_search = QLineEdit()
            self.vtl_search.setPlaceholderText("Username#Tag")
            self.vtl_search.setMaximumWidth(300)
            self.vtl_search.returnPressed.connect(self.search_vtl)
            search_layout.addWidget(self.vtl_search)
            
            btn = QPushButton("Search")
            btn.clicked.connect(self.search_vtl)
            search_layout.addWidget(btn)
            search_layout.addStretch()
            
            search_widget = QWidget()
            search_widget.setLayout(search_layout)
            layout.addWidget(search_widget, 0)
            
            self.vtl_web = QWebEngineView()
            self.vtl_web.setHtml(f"<html><body style='background:{self.current_theme.background};color:{self.current_theme.text};display:flex;justify-content:center;align-items:center;height:100vh;font-family:Segoe UI'><div>Search a user to get started</div></body></html>")
            layout.addWidget(self.vtl_web, 1)
            
            self.vtl_container = container
            self.tabs.addTab(container, "VTL.lol")
        elif not checked and self.vtl_web:
            if hasattr(self, 'vtl_container'):
                idx = self.tabs.indexOf(self.vtl_container)
                if idx != -1:
                    self.tabs.removeTab(idx)
                self.vtl_container = None
            self.vtl_web = None
            self.vtl_search = None
        self.settings.setValue("show_vtl", checked)
    
    def search_vtl(self):
        if not self.vtl_search or not self.vtl_web:
            return
        text = self.vtl_search.text().strip()
        if not text:
            return
        if '#' in text:
            user, tag = text.split('#', 1)
            self.vtl_web.load(QUrl(f"https://vtl.lol/id/{user}_{tag}"))
        elif re.match(r"^[0-9a-fA-F-]{36}$", text):
            self.vtl_web.load(QUrl(f"https://vtl.lol/id/{text}"))
        else:
            self.status_bar.showMessage("Invalid format. Use Username#Tag", 3000)

    def start_vry(self):
        verbose = self.settings.value("verbose_level", 0, type=int)
        if verbose > 0:
            self.console_output.append("Starting VRY...\n")
        
        self.worker_thread = VRYWorkerThread(verbose)
        self.worker_thread.output_signal.connect(self.on_console_output)
        self.worker_thread.error_signal.connect(self.on_console_error)
        self.worker_thread.table_update_signal.connect(self.on_table_update)
        self.worker_thread.table_row_signal.connect(self.on_table_row_update)
        self.worker_thread.status_signal.connect(self.on_status_update)
        self.worker_thread.start()
    
    def refresh_data(self):
        if self.worker_thread and self.worker_thread.running:
            was_frozen = self.freeze_btn.isChecked()
            if was_frozen:
                self.freeze_btn.setChecked(False)
                self.toggle_freeze(False)
            self.status_bar.showMessage("Refreshing...", 2000)
            if was_frozen:
                QTimer.singleShot(500, lambda: (self.freeze_btn.setChecked(True), self.toggle_freeze(True)))
    
    def on_console_output(self, text):
        self.console_output.append(text)
    
    def on_console_error(self, text):
        self.console_output.append(f"ERROR: {text}")
        self.status_bar.showMessage(f"Error: {text}", 5000)
    
    def on_table_row_update(self, row_data, metadata):
        if not self.freeze_btn.isChecked():
            md = dict(metadata)
            md['incognito_privacy'] = self.incognito_action.isChecked()
            self.player_table.add_row_streaming(row_data, md)
    
    def on_table_update(self, data, metadata):
        self.player_table_data = data
        md = dict(metadata)
        md['incognito_privacy'] = self.incognito_action.isChecked()
        self.player_table_metadata = md
        
        if not self.freeze_btn.isChecked():
            self.player_table.update_table(data, md)
            self.status_bar.showMessage(f"Updated: {len(data)} players", 3000)
    
    def on_status_update(self, state, extra):
        display = {"INGAME": "In-Game", "PREGAME": "Agent Select", "MENUS": "In-Menus"}.get(state, state)
        text = f"Status: {display}"
        if extra:
            if "Attacker" in extra:
                extra = extra.replace("Attacker", "⚔ Attacker")
            elif "Defender" in extra:
                extra = extra.replace("Defender", "🛡 Defender")
            text += f" • {extra}"
        self.status_label.setText(text)
    
    def on_incognito_changed(self, checked):
        self.settings.setValue("incognito_privacy", checked)
        if self.player_table_data:
            self.on_table_update(self.player_table_data, self.player_table_metadata)
    
    def load_settings(self):
        theme = self.settings.value("theme", "Dark")
        if theme in THEMES:
            self.change_theme(theme)
        
        self.toggle_matchloadouts.setChecked(self.settings.value("show_matchloadouts", True, type=bool))
        self.toggle_vtl.setChecked(self.settings.value("show_vtl", False, type=bool))
        self.toggle_console.setChecked(self.settings.value("show_console", False, type=bool))
        
        if self.toggle_matchloadouts.isChecked():
            self.toggle_matchloadouts_tab(True)
        if self.toggle_vtl.isChecked():
            self.toggle_vtl_tab(True)
        if self.toggle_console.isChecked():
            self.toggle_console_tab(True)
        
        self.incognito_action.setChecked(self.settings.value("incognito_privacy", True, type=bool))
    
    def save_settings(self):
        self.settings.setValue("theme", self.current_theme.name)
        self.settings.setValue("show_matchloadouts", self.toggle_matchloadouts.isChecked())
        self.settings.setValue("show_vtl", self.toggle_vtl.isChecked())
        self.settings.setValue("show_console", self.toggle_console.isChecked())
        self.settings.setValue("incognito_privacy", self.incognito_action.isChecked())
    
    def closeEvent(self, event):
        self.save_settings()
        
        if self.matchloadouts_web and hasattr(self.matchloadouts_web, 'cleanup'):
            self.matchloadouts_web.cleanup()
        
        if self.worker_thread:
            self.worker_thread.stop()
            self.worker_thread.quit()
            if not self.worker_thread.wait(5000):
                self.worker_thread.terminate()
        
        event.accept()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        configure()
        if not inquirer.confirm(message="Run vRY now?", default=True).execute():
            sys.exit(0)
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName("VRY - UI v2.14")
    
    window = VRYMainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
