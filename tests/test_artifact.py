import os
import tempfile
import unittest
from unittest import mock

from obs_maven.artifact import Artifact

RPM_VERSION = "9.9"


def make_artifact(**config):
    config.setdefault("artifact", "ehcache")
    config.setdefault("repository", "repo")
    return Artifact(config, {"repo": object()}, "org.example")


def run_extract(artifact, paths):
    """Run Artifact.extract() on a fake RPM listing `paths`, return (extracted entry, version)."""
    xml = (
        '<rpmHeader><rpmTag name="Version"><string>%s</string></rpmTag>'
        '<rpmTag name="Filelinktos">%s</rpmTag></rpmHeader>' % (RPM_VERSION, "<string/>" * len(paths))
    )

    def popen(args, **kwargs):
        output = xml.encode() if "--xml" in args else "\n".join(paths).encode()
        return mock.Mock(communicate=mock.Mock(return_value=(output, None)))

    extracted = []
    with mock.patch("obs_maven.artifact.subprocess.Popen", side_effect=popen), mock.patch(
        "obs_maven.artifact.Artifact.extract_file_from_rpm",
        side_effect=lambda tmp, rpm, dst, entry: extracted.append(entry),
    ), mock.patch("obs_maven.artifact.shutil.rmtree"):
        _, _, version = artifact.extract("/tmp/pkg.rpm", "/tmp", False)
    return extracted[0], version


class SelectionTest(unittest.TestCase):
    def test_artifact_jar_is_selected_among_several(self):
        paths = ["/usr/share/java/other.jar", "/usr/share/java/ehcache-3.11.1.jar"]
        entry, _ = run_extract(make_artifact(), paths)
        self.assertEqual("/usr/share/java/ehcache-3.11.1.jar", entry)

    def test_non_jar_files_are_ignored(self):
        paths = ["/usr/share/doc/ehcache/README", "/usr/share/java/ehcache.jar"]
        entry, _ = run_extract(make_artifact(), paths)
        self.assertEqual("/usr/share/java/ehcache.jar", entry)

    def test_jar_override_is_used_as_is(self):
        paths = ["/usr/share/java/ehcache.jar", "/usr/share/java/content-2.2.3.jar"]
        entry, _ = run_extract(make_artifact(jar=r"content-2\.2\.3\.jar"), paths)
        self.assertEqual("/usr/share/java/content-2.2.3.jar", entry)

    def test_jar_override_without_extension_matches_any_suffix(self):
        paths = ["/usr/share/java/ehcache.jar", "/usr/share/java/content-2.2.3.jar"]
        entry, _ = run_extract(make_artifact(jar="content-"), paths)
        self.assertEqual("/usr/share/java/content-2.2.3.jar", entry)

    def test_no_match_among_several_fails(self):
        paths = ["/usr/share/java/foo.jar", "/usr/share/java/bar.jar"]
        with self.assertRaises(RuntimeError):
            run_extract(make_artifact(), paths)


class ClassifierSelectionTest(unittest.TestCase):
    def test_classified_jar_is_selected_in_any_naming_and_folder(self):
        names = ["ehcache-jakarta.jar", "ehcache-3.11.1-jakarta.jar", "ehcache-jakarta-3.11.1.jar"]
        for folder in ["/usr/share/java", "/usr/share/java/ehcache"]:
            for name in names:
                with self.subTest(folder=folder, name=name):
                    expected = "%s/%s" % (folder, name)
                    decoys = ["ehcache.jar", "ehcache-3.11.1.jar", "other-jakarta.jar"]
                    paths = ["%s/%s" % (folder, n) for n in decoys] + [expected]
                    entry, _ = run_extract(make_artifact(classifier="jakarta"), paths)
                    self.assertEqual(expected, entry)

    def test_no_classified_jar_among_several_fails(self):
        paths = ["/usr/share/java/ehcache.jar", "/usr/share/java/other.jar"]
        with self.assertRaises(RuntimeError):
            run_extract(make_artifact(classifier="jakarta"), paths)

    def test_unclassified_jar_not_selected_for_classifier(self):
        paths = ["/usr/share/java/ehcache.jar", "/usr/share/java/ehcache-jakarta.jar"]
        entry, _ = run_extract(make_artifact(classifier="jakarta"), paths)
        self.assertEqual("/usr/share/java/ehcache-jakarta.jar", entry)


