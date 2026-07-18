from enum import Enum


class ExecutionMode(str, Enum):
    OFFLINE = "offline"
    ONLINE = "online"
