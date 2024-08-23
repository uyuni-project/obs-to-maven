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
# You should have re`ceived a copy of the GNU General Public License

import logging
import xml.sax.handler
import xml.sax

import obs_maven.rpm

COMMON_NS = "http://linux.duke.edu/metadata/common"
SEARCHED_CHARS = ["arch", "name"]


class Handler(xml.sax.handler.ContentHandler):
    """
    SAX parser handler for repository primary.xml files.
    """

    def __init__(self):
        super().__init__()
        self.package = None
        self.rpms = {}
        self.text = None

    def startElementNS(self, name, qname, attrs):
        searched_attrs = {
            "location": ["href"],
            "time": ["file"],
            "version": ["epoch", "ver", "rel"],
        }

        if name == (COMMON_NS, "package"):
            self.package = {}
        elif self.package is not None and name[0] == COMMON_NS and name[1] in searched_attrs:
            for attr_name in searched_attrs[name[1]]:
                if attr_name not in attrs.getQNames():
                    logging.error("missing %s %s attribute, ignoring package", name[1], attr_name)
                    self.package = None
                else:
                    value = attrs.getValueByQName(attr_name)
                    self.package["/".join([name[1], attr_name])] = value
        elif self.package is not None and name[0] == COMMON_NS and name[1] in SEARCHED_CHARS:
            self.text = ""

    def characters(self, content):
        if self.text is not None:
            self.text += content

    def endElementNS(self, name, qname):
        if name == (COMMON_NS, "package"):
            if self.package is not None and self.package["arch"] in ["x86_64", "noarch"]:
                pkg_name = self.package["name"]

                rpm = obs_maven.rpm.Rpm(
                    self.package["location/href"],
                    int(self.package["time/file"]),
                    pkg_name,
                    self.package["version/epoch"],
                    self.package["version/ver"],
                    self.package["version/rel"],
                )

                latest_rpm = self.rpms.get(pkg_name)
                if latest_rpm is None or latest_rpm.compare(rpm) >= 1:
                    self.rpms[pkg_name] = rpm
        elif self.package is not None and name[0] == COMMON_NS and name[1] in SEARCHED_CHARS:
            self.package[name[1]] = self.text
            self.text = None
