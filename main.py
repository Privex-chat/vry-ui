"""
VRY - UI v2.12
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
ANSI_RGB_RE = re.compile(r'\x1B\[38;2;(\d+);(\d+);(\d+)m')
ANSI_ANY_RE = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
ANSI_RESET_RE = re.compile(r'\x1B\[0m')

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
    print(f"Error getting system info: {e}")
    sys.exit(1)

try:
    import psutil
    import platform
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    from src.webview import MatchLoadoutsContainer
    OPTIMIZED_WEBVIEW_AVAILABLE = True
except ImportError:
    print("Warning: webview.py not found. Using standard WebView.")
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
    "Dark": Theme(
        "Dark",
        background="#1a1a1a",
        text="#e0e0e0",
        border="#333333",
        alternate="#252525",
        selection="#3d3d3d",
        header="#2b2b2b",
        table_bg="#1e1e1e",
        table_text="#ffffff",
        table_grid="#2a2a2a",
        status_bg="#007acc",
        accent="#007acc"
    ),
    "Light": Theme(
        "Light",
        background="#f5f5f5",
        text="#333333",
        border="#cccccc",
        alternate="#e8e8e8",
        selection="#d0e3ff",
        header="#e0e0e0",
        table_bg="#ffffff",
        table_text="#000000",
        table_grid="#dddddd",
        status_bg="#0078d4",
        accent="#0078d4"
    ),
    "Midnight": Theme(
        "Midnight",
        background="#0d1117",
        text="#c9d1d9",
        border="#30363d",
        alternate="#161b22",
        selection="#1f6feb",
        header="#010409",
        table_bg="#0d1117",
        table_text="#c9d1d9",
        table_grid="#21262d",
        status_bg="#1f6feb",
        accent="#58a6ff"
    ),
    "Valorant": Theme(
        "Valorant",
        background="#0f1923",
        text="#ffffff",
        border="#ff4655",
        alternate="#1b2838",
        selection="#ff4655",
        header="#111111",
        table_bg="#0f1923",
        table_text="#ffffff",
        table_grid="#ff4655",
        status_bg="#ff4655",
        accent="#ff4655"
    )
}


class VRYWorkerThread(QThread):
    
    output_signal = Signal(str)
    error_signal = Signal(str)
    table_update_signal = Signal(list, dict)
    status_signal = Signal(str, str)
    
    def __init__(self, verbose_level=0):
        super().__init__()
        self.running = False
        self.initialized = False
        self.game_state = None
        self.firstTime = True
        self.verbose_level = verbose_level
        self.loop = None
        
    def initialize_vry(self):
        try:
            self.Logging = Logging()
            self.log = self.Logging.log
            
            if self.verbose_level > 0:
                self.output_signal.emit(f"Operating system: {get_os()}\n")
            
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
            
            if self.cfg.get_feature_flag("discord_rpc"):
                self.rpc = Rpc(self.map_urls, gamemodes, self.colors, self.log)
            else:
                self.rpc = None
            
            self.Wss = Ws(self.Requests.lockfile, self.Requests, self.cfg, 
                         self.colors, hide_names, self.Server, self.rpc)
            
            self.valoApiSkins = requests.get("https://valorant-api.com/v1/weapons/skins")
            self.gameContent = self.content.get_content()
            self.seasonID = self.content.get_latest_season_id(self.gameContent)
            self.previousSeasonID = self.content.get_previous_season_id(self.gameContent)
            
            self.seasonActEp = self.content.get_act_episode_from_act_id(self.seasonID)
            self.previousSeasonActEp = self.content.get_act_episode_from_act_id(self.previousSeasonID)
            
            self.initialized = True
            self.output_signal.emit(f"VRY Mobile - {self.get_ip()}:{self.cfg.port}")
            if self.verbose_level > 0:
                self.output_signal.emit("Initialization complete")
            
        except Exception as e:
            self.error_signal.emit(f"Initialization error: {str(e)}")
            if self.verbose_level > 1:
                self.log(traceback.format_exc())
    
    def log(self, message):
        if self.verbose_level > 1:
            self.output_signal.emit(f"[DEBUG] {message}")
            
    def get_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            s.connect(("10.254.254.254", 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = "127.0.0.1"
        finally:
            s.close()
        return IP
    
    def run(self):
        self.running = True
        
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            if not self.initialized:
                self.initialize_vry()
                
            if not self.initialized:
                self.error_signal.emit("Failed to initialize VRY")
                return
            
            while self.running:
                try:
                    self.process_game_state()
                    for _ in range(20):
                        if not self.running:
                            break
                        self.msleep(100)
                except Exception as e:
                    if self.verbose_level > 0:
                        self.error_signal.emit(f"Processing error: {str(e)}")
                    if self.verbose_level > 1:
                        self.log(traceback.format_exc())
                    for _ in range(50):
                        if not self.running:
                            break
                        self.msleep(100)
        finally:
            if self.loop:
                try:
                    self.loop.close()
                except Exception:
                    pass
    
    def process_game_state(self):
        try:
            if self.firstTime:
                run = True
                while run and self.running:
                    presence = self.presences.get_presence()
                    if self.presences.get_private_presence(presence) is not None:
                        if self.cfg.get_feature_flag("discord_rpc"):
                            self.rpc.set_rpc(self.presences.get_private_presence(presence))
                        self.game_state = self.presences.get_game_state(presence)
                        if self.game_state is not None:
                            run = False
                    for _ in range(20):
                        if not self.running:
                            break
                        self.msleep(100)
                self.log(f"first game state: {self.game_state}")
                self.firstTime = False
            else:
                previous_game_state = self.game_state
                
                if self.loop and not self.loop.is_closed():
                    self.game_state = self.loop.run_until_complete(
                        self.Wss.recconect_to_websocket(self.game_state)
                    )
                else:
                    self.loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self.loop)
                    self.game_state = self.loop.run_until_complete(
                        self.Wss.recconect_to_websocket(self.game_state)
                    )
                
                if previous_game_state != self.game_state and self.game_state == "MENUS":
                    self.rank.invalidate_cached_responses()
                self.log(f"new game state: {self.game_state}")
            
            presence = self.presences.get_presence()
            priv_presence = self.presences.get_private_presence(presence)
            
            if priv_presence["provisioningFlow"] == "CustomGame" or priv_presence["partyState"] == "CUSTOM_GAME_SETUP":
                gamemode = "Custom Game"
            else:
                gamemode = gamemodes.get(priv_presence["queueId"])
            
            game_state_names = {
                "INGAME": "In-Game",
                "PREGAME": "Agent Select",
                "MENUS": "In-Menus"
            }
            self.status_signal.emit(self.game_state, gamemode)
            
            table_data = []
            metadata = {"state": self.game_state, "mode": gamemode}
            
            if self.game_state == "INGAME":
                table_data, metadata = self.process_ingame_state(presence)
            elif self.game_state == "PREGAME":
                table_data, metadata = self.process_pregame_state(presence)
            elif self.game_state == "MENUS":
                table_data, metadata = self.process_menu_state(presence)
            
            if table_data:
                self.table_update_signal.emit(table_data, metadata)
                
        except Exception as e:
            if self.verbose_level > 0:
                self.error_signal.emit(f"State processing error: {str(e)}")
            if self.verbose_level > 1:
                self.log(traceback.format_exc())
    
    def format_rank_with_act(self, rank_text, act, episode):
        if not rank_text or rank_text == "Unranked":
            return rank_text
        if act and episode:
            return f"{rank_text} ({episode}A{act})"
        return rank_text
    
    def process_ingame_state(self, presence):
        table_data = []
        metadata = {"state": "INGAME"}
        
        coregame_stats = self.coregame.get_coregame_stats()
        if not coregame_stats:
            return table_data, metadata
        
        Players = coregame_stats["Players"]
        partyMembers = self.menu.get_party_members(self.Requests.puuid, presence)
        partyMembersList = [a["Subject"] for a in partyMembers]
        
        players_data = {"ignore": partyMembersList}
        for player in Players:
            if player["Subject"] == self.Requests.puuid and self.cfg.get_feature_flag("discord_rpc"):
                self.rpc.set_data({"agent": player["CharacterID"]})
            players_data.update({
                player["Subject"]: {
                    "team": player["TeamID"],
                    "agent": player["CharacterID"],
                    "streamer_mode": player["PlayerIdentity"]["Incognito"]
                }
            })
        self.Wss.set_player_data(players_data)
        
        self.presences.wait_for_presence(self.namesClass.get_players_puuid(Players))
        names = self.namesClass.get_names_from_puuids(Players)
        
        try:
            loadouts_arr = self.loadoutsClass.get_match_loadouts(
                self.coregame.get_coregame_match_id(),
                Players, self.cfg.weapon, self.valoApiSkins, names, state="game"
            )
            loadouts = loadouts_arr[0]
        except (IndexError, KeyError) as e:
            self.log(f"Error fetching loadouts: {e}")
            loadouts = {}
        
        Players.sort(key=lambda p: p["PlayerIdentity"].get("AccountLevel"), reverse=True)
        Players.sort(key=lambda p: p["TeamID"], reverse=True)
        
        partyOBJ = self.menu.get_party_json(self.namesClass.get_players_puuid(Players), presence)
        partyIcons = {}
        partyCount = 0
        allyTeam = None
        for p in Players:
            if p["Subject"] == self.Requests.puuid:
                allyTeam = p["TeamID"]
                break
        
        for player in Players:
            party_icon = ""
            for party in partyOBJ:
                if player["Subject"] in partyOBJ[party]:
                    if party not in partyIcons:
                        partyIcons[party] = PARTYICONLIST[partyCount]
                        party_icon = PARTYICONLIST[partyCount]
                        partyCount += 1
                    else:
                        party_icon = partyIcons[party]
            
            playerRank = self.rank.get_rank(player["Subject"], self.seasonID)
            previousPlayerRank = self.rank.get_rank(player["Subject"], self.previousSeasonID)
            
            ppstats = self.pstats.get_stats(player["Subject"])
            
            row_data = {
                "party": party_icon,
                "agent": self.agent_dict.get(player["CharacterID"].lower(), ""),
                "name": names[player["Subject"]],
                "incognito": player["PlayerIdentity"]["Incognito"],
                "team": player["TeamID"],
                "ally_team": allyTeam,
                "is_self": player["Subject"] == self.Requests.puuid,
                "is_party": player["Subject"] in partyMembersList,
                "skin": loadouts.get(player["Subject"], ""),
                "rank": NUMBERTORANKS[playerRank["rank"]],
                "rank_act": self.seasonActEp.get("act"),
                "rank_ep": self.seasonActEp.get("episode"),
                "rr": playerRank["rr"],
                "peak_rank": NUMBERTORANKS[playerRank["peakrank"]],
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
            table_data.append(row_data)
            
            self.stats.save_data({
                player["Subject"]: {
                    "name": names[player["Subject"]],
                    "agent": self.agent_dict[player["CharacterID"].lower()],
                    "map": self.current_map,
                    "rank": playerRank["rank"],
                    "rr": playerRank["rr"],
                    "match_id": self.coregame.match_id,
                    "epoch": time.time()
                }
            })
        
        return table_data, metadata
    
    def process_pregame_state(self, presence):
        table_data = []
        metadata = {"state": "PREGAME"}
        
        pregame_stats = self.pregame.get_pregame_stats()
        if not pregame_stats:
            return table_data, metadata
        
        Players = pregame_stats["AllyTeam"]["Players"]
        self.presences.wait_for_presence(self.namesClass.get_players_puuid(Players))
        names = self.namesClass.get_names_from_puuids(Players)
        
        partyMembers = self.menu.get_party_members(self.Requests.puuid, presence)
        partyMembersList = [a["Subject"] for a in partyMembers]
        partyOBJ = self.menu.get_party_json(self.namesClass.get_players_puuid(Players), presence)
        
        Players.sort(key=lambda p: p["PlayerIdentity"].get("AccountLevel"), reverse=True)
        
        partyIcons = {}
        partyCount = 0
        
        for player in Players:
            party_icon = ""
            for party in partyOBJ:
                if player["Subject"] in partyOBJ[party]:
                    if party not in partyIcons:
                        partyIcons[party] = PARTYICONLIST[partyCount]
                        party_icon = PARTYICONLIST[partyCount]
                        partyCount += 1
                    else:
                        party_icon = partyIcons[party]
            
            playerRank = self.rank.get_rank(player["Subject"], self.seasonID)
            previousPlayerRank = self.rank.get_rank(player["Subject"], self.previousSeasonID)
            ppstats = self.pstats.get_stats(player["Subject"])
            teams = pregame_stats.get("Teams", [])
            team_id = teams[0]["TeamID"] if teams else None

            row_data = {
                "party": party_icon,
                "agent": self.agent_dict.get(player["CharacterID"].lower(), ""),
                "agent_state": player["CharacterSelectionState"],
                "name": names[player["Subject"]],
                "incognito": player["PlayerIdentity"]["Incognito"],
                "team": team_id,
                "is_self": player["Subject"] == self.Requests.puuid,
                "is_party": player["Subject"] in partyMembersList,
                "skin": "",
                "rank": NUMBERTORANKS[playerRank["rank"]],
                "rank_act": self.seasonActEp.get("act"),
                "rank_ep": self.seasonActEp.get("episode"),
                "rr": playerRank["rr"],
                "peak_rank": NUMBERTORANKS[playerRank["peakrank"]],
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
            table_data.append(row_data)
        
        return table_data, metadata
    
    def process_menu_state(self, presence):
        table_data = []
        metadata = {"state": "MENUS"}
        
        Players = self.menu.get_party_members(self.Requests.puuid, presence)
        names = self.namesClass.get_names_from_puuids(Players)
        
        Players.sort(key=lambda p: p["PlayerIdentity"].get("AccountLevel"), reverse=True)
        
        seen = []
        for player in Players:
            if player["Subject"] not in seen:
                playerRank = self.rank.get_rank(player["Subject"], self.seasonID)
                previousPlayerRank = self.rank.get_rank(player["Subject"], self.previousSeasonID)
                ppstats = self.pstats.get_stats(player["Subject"])
                
                row_data = {
                    "party": PARTYICONLIST[0],
                    "agent": "",
                    "name": names[player["Subject"]],
                    "incognito": False,
                    "is_self": player["Subject"] == self.Requests.puuid,
                    "is_party": True,
                    "skin": "",
                    "rank": NUMBERTORANKS[playerRank["rank"]],
                    "rank_act": self.seasonActEp.get("act"),
                    "rank_ep": self.seasonActEp.get("episode"),
                    "rr": playerRank["rr"],
                    "peak_rank": NUMBERTORANKS[playerRank["peakrank"]],
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
                table_data.append(row_data)
                seen.append(player["Subject"])
        
        return table_data, metadata
    
    def stop(self):
        self.running = False
        
        if self.loop and not self.loop.is_closed():
            try:
                pending = asyncio.all_tasks(self.loop)
                for task in pending:
                    task.cancel()
                self.loop.stop()
                self.loop.close()
            except Exception:
                pass
        
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


class VRYTableWidget(QTableWidget):
    
    def __init__(self):
        super().__init__()
        self.current_theme = THEMES["Dark"]
        self.setup_table()
        
    def setup_table(self):
        self.setColumnCount(14)
        headers = ["Party", "Agent", "Name", "Skin", "Rank", "RR", 
                  "Peak", "Previous", "Pos.", "HS%", "WR%", "K/D", "Level", "ΔRR"]
        self.setHorizontalHeaderLabels(headers)
        
        header_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        self.horizontalHeader().setFont(header_font)
        
        header = self.horizontalHeader()
        for col in range(self.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        stretch_columns = [2, 3, 4, 6, 7, 10]
        for col in stretch_columns:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)

        self.setColumnWidth(0, 50)
        self.setColumnWidth(1, 80)
        self.setColumnWidth(2, 140)
        self.setColumnWidth(3, 140)
        self.setColumnWidth(4, 120)
        self.setColumnWidth(5, 45)
        self.setColumnWidth(6, 120)
        self.setColumnWidth(7, 120)
        self.setColumnWidth(8, 45)
        self.setColumnWidth(9, 55)
        self.setColumnWidth(10, 75)
        self.setColumnWidth(11, 55)
        self.setColumnWidth(12, 55)
        self.setColumnWidth(13, 60)
        
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
            QTableWidget::item:hover {{
                background-color: {theme.alternate};
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
            QHeaderView::section:hover {{
                background-color: {theme.selection};
            }}
            QTableCornerButton::section {{
                background-color: {theme.header};
                border: none;
            }}
        """)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)

        total_width = self.viewport().width()
        weights = {
            2: 3,
            3: 2,
            4: 2,
            6: 2,
            7: 2,
            10: 1
        }

        total_weight = sum(weights.values())

        for col, w in weights.items():
            self.setColumnWidth(col, int(total_width * (w / total_weight)))

        compact_cols = [0, 1, 5, 8, 9, 11, 12, 13]
        for col in compact_cols:
            self.resizeColumnToContents(col)
            
            if self.columnWidth(col) < 40:
                self.setColumnWidth(col, 40)

    def update_table(self, data, metadata):
        self.setRowCount(0)

        def safe_float(value, default=0.0):
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

        def safe_int(value, default=0):
            try:
                return int(value)
            except (ValueError, TypeError):
                return default

        def parse_and_create_item(raw):
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
                    return item, True
                except Exception:
                    pass
            return item, False
        
        def format_rank_with_episode(rank_text, act, ep):
            if not rank_text or "Unranked" in str(rank_text):
                return rank_text
            clean_rank = ANSI_ANY_RE.sub("", str(rank_text))
            if act and ep:
                return f"{clean_rank} {ep}A{act}"
            return rank_text

        privacy_enabled = bool(metadata.get('incognito_privacy', True))

        for row_data in data:
            row_position = self.rowCount()
            self.insertRow(row_position)

            party_item, _ = parse_and_create_item(row_data.get("party", ""))
            party_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row_position, 0, party_item)

            agent_item, agent_colored = parse_and_create_item(row_data.get("agent", ""))
            if not agent_colored and "agent_state" in row_data:
                if row_data["agent_state"] == "locked":
                    agent_item.setForeground(QColor(255, 255, 255))
                elif row_data["agent_state"] == "selected":
                    agent_item.setForeground(QColor(128, 128, 128))
                else:
                    agent_item.setForeground(QColor(54, 53, 51))
            agent_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row_position, 1, agent_item)

            name_raw = row_data.get("name", "")
            incog_flag = bool(row_data.get("incognito", False))
            is_self = bool(row_data.get("is_self", False))
            is_party = bool(row_data.get("is_party", False))

            if incog_flag and privacy_enabled and not is_self and not is_party:
                name_item = QTableWidgetItem("Incognito")
                font = QFont()
                font.setBold(True)
                name_item.setFont(font)
                name_item.setForeground(QColor(128, 0, 0))
                skip_team_coloring = True
            else:
                display_name = ("*" + str(name_raw)) if (incog_flag and not privacy_enabled) else str(name_raw)
                name_item, name_colored = parse_and_create_item(display_name)
                skip_team_coloring = False

            if not skip_team_coloring and not name_colored:
                if is_self:
                    name_item.setForeground(QColor(255, 215, 0))
                elif is_party:
                    name_item.setForeground(QColor(76, 151, 237))
                elif "team" in row_data and "ally_team" in row_data:
                    if row_data["team"] == row_data.get("ally_team"):
                        name_item.setForeground(QColor(0, 255, 127))
                    else:
                        name_item.setForeground(QColor(255, 69, 0))

            self.setItem(row_position, 2, name_item)

            skin_item, _ = parse_and_create_item(row_data.get("skin", ""))
            self.setItem(row_position, 3, skin_item)

            rank_text = format_rank_with_episode(
                row_data.get("rank", ""),
                row_data.get("rank_act"),
                row_data.get("rank_ep")
            )
            rank_item, _ = parse_and_create_item(rank_text)
            self.setItem(row_position, 4, rank_item)

            rr_val = safe_int(row_data.get("rr", 0))
            rr_item = QTableWidgetItem(str(rr_val))
            rr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row_position, 5, rr_item)

            peak_text = format_rank_with_episode(
                row_data.get("peak_rank", ""),
                row_data.get("peak_act"),
                row_data.get("peak_ep")
            )
            peak_item, _ = parse_and_create_item(peak_text)
            self.setItem(row_position, 6, peak_item)

            prev_text = format_rank_with_episode(
                row_data.get("previous_rank", ""),
                row_data.get("previous_act"),
                row_data.get("previous_ep")
            )
            prev_item, _ = parse_and_create_item(prev_text)
            self.setItem(row_position, 7, prev_item)

            lb_val = safe_int(row_data.get("leaderboard", 0))
            lb_item = QTableWidgetItem(str(lb_val) if lb_val > 0 else "")
            lb_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row_position, 8, lb_item)

            hs_val = row_data.get("hs", "N/A")
            if hs_val != "N/A":
                hs_display = f"{safe_float(hs_val):.1f}%"
            else:
                hs_display = "N/A"
            hs_item = QTableWidgetItem(hs_display)
            hs_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row_position, 9, hs_item)

            wr_val = row_data.get("wr", "N/a")
            games_val = safe_int(row_data.get("games", 0))
            if wr_val != "N/a":
                wr_display = f"{safe_int(wr_val)}% ({games_val})"
            else:
                wr_display = f"N/A ({games_val})"
            wr_item = QTableWidgetItem(wr_display)
            wr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row_position, 10, wr_item)

            kd_val = row_data.get("kd", "N/A")
            if kd_val != "N/A":
                kd_display = f"{safe_float(kd_val):.2f}"
            else:
                kd_display = "N/A"
            kd_item = QTableWidgetItem(kd_display)
            kd_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row_position, 11, kd_item)

            level_val = row_data.get("level", "")
            if row_data.get("hide_level") and not is_self and not is_party:
                level_val = ""
            level_item = QTableWidgetItem(str(level_val))
            level_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row_position, 12, level_item)

            earned_rr = row_data.get("earned_rr", "N/A")
            afk_penalty = row_data.get("afk_penalty", "N/A")
            
            if earned_rr != "N/A" and afk_penalty != "N/A":
                earned_display = f"{earned_rr:+d}"
                if afk_penalty != 0:
                    earned_display += f" ({afk_penalty})"
                rr_item = QTableWidgetItem(earned_display)
                if earned_rr > 0:
                    rr_item.setForeground(QColor(0, 255, 0))
                elif earned_rr < 0:
                    rr_item.setForeground(QColor(255, 0, 0))
            else:
                rr_item = QTableWidgetItem("")
            
            rr_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row_position, 13, rr_item)

        self.resizeColumnsToContents()
        
        if metadata.get("state") == "MENUS":
            self.setColumnHidden(0, True)
            self.setColumnHidden(1, True)
            self.setColumnHidden(3, True)
        else:
            self.setColumnHidden(0, False)
            self.setColumnHidden(1, False)
            self.setColumnHidden(3, metadata.get("state") == "PREGAME")