class VersionParsingTest(unittest.TestCase):
    def check(self, name, expected, **config):
        with self.subTest(name=name, config=config):
            _, version = run_extract(make_artifact(**config), ["/usr/share/java/" + name])
            self.assertEqual(expected, version)

    def test_classifier_naming_variants(self):
        self.check("ehcache-3.11.1-jakarta.jar", "3.11.1", classifier="jakarta")
        self.check("ehcache-jakarta-3.11.1.jar", "3.11.1", classifier="jakarta")

    def test_unversioned_classified_jar_uses_rpm_version(self):
        self.check("ehcache-jakarta.jar", RPM_VERSION, classifier="jakarta")

    def test_without_classifier(self):
        self.check("ehcache-3.11.1.jar", "3.11.1")
        self.check("ehcache.jar", RPM_VERSION)

    def test_jar_override_without_version_uses_rpm_version(self):
        self.check(
            "apache-commons-logging.jar",
            RPM_VERSION,
            artifact="commons-logging",
            jar=r"apache-commons-logging\.jar",
        )

    def test_jar_override_named_after_artifact_keeps_version(self):
        self.check("ehcache-3.11.1.jar", "3.11.1", jar=r"ehcache-3\.11\.1\.jar")


class FreshnessTest(unittest.TestCase):
    def test_other_group_only_matches_when_parsing_pom(self):
        with tempfile.TemporaryDirectory() as repo:
            version_dir = os.path.join(repo, "org", "other", "ehcache", "1.0")
            os.makedirs(version_dir)
            jar_path = os.path.join(version_dir, "ehcache-1.0.jar")
            with open(jar_path, "w") as jar_file:
                jar_file.write("unclassified")
            os.utime(jar_path, (123, 123))

            artifact = make_artifact(group="org/example")
            rpm_file = mock.Mock(mtime=123, name="ehcache-1.0-1.noarch.rpm")
            for parse_pom in (False, True):
                with self.subTest(parse_pom=parse_pom), mock.patch.object(
                    artifact, "get_binary", return_value=rpm_file
                ), mock.patch.object(
                    artifact, "fetch_binary", return_value="/tmp/ehcache-1.0-1.noarch.rpm"
                ) as fetch_binary, mock.patch.object(
                    artifact, "extract", return_value=("/tmp/ehcache.jar", "org.example", "1.0")
                ), mock.patch.object(artifact, "deploy") as deploy:
                    artifact.process(repo, "/tmp", parse_pom)

                    if parse_pom:
                        fetch_binary.assert_not_called()
                        deploy.assert_not_called()
                    else:
                        fetch_binary.assert_called_once_with(rpm_file, "/tmp")
                        deploy.assert_called_once_with("/tmp/ehcache.jar", "org.example", "1.0", repo, 123)

    def test_exact_unclassified_jar_with_same_mtime_is_skipped(self):
        with tempfile.TemporaryDirectory() as repo:
            version_dir = os.path.join(repo, "org", "example", "ehcache", "1.0")
            os.makedirs(version_dir)
            unclassified_jar = os.path.join(version_dir, "ehcache-1.0.jar")
            with open(unclassified_jar, "w") as jar_file:
                jar_file.write("unclassified")
            os.utime(unclassified_jar, (123, 123))

            artifact = make_artifact(group="org/example")
            rpm_file = mock.Mock(mtime=123, name="ehcache-1.0-1.noarch.rpm")
            with mock.patch.object(artifact, "get_binary", return_value=rpm_file), mock.patch.object(
                artifact, "fetch_binary"
            ) as fetch_binary, mock.patch.object(artifact, "deploy") as deploy:
                artifact.process(repo, "/tmp", False)

            fetch_binary.assert_not_called()
            deploy.assert_not_called()

    def test_classified_jar_does_not_skip_unclassified_artifact(self):
        with tempfile.TemporaryDirectory() as repo:
            version_dir = os.path.join(repo, "org", "example", "ehcache", "1.0")
            os.makedirs(version_dir)
            classified_jar = os.path.join(version_dir, "ehcache-1.0-jakarta.jar")
            with open(classified_jar, "w") as jar_file:
                jar_file.write("classified")
            os.utime(classified_jar, (123, 123))

            artifact = make_artifact(group="org/example")
            rpm_file = mock.Mock(mtime=123, name="ehcache-1.0-1.noarch.rpm")
            with mock.patch.object(artifact, "get_binary", return_value=rpm_file), mock.patch.object(
                artifact, "fetch_binary", return_value="/tmp/ehcache-1.0-1.noarch.rpm"
            ) as fetch_binary, mock.patch.object(
                artifact, "extract", return_value=("/tmp/ehcache.jar", "org.example", "1.0")
            ), mock.patch.object(artifact, "deploy") as deploy:
                artifact.process(repo, "/tmp", False)

            fetch_binary.assert_called_once_with(rpm_file, "/tmp")
            deploy.assert_called_once_with("/tmp/ehcache.jar", "org.example", "1.0", repo, 123)


if __name__ == "__main__":
    unittest.main()
