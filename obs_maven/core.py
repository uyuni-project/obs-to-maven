#!/usr/bin/python3

# Tool creating a maven repository out of rpms built by OBS
# Copyright (C) 2022  SUSE Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License

import argparse
import logging
import os
import os.path
import shutil
import sys
import tempfile
import yaml
import xml.etree.ElementTree as ET

from obs_maven.repo import Repo
from obs_maven.artifact import Artifact

logging.basicConfig(level=logging.INFO)


class Configuration:
    def __init__(self, config_path, repo, cache_path, allowed_artifacts):
        data = {}
        if os.path.isfile(config_path):
            f = open(config_path, "r")
            data = yaml.safe_load(f)
            f.close()
        self.url = data.get("url", "https://download.opensuse.org/repositories")
        self.repo = repo
        
        repositories = data.get("repositories", {})
        repos = {name: Repo(name, cache_path, self.url, data.get("project"), data.get("repository"), data.get("url")) for name, data in repositories.items()}

        self.artifacts = [
            Artifact(artifact, repos, data.get("group", "suse")) for artifact in data.get("artifacts", []) if not allowed_artifacts or artifact["artifact"] in allowed_artifacts
        ]

def main():
    ret = 0
    parser = argparse.ArgumentParser(
        description="OBS to Maven repository synchronization tool",
        conflict_handler="resolve",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("config", help="Path to the YAML configuration file")
    parser.add_argument("out", help="Path to the output maven repository")

    parser.add_argument(
        "-p",
        "--parse-pom",
        help="Extract the group id and the version information from the pom contained in the package",
        dest="parse_pom",
        action='store_true',
        default=False
    )

    parser.add_argument(
        "-a",
        "--artifact",
        help="Process only the specified artifact(s). Can be repeated multiple times",
        dest="allowed_artifacts",
        action='append',
        default=[]
    )

    parser.add_argument(
        "-c",
        "--cache",
        help="Path to the cache directory",
        dest="cache",
        default=".obs-to-maven-cache",
        type=str,
    )

    parser.add_argument(
        "-d",
        "--debug",
        help="Show debug messages",
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG,
        default=logging.INFO,
    )

    args = parser.parse_args()

    logging.getLogger().setLevel(args.loglevel)
    logging.debug("Reading configuration")
    config = Configuration(args.config, args.out, args.cache, args.allowed_artifacts)
    tmp = tempfile.mkdtemp(prefix="obsmvn-")
    try:
        for artifact in config.artifacts:
            artifact.process(config.repo, tmp, args.parse_pom)
    except RuntimeError as e:
        logging.error(e)
        ret = 1
    shutil.rmtree(tmp)
    return ret


if __name__ == "__main__":
    sys.exit(main())