class ThemeCustomizationDialog(QDialog):
    
    def __init__(self, parent=None, current_theme=None):
        super().__init__(parent)
        self.setWindowTitle("Customize Theme")
        self.setModal(True)
        self.current_theme = current_theme or THEMES["Dark"]
        
        theme_attrs = {k: v for k, v in vars(self.current_theme).items() if k != 'name'}
        self.custom_theme = Theme("Custom", **theme_attrs)
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        color_grid = QGridLayout()
        
        self.color_buttons = {}
        color_properties = [
            ("Background", "background"),
            ("Text", "text"),
            ("Border", "border"),
            ("Selection", "selection"),
            ("Table Background", "table_bg"),
            ("Table Text", "table_text"),
            ("Accent", "accent")
        ]
        
        for i, (label, prop) in enumerate(color_properties):
            color_grid.addWidget(QLabel(label + ":"), i, 0)
            
            btn = QPushButton()
            color_value = getattr(self.custom_theme, prop)
            btn.setStyleSheet(f"background-color: {color_value}; border: 1px solid #000;")
            btn.clicked.connect(lambda checked, p=prop, b=btn: self.choose_color(p, b))
            self.color_buttons[prop] = btn
            
            color_grid.addWidget(btn, i, 1)
        
        layout.addLayout(color_grid)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    def choose_color(self, property_name, button):
        current_color = QColor(getattr(self.custom_theme, property_name))
        color = QColorDialog.getColor(current_color, self, f"Choose {property_name} color")
        
        if color.isValid():
            hex_color = color.name()
            setattr(self.custom_theme, property_name, hex_color)
            button.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #000;")
    
    def get_custom_theme(self):
        return self.custom_theme


