from enum import Enum


class DependencyEvidenceType(str, Enum):
    VARIABLE_REFERENCE = "variable_reference"
    PATH_CORRESPONDENCE = "path_correspondence"
    EXPLICIT_REFERENCE = "explicit_reference"
    CONFIGURATION = "configuration"
