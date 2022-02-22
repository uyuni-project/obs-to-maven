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

import gzip
import logging
import os
import shutil
import urllib.request
import xml.sax
import xml.sax.handler
import xml.etree.ElementTree as ET
from xml.sax.xmlreader import InputSource

import obs_maven.primary_handler


class Repo:
    def __init__(self, uri, project, repository):
        self.uri = uri
        self.project = project.replace(":", ":/")
        self.repository = repository
        self._rpms = None

    def find_primary(self):
        ns = {"repo": "http://linux.duke.edu/metadata/repo", "rpm": "http://linux.duke.edu/metadata/rpm"}
        repomd_url = "{}/{}/{}/repodata/repomd.xml".format(self.uri, self.project, self.repository)
        logging.debug("Parsing %s", repomd_url)
        f = urllib.request.urlopen(repomd_url)
        doc = ET.fromstring(f.read())
        primary_href = doc.find("./repo:data[@type='primary']/repo:location", ns).get("href")
        return "{}/{}/{}/{}".format(self.uri, self.project, self.repository, primary_href)

    def parse_primary(self):
        primary_url = self.find_primary()
        logging.debug("Parsing primary %s", primary_url)
        with urllib.request.urlopen(primary_url) as primary_fd:
            with gzip.GzipFile(fileobj=primary_fd, mode="rb") as gzip_fd:
                parser = xml.sax.make_parser()
                handler = obs_maven.primary_handler.Handler()
                parser.setContentHandler(handler)
                parser.setFeature(xml.sax.handler.feature_namespaces, True)
                input_source = InputSource()
                input_source.setByteStream(gzip_fd)
                parser.parse(input_source)
                self._rpms = handler.rpms.values()

    @property
    def rpms(self):
        if not self._rpms:
            self.parse_primary()
        return self._rpms

    def get_binary(self, path, target, mtime):
        """
        Equivalent of osc.core.get_binary_file
        """
        f = urllib.request.urlopen("{}/{}/{}/{}".format(self.uri, self.project, self.repository, path))
        target_f = open(target, "wb")
        shutil.copyfileobj(f, target_f)
        target_f.close()
        f.close()
        os.utime(target, (mtime, mtime))
