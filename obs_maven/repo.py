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
    def __init__(self, base_url, project, repository, custom_url=None):
        self.base_url = base_url
        self.custom_url = custom_url
        if not custom_url:
            if project is not None and repository is not None:
                self.project = project.replace(":", ":/")
                self.repository = repository
            else:
                raise ValueError("Either 'project' and 'repository' or 'url' must be defined for the repository")
        self._rpms = None

    def get_repo_path(self, path):
        if self.custom_url is not None:
            return "{}/{}".format(self.custom_url, path)
        else:
            return "{}/{}/{}/{}".format(self.base_url, self.project, self.repository, path)

    def find_primary(self):
        ns = {"repo": "http://linux.duke.edu/metadata/repo", "rpm": "http://linux.duke.edu/metadata/rpm"}
        repomd_url = self.get_repo_path("repodata/repomd.xml")
        logging.debug("Parsing %s", repomd_url)
        f = urllib.request.urlopen(repomd_url)
        doc = ET.fromstring(f.read())
        primary_href = doc.find("./repo:data[@type='primary']/repo:location", ns).get("href")
        return self.get_repo_path(primary_href)

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
        url = self.get_repo_path(path)
        logging.debug("Getting binary from: %s", url)
        f = None
        target_f = None
        for cnt in range(1, 4):
            try:
                f = urllib.request.urlopen(url)
                target_f = open(target, "wb")
                shutil.copyfileobj(f, target_f)
                target_f.close()
                f.close()
                os.utime(target, (mtime, mtime))
                break
            except ConnectionResetError:
                if target_f:
                    target_f.close()
                    target_f = None
                if f:
                    f.close()
                    f = None
                if cnt < 3:
                    logging.debug("Getting binary try {}".format(cnt + 1))
                    time.sleep(2)
                else:
                    raise
