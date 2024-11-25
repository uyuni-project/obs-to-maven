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

from datetime import datetime
import errno
import logging
import os
import os.path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET


class Artifact:
    def __init__(self, config, repositories, group):
        self.artifact = config["artifact"]
        self.default_group = config.get("group", group)

        self.package = config.get("rpm") or config.get("package", self.artifact)
        if config.get("rpm"):
            logging.warning('artifact "rpm" property is deprecated')
        self.arch = config.get("arch", "noarch")
        self.repository = repositories.get(config["repository"])
        if not self.repository:
            raise RuntimeError("Missing repository definition: " + config["repository"])
        self.jar = config.get("jar")

    def get_binary(self):
        file_pattern = self.package if self.package.endswith("-") else self.package + "-[0-9]"
        excluded = ["javadoc", "examples", "manual", "test", "demo"]
        filtered = [
            file
            for file in self.repository.rpms
            if not bool([pattern for pattern in excluded if pattern in file.name]) and re.match(file_pattern, file.name)
        ]

        if len(filtered) > 1:
            raise RuntimeError(
                "Found more than one file for {}:\n  {}".format(
                    self.artifact, "\n  ".join([file.name for file in filtered])
                )
            )

        if len(filtered) == 0:
            raise RuntimeError('Found no file matching "{}" for {}'.format(file_pattern, self.artifact))
        return filtered[0]

    def fetch_binary(self, file, tmp):
        target_file = os.path.join(tmp, file.name)
        logging.info("Downloading %s" % target_file)
        self.repository.get_binary(file.path, target_file, file.mtime)
        if os.path.isfile(target_file):
            return target_file
        return None

    def extract(self, rpm_file, tmp, parse_pom):
        # Get the rpm tags
        rpm_process = subprocess.Popen(["rpm", "-q", "--xml", "-p", rpm_file], stdout=subprocess.PIPE)
        rpm_tags = ET.fromstring(rpm_process.communicate()[0])

        # Get the file links list and package version
        links = [node.text for node in rpm_tags.findall('.//rpmTag[@name="Filelinktos"]/*')]
        # Extract the version declared by the RPM
        rpm_version = rpm_tags.find(".//rpmTag[@name='Version']/").text

        # Get the files
        rpm_process = subprocess.Popen(["rpm", "-qlp", rpm_file], stdout=subprocess.PIPE)
        files = rpm_process.communicate()[0].splitlines()

        not_linked = [f.decode("utf-8") for (i, f) in enumerate(files) if links[i] is None]
        logging.debug("not linked:\n  %s" % "\n  ".join(not_linked))

        pattern = self.jar if self.jar is not None else self.artifact
        end_pattern = r"[^/]*\.jar" if self.jar is None or not self.jar.endswith(".jar") else ""
        full_pattern = "^/usr/.*/%s%s$" % (pattern, end_pattern)
        logging.debug("full pattern: %s" % full_pattern)

        jars = [f for f in not_linked if re.match("^/usr/.*/{}".format(end_pattern), f)]
        if len(jars) == 0:
            raise RuntimeError("Found no jar to extract in " + rpm_file)
        elif len(jars) > 1:
            to_extract = [f for f in jars if re.match(full_pattern, f)]
            if len(to_extract) == 0:
                raise RuntimeError("Found no jar matching {} in {}".format(pattern, rpm_file))
            elif len(to_extract) > 1:
                raise RuntimeError(
                    "Found several jars to extract in {}:\n  {}".format(rpm_file, "\n  ".join(to_extract))
                )
            jar_entry = to_extract[0]
        else:
            jar_entry = jars[0]

        # Parse the jar file version, optionally available in the file name
        matcher = re.search("%s-([0-9.]+).jar" % self.artifact, os.path.basename(jar_entry))
        if matcher:
            jar_version = matcher.group(1)
        else:
            jar_version = None

        # If specified, extract the pom and parse the data
        if parse_pom:
            (pom_group, pom_version) = self.parse_pom_information(rpm_file, not_linked, tmp)
        else:
            (pom_group, pom_version) = (None, None)

        # Extract the jar file from the RPM
        dst_path = os.path.join(tmp, os.path.basename(jar_entry))
        logging.info("extracting %s to %s" % (jar_entry, dst_path))
        Artifact.extract_file_from_rpm(tmp, rpm_file, dst_path, jar_entry)

        shutil.rmtree(os.path.join(tmp, "usr"))

        return dst_path, pom_group or self.default_group, pom_version or jar_version or rpm_version

    def parse_pom_information(self, rpm_file, file_list, tmp):
        # First check for a file named <artifact>.pom
        logging.debug("Searching pom for artifact %s" % self.artifact)
        poms = [f for f in file_list if re.match("^/usr/share/maven-poms/.*{}.pom".format(self.artifact), f)]
        if len(poms) == 0:
            # If no result, fallback to parse all available poms
            logging.debug("No direct pom file found. Searching all poms available")
            poms = [f for f in file_list if re.match("^/usr/share/maven-poms/.*.pom", f)]

        if len(poms) == 0:
            # Still no data available
            logging.debug("No pom available in the package")
            return None, None

        for pom_entry in poms:
            pom_dst_path = os.path.join(tmp, os.path.basename(pom_entry))
            logging.debug("Processing pom available at %s" % pom_entry)

            # Extract and parse the file
            Artifact.extract_file_from_rpm(tmp, rpm_file, pom_dst_path, pom_entry)
            pom_doc = ET.parse(pom_dst_path)
            project_tag = pom_doc.getroot()

            # Identify if the pom.xml file uses namespace: we need to ajust the xpaths
            ns = project_tag.tag[:-len("project")]
            artifact_tag = project_tag.find("./{}artifactId".format(ns))
            if artifact_tag is None or artifact_tag.text != self.artifact:
                logging.debug("artifact {} not found".format(self.artifact))
                continue

            # Search for a groupId tag, if not present check if it's available on the parent
            group_tag = project_tag.find("./{}groupId".format(ns))
            if group_tag is None:
                group_tag = project_tag.find("./{}parent/{}groupId".format(ns, ns))

            # Search for a version tag, if not present check if it's available on the parent
            version_tag = project_tag.find("./{}version".format(ns))
            if version_tag is None:
                version_tag = project_tag.find("./{}parent/{}version".format(ns, ns))

            if version_tag is not None and group_tag is not None:
                logging.info("Maven identifier is %s:%s:%s" % (group_tag.text, self.artifact, version_tag.text))
                return group_tag.text, version_tag.text

        return None, None

    def deploy(self, jar, group, version, repo, mtime):
        artifact_folder = os.path.join(repo, Artifact.format_as_directory(group), self.artifact)
        try:
            os.makedirs(os.path.join(artifact_folder, version))
        except OSError as e:
            if e.errno == errno.EEXIST:
                pass
            else:
                raise
        jar_path = os.path.join(artifact_folder, version, "%s-%s.jar" % (self.artifact, version))
        logging.info("deploying %s to %s" % (jar, jar_path))
        shutil.copyfile(jar, jar_path)
        logging.debug("Setting mtime %d on %s" % (mtime, jar_path))
        os.utime(jar_path, (mtime, mtime))

        pom = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>%s</groupId>
  <artifactId>%s</artifactId>
  <version>%s</version>
  <description>POM was created from obs-to-maven</description>
