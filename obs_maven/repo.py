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

import os
import os.path
import shutil
import urllib.request
import xml.etree.ElementTree as ET
import zlib

from obs_maven.rpm import Rpm

class Repo:
    def __init__(self, uri, project, repository):
        self.uri = uri
        self.project = project.replace(':', ':/')
        self.repository = repository
        self._rpms = None

    def find_primary(self):
        ns = {'repo': 'http://linux.duke.edu/metadata/repo', 'rpm': 'http://linux.duke.edu/metadata/rpm'}
        f = urllib.request.urlopen(
            "{}/{}/{}/repodata/repomd.xml".format(self.uri, self.project, self.repository)
        )
        doc = ET.fromstring(f.read())
        primary_href = doc.find("./repo:data[@type='primary']/repo:location", ns).get("href")
        return "{}/{}/{}/{}".format(self.uri, self.project, self.repository, primary_href)

    def parse_primary(self):
        ns = {"c": "http://linux.duke.edu/metadata/common", "rpm":"http://linux.duke.edu/metadata/rpm"}
        f = urllib.request.urlopen(self.find_primary())
        primary_xml = zlib.decompress(f.read(), 16 + zlib.MAX_WBITS)
        doc = ET.fromstring(primary_xml)

        all_rpms = [
            Rpm(n.find("c:location", ns).get("href"),
                int(n.find("c:time", ns).get("file")),

                n.find("c:name", ns).text,
                n.find("c:version", ns))
            for n
            in doc.findall(".//c:package", ns)
            if n.find("c:arch", ns).text in ["x86_64", "noarch"]
        ]
        latest_rpms = {}
        for rpm in all_rpms:
            latest = latest_rpms.get(rpm.pkgname)
            if latest is None or latest.compare(rpm):
                latest_rpms[rpm.pkgname] = rpm
        self._rpms = latest_rpms.values()

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
        target_f = open(target, 'wb')
        shutil.copyfileobj(f, target_f)
        target_f.close()
        f.close()
        os.utime(target, (mtime, mtime))