class VRYMainWindow(QMainWindow):
    
    def __init__(self):
        super().__init__()
        
        self.settings = QSettings("VRY", "VRY - UI v2")
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
            self.resource_timer.start(30000)
        
        QTimer.singleShot(100, self.start_vry)
    
    def monitor_resources(self):
        if not PSUTIL_AVAILABLE or not self.show_resource_warning:
            return
            
        try:
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            if memory.percent > 90 or cpu_percent > 95:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowTitle("High Resource Usage")
                msg.setText(
                    f"System resources are running low:\n"
                    f"Memory Usage: {memory.percent:.1f}%\n"
                    f"CPU Usage: {cpu_percent:.1f}%"
                )
                msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg.exec()
                
        except Exception as e:
            print(f"Resource monitoring error: {e}")
    
    def init_ui(self):
        self.setWindowTitle("VRY - UI v2.12")
        self.setGeometry(100, 100, 1400, 850)
        self.setWindowIcon(QIcon("icon.ico"))
        
        app_font = QFont("Segoe UI", 9)
        self.setFont(app_font)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.create_menu_bar()
        
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        main_layout.addWidget(self.tabs)
        
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
        
        self.refresh_btn = QPushButton("↻ Refresh")
        self.refresh_btn.setMaximumWidth(100)
        self.refresh_btn.clicked.connect(self.refresh_data)
        status_layout.addWidget(self.refresh_btn)
        
        vry_layout.addWidget(status_panel)
        
        self.player_table = VRYTableWidget()
        vry_layout.addWidget(self.player_table)
        
        self.tabs.addTab(vry_widget, "Players")
        
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
    
    def create_menu_bar(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu('File')
        
        refresh_action = QAction('Refresh Data', self)
        refresh_action.setShortcut('F5')
        refresh_action.triggered.connect(self.refresh_data)
        file_menu.addAction(refresh_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('Exit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        view_menu = menubar.addMenu('View')
        
        theme_menu = view_menu.addMenu('Theme')
        
        self.theme_group = []
        for theme_name in THEMES.keys():
            action = QAction(theme_name, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, t=theme_name: self.change_theme(t))
            theme_menu.addAction(action)
            self.theme_group.append(action)
        
        theme_menu.addSeparator()
        
        custom_theme_action = QAction('Customize...', self)
        custom_theme_action.triggered.connect(self.customize_theme)
        theme_menu.addAction(custom_theme_action)
        
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
        
        settings_menu = view_menu.addMenu('Settings')
        
        incognito_action = QAction('Incognito Privacy', self)
        incognito_action.setCheckable(True)
        incognito_action.setChecked(True)
        incognito_action.triggered.connect(self.on_incognito_privacy_changed)
        settings_menu.addAction(incognito_action)
        self.incognito_privacy_menu_action = incognito_action
        
        settings_menu.addSeparator()
        
        verbose_menu = settings_menu.addMenu('Console Verbosity')
        self.verbose_group = []
        
        verbose_levels = [
            ("Disabled", 0),
            ("Errors Only", 1),
            ("Normal", 2),
            ("Debug", 3)
        ]
        
        for label, level in verbose_levels:
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, l=level: self.set_verbose_level(l))
            verbose_menu.addAction(action)
            self.verbose_group.append((action, level))
    
    def apply_theme(self, theme):
        self.current_theme = theme
        
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {theme.background};
            }}
            QWidget {{
                background-color: {theme.background};
                color: {theme.text};
            }}
            QTabWidget::pane {{
                border: 1px solid {theme.border};
                background-color: {theme.background};
            }}
            QTabBar::tab {{
                background-color: {theme.header};
                color: {theme.text};
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {theme.selection};
                border-bottom: 3px solid {theme.accent};
            }}
            QTabBar::tab:hover {{
                background-color: {theme.alternate};
            }}
            QPushButton {{
                background-color: {theme.selection};
                color: {theme.text};
                border: 1px solid {theme.border};
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {theme.alternate};
                border: 1px solid {theme.accent};
            }}
            QPushButton:pressed {{
                background-color: {theme.header};
            }}
            QLabel {{
                color: {theme.text};
                padding: 4px;
            }}
            QStatusBar {{
                background-color: {theme.status_bg};
                color: white;
                font-weight: bold;
            }}
            QMenuBar {{
                background-color: {theme.header};
                color: {theme.text};
            }}
            QMenuBar::item:selected {{
                background-color: {theme.selection};
            }}
            QMenu {{
                background-color: {theme.background};
                color: {theme.text};
                border: 1px solid {theme.border};
            }}
            QMenu::item:selected {{
                background-color: {theme.selection};
            }}
            QComboBox {{
                background-color: {theme.selection};
                color: {theme.text};
                border: 1px solid {theme.border};
                padding: 5px;
                border-radius: 3px;
            }}
            QComboBox:hover {{
                border: 1px solid {theme.accent};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {theme.background};
                color: {theme.text};
                selection-background-color: {theme.selection};
            }}
            QTextEdit {{
                background-color: {theme.table_bg};
                color: {theme.text};
                border: 1px solid {theme.border};
            }}
            QLineEdit {{
                background-color: {theme.table_bg};
                color: {theme.text};
                border: 1px solid {theme.border};
                padding: 5px;
                border-radius: 3px;
            }}
            QLineEdit:focus {{
                border: 1px solid {theme.accent};
            }}
            QCheckBox {{
                color: {theme.text};
                spacing: 5px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {theme.border};
                border-radius: 3px;
                background-color: {theme.table_bg};
            }}
            QCheckBox::indicator:checked {{
                background-color: {theme.accent};
                border-color: {theme.accent};
            }}
            QCheckBox::indicator:hover {{
                border-color: {theme.accent};
            }}
        """)
        
        if hasattr(self, 'player_table'):
            self.player_table.apply_theme(theme)
        
        if hasattr(self, 'console_output'):
            self.console_output.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {theme.table_bg};
                    color: {theme.text};
                    border: none;
                }}
            """)
    
    def change_theme(self, theme_name):
        if theme_name in THEMES:
            self.apply_theme(THEMES[theme_name])
            self.settings.setValue("theme", theme_name)
            
            for action in self.theme_group:
                action.setChecked(action.text() == theme_name)
    
    def customize_theme(self):
        dialog = ThemeCustomizationDialog(self, self.current_theme)
        if dialog.exec():
            custom_theme = dialog.get_custom_theme()
            THEMES["Custom"] = custom_theme
            self.change_theme("Custom")
    
    def set_verbose_level(self, level):
        self.settings.setValue("verbose_level", level)
        
        for action, action_level in self.verbose_group:
            action.setChecked(action_level == level)
        
        if self.worker_thread:
            self.worker_thread.verbose_level = level
    
    def toggle_console_tab(self, checked):
        if checked:
            if self.tabs.indexOf(self.console_widget) == -1:
                self.tabs.addTab(self.console_widget, "Console")
        else:
            index = self.tabs.indexOf(self.console_widget)
            if index != -1:
                self.tabs.removeTab(index)
        
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
            index = self.tabs.indexOf(self.matchloadouts_web)
            if index != -1:
                self.tabs.removeTab(index)
            
            if hasattr(self.matchloadouts_web, 'cleanup'):
                self.matchloadouts_web.cleanup()
            self.matchloadouts_web = None
        
        self.settings.setValue("show_matchloadouts", checked)
    
    def toggle_vtl_tab(self, checked):
        if checked and not self.vtl_web:
            vtl_container = QWidget()
            vtl_layout = QVBoxLayout(vtl_container)
            vtl_layout.setContentsMargins(0, 0, 0, 0)
            
            search_layout = QHBoxLayout()
            search_layout.setContentsMargins(10, 10, 10, 10)
            
            search_label = QLabel("Lookup:")
            search_layout.addWidget(search_label)
            
            self.vtl_search_input = QLineEdit()
            self.vtl_search_input.setPlaceholderText("Username#Tag")
            self.vtl_search_input.setMaximumWidth(300)
            self.vtl_search_input.returnPressed.connect(self.search_vtl_account)
            search_layout.addWidget(self.vtl_search_input)
            
            search_btn = QPushButton("Search")
            search_btn.clicked.connect(self.search_vtl_account)
            search_layout.addWidget(search_btn)
            
            search_layout.addStretch()
            
            search_widget = QWidget()
            search_widget.setLayout(search_layout)
            vtl_layout.addWidget(search_widget, 0)
            
            self.vtl_web = QWebEngineView()

            placeholder_html = f"""
            <html>
            <head>
            <style>
                body {{
                    background-color: {self.current_theme.background};
                    color: {self.current_theme.text};
                    font-family: 'Segoe UI', Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                }}
                .message {{
                    font-size: 20px;
                    font-weight: 500;
                }}
            </style>
            </head>
            <body>
                <div class="message">Type and search a User to get started</div>
            </body>
            </html>
            """
            self.vtl_web.setHtml(placeholder_html)

            vtl_layout.addWidget(self.vtl_web, 1)
            
            self.vtl_container = vtl_container
            self.tabs.addTab(self.vtl_container, "VTL.lol")
            
        elif not checked and self.vtl_web:
            if hasattr(self, 'vtl_container'):
                index = self.tabs.indexOf(self.vtl_container)
                if index != -1:
                    self.tabs.removeTab(index)
                self.vtl_container = None
            self.vtl_web = None
            self.vtl_search_input = None
        
        self.settings.setValue("show_vtl", checked)
    
    def search_vtl_account(self):
        if not self.vtl_search_input or not self.vtl_web:
            return
        
        search_text = self.vtl_search_input.text().strip()
        if not search_text:
            return

        try:
            if re.match(r"^[0-9a-fA-F-]{36}$", search_text):
                vtl_url = f"https://vtl.lol/id/{search_text}"
                self.vtl_web.load(QUrl(vtl_url))
                self.status_bar.showMessage(f"Searching by PUUID: {search_text}", 3000)
            elif '#' in search_text:
                username, tag = search_text.split('#', 1)
                vtl_url = f"https://vtl.lol/id/{username}_{tag}"
                self.vtl_web.load(QUrl(vtl_url))
                self.status_bar.showMessage(f"Searching: {search_text}", 3000)
            else:
                self.status_bar.showMessage("Invalid input. Use Username#Tag or a valid PUUID", 4000)
        except Exception as e:
            self.status_bar.showMessage(f"Error: {str(e)}", 3000)

    def start_vry(self):
        verbose_level = self.settings.value("verbose_level", 0, type=int)
        
        if verbose_level > 0:
            self.console_output.append("Starting VALORANT Rank Yoinker...\n")
        
        self.worker_thread = VRYWorkerThread(verbose_level)
        self.worker_thread.output_signal.connect(self.on_console_output)
        self.worker_thread.error_signal.connect(self.on_console_error)
        self.worker_thread.table_update_signal.connect(self.on_table_update)
        self.worker_thread.status_signal.connect(self.on_status_update)
        self.worker_thread.start()
    
    def refresh_data(self):
        if self.worker_thread and self.worker_thread.running:
            if self.worker_thread.verbose_level > 0:
                self.console_output.append("Refreshing data...\n")
            self.status_bar.showMessage("Refreshing...", 2000)
    
    def on_console_output(self, text):
        self.console_output.append(text)
    
    def on_console_error(self, text):
        self.console_output.append(f"ERROR: {text}")
        self.status_bar.showMessage(f"Error: {text}", 5000)
    
    def on_table_update(self, data, metadata):
        self.player_table_data = data
        md = dict(metadata) if metadata else {}
        md['incognito_privacy'] = self.incognito_privacy_menu_action.isChecked()
        self.player_table_metadata = md
        
        self.player_table.update_table(data, md)
        self.status_bar.showMessage(f"Updated: {len(data)} players", 3000)
    
    def on_status_update(self, state, extra_info):
        state_display = {
            "INGAME": "🎮 In-Game",
            "PREGAME": "🎯 Agent Select",
            "MENUS": "📋 In-Menus"
        }.get(state, state)
        
        status_text = f"Status: {state_display}"
        if extra_info:
            status_text += f" • {extra_info}"
        
        self.status_label.setText(status_text)
    
    def on_incognito_privacy_changed(self, checked):
        if self.worker_thread:
            try:
                self.worker_thread.incognito_privacy = checked
            except:
                pass
        
        self.settings.setValue("incognito_privacy", checked)
        
        if self.player_table_data and self.player_table_metadata:
            self.on_table_update(self.player_table_data, self.player_table_metadata)
    
    def load_settings(self):
        theme_name = self.settings.value("theme", "Dark")
        if theme_name in THEMES:
            self.change_theme(theme_name)
        
        show_matchloadouts = self.settings.value("show_matchloadouts", True, type=bool)
        show_vtl = self.settings.value("show_vtl", False, type=bool)
        show_console = self.settings.value("show_console", False, type=bool)
        
        self.toggle_matchloadouts.setChecked(show_matchloadouts)
        self.toggle_vtl.setChecked(show_vtl)
        self.toggle_console.setChecked(show_console)
        
        if show_matchloadouts:
            self.toggle_matchloadouts_tab(True)
        if show_vtl:
            self.toggle_vtl_tab(True)
        if show_console:
            self.toggle_console_tab(True)
        
        incognito_privacy = self.settings.value("incognito_privacy", True, type=bool)
        self.incognito_privacy_menu_action.setChecked(incognito_privacy)
        
        verbose_level = self.settings.value("verbose_level", 0, type=int)
        for action, level in self.verbose_group:
            action.setChecked(level == verbose_level)
    
    def save_settings(self):
        self.settings.setValue("theme", self.current_theme.name)
        self.settings.setValue("show_matchloadouts", self.toggle_matchloadouts.isChecked())
        self.settings.setValue("show_vtl", self.toggle_vtl.isChecked())
        self.settings.setValue("show_console", self.toggle_console.isChecked())
        self.settings.setValue("incognito_privacy", self.incognito_privacy_menu_action.isChecked())
    
    def closeEvent(self, event):
        self.save_settings()
        
        if self.matchloadouts_web:
            if hasattr(self.matchloadouts_web, 'cleanup'):
                self.matchloadouts_web.cleanup()
        
        if self.worker_thread:
            self.worker_thread.stop()
            self.worker_thread.quit()
            self.worker_thread.wait(3000)

        event.accept()


def main():
    
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        configure()
        run_app = inquirer.confirm(
            message="Do you want to run vRY now?", default=True
        ).execute()
        if not run_app:
            sys.exit(0)
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName("VRY - UI v2.12")
    app.setOrganizationName("VRY")
    
    window = VRYMainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()