</project>""" % (
            group,
            self.artifact,
            version,
        )
        with open(os.path.join(artifact_folder, version, "%s-%s.pom" % (self.artifact, version)), "w") as fd:
            fd.write(pom)

        # Maintain metadata file repo/group/artifact/maven-metadata-local.xml
        metadata_path = os.path.join(artifact_folder, "maven-metadata-local.xml")
        update_time = datetime.strftime(datetime.now(), "%Y%m%d%H%M%S")
        write_anew = True
        if os.path.isfile(metadata_path):
            doc = ET.parse(metadata_path)
            versions_node = doc.find("versions")
            lastupdated_node = doc.find("lastUpdated")
            if versions_node is None or lastupdated_node is None:
                logging.warning("Invalid XML file: creating a new one: %s" % metadata_path)
            else:
                version_node = ET.SubElement(versions_node, "version")
                version_node.text = version
                lastupdated_node.text = update_time
                doc.write(metadata_path)
                write_anew = False

        # Something wrong happened or we don't have the file: create a fresh one
        if write_anew:
            xml = """<?xml version="1.0" encoding="UTF-8"?>
<metadata xmlns="http://maven.apache.org/METADATA/1.1.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/METADATA/1.1.0 https://maven.apache.org/xsd/repository-metadata-1.1.0.xsd">
  <groupId>%s</groupId>
  <artifactId>%s</artifactId>
  <versioning>
    <release>%s</release>
    <versions>
      <version>%s</version>
    </versions>
    <lastUpdated>%s</lastUpdated>
  </versioning>
</metadata>
""" % (
                group,
                self.artifact,
                version,
                version,
                update_time,
            )
            with open(metadata_path, "w") as fd:
                fd.write(xml)

    def process(self, repo, tmp, parse_pom):
        logging.info("Processing artifact %s" % self.artifact)
        file = self.get_binary()

        # Check if one of the artifact's jar has the same mtime. If so no need to update
        mtimes = [
            y
            for x in [
                [os.stat(os.path.join(root, f)).st_mtime for f in files if f.endswith(".jar")]
                for root, dirs, files in os.walk(repo)
                if "%s%s%s" % (os.path.sep, self.artifact, os.path.sep) in root
            ]
            for y in x
        ]

        if not [mtime for mtime in mtimes if file.mtime == int(mtime)]:
            logging.debug("package mtime: %d, [%s]" % (file.mtime, ", ".join(["%f" % t for t in mtimes])))
            rpm_file = self.fetch_binary(file, tmp)
            if rpm_file is None:
                raise RuntimeError("Failed to download " + file)

            # Find out the version
            m = re.match(".*-([^-]+)-[^-]+.[^.]+.rpm", rpm_file)
            if m is None:
                raise RuntimeError("Failed to get version of " + rpm_file)

            # Extract the jar and pom
            (jar, group, version) = self.extract(rpm_file, tmp, parse_pom)

            # Install in the repository
            self.deploy(jar, group, version, repo, file.mtime)
        else:
            logging.info("Skipping artifact %s" % self.artifact)

    @staticmethod
    def extract_file_from_rpm(tmp, rpm_file, dst_path, entry):
        old_pwd = os.getcwd()
        os.chdir(tmp)
        rpm2cpio = subprocess.Popen(("rpm2cpio", rpm_file), stdout=subprocess.PIPE)
        dst = open(dst_path, "wb")
        cpio = subprocess.Popen(
            ("cpio", "-id", "." + entry), stdin=rpm2cpio.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        ret = cpio.wait()
        dst.close()
        os.chdir(old_pwd)
        if ret != 0:
            raise RuntimeError("Failed to extract jar file {}: {}".format(entry, cpio.communicate()[1]))

        shutil.copy(os.path.join(tmp, "." + entry), dst_path)

    @staticmethod
    def format_as_directory(group):
        return group.replace(".", "/")
