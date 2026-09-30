"""Shared infrastructure adopted from DishtaYantra: the YAML/properties
configuration system (PropertiesConfigurator, its parsers and typed accessors).

Copyright (c) 2025-2030 Ashutosh Sinha. All rights reserved.
"""
from .properties_configurator import ConfigurationManager, PropertiesConfigurator

__all__ = ["ConfigurationManager", "PropertiesConfigurator"]
