"""
uav_assistant
=============
LLM tabanlı İHA (drone) pilot asistanı prototipi.

Modüller:
    simulation         : 3B drone simülasyonu ve durum (state) yönetimi
    safety             : Güvenlik katmanı (kural tabanlı komut doğrulama)
    tools              : Güvenli araç fonksiyonları (get_telemetry, takeoff,
                         land, return_to_home, go_to)
    logger             : JSON/CSV loglama sistemi
    agent              : Doğal dil arayüzü (hibrit: kural tabanlı + opsiyonel
                         LLM) + çok-adımlı görev planlama
    scenario_generator : Rastgele test senaryosu üreticisi (özgün özellik)
"""

from .simulation import DroneSimulator, DroneState, FlightMode
from .safety import SafetyLayer, SafetyDecision
from .tools import DroneTools, ToolResult
from .logger import MissionLogger
from .agent import DronePilotAgent, RuleBasedNLU, LLMBackend, Intent
from . import scenario_generator
from .visualize import save_map
from .simulation import KeepOut

__all__ = [
    "DroneSimulator", "DroneState", "FlightMode",
    "SafetyLayer", "SafetyDecision",
    "DroneTools", "ToolResult",
    "MissionLogger",
    "DronePilotAgent", "RuleBasedNLU", "LLMBackend", "Intent",
    "scenario_generator", "save_map", "KeepOut",
]

__version__ = "1.0.0"
