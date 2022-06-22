Dependencies
============

This tool runs only on Python 3... all the listed dependencies need to be installed for it.

* PyYAML
* rpm
* cpio

Configuration file
==================

Here is a sample configuration file:

```yaml
url: https://download.opensuse.org/repositories
group: suse
repositories:
  Leap:
    project: openSUSE:Leap:15.4
    repository: standard
  Uyuni:
    project: systemsmanagement:Uyuni:Master
    repository: openSUSE_Leap_15.4
  Leap_sle:
    url: https://download.opensuse.org/update/leap/15.4/sle
artifacts:
  - artifact: salt-netapi-client
    repository: Uyuni
  - artifact: asm
    package: asm3
    jar: asm3-all
    repository: Leap
  - artifact: google-gson
    package: jakarta-commons-digester
    jar: gson.jar
    group: sle
    repository: Leap_sle
```

The `url` property is optional and defaults to `https://download.opensuse.org/repositories`, but can be used to get packages from another download site.
The `url` is used together with the `project` and `repository` values for each repository to construct the full repository URL.

The `repositories` key contains a dictionary of repository definitions.
The name of those repositories is used in the artifacts.
A repository can either be specified by its project/repository name or a custom `url` parameter that must be a full URL pointing to the repository.
If both are provided, the custom `url` is used.

The `artifacts` list describes all the artifacts to create in the maven repository.
The properties of each artifact help locating the RPM and jar files in OBS. The following properties are mandatory:

* `artifact`: the name of the artifact in the maven repository
* `repository`: one of the item defined in `repositories`, tells where to look for the rpm

Since there is no silver bullet to find the RPM or the JAR file in it, there are some additional optional properties to provide hints:

* `package`: the name of the package in OBS. Note that this is different from the RPM name. By default, the artifact name is used and the `demo`, `test`, `manual`, `examples` and `javadoc` rpms are discarded. If the pattern includes the version match, terminate it with `-` to avoid the `-[0-9]` pattern to be appended.
* `arch`: defaults to `noarch`, but this may need to be overriden in some cases.
* `rpm`: a regular expression to match the file name of the RPM **deprecated**
* `jar`: a regular expression to match the non symlinked jar base name.

As a maven repository needs a group ID for each artifact, this can be configured at several levels.
Either at the root of the YAML structure in a `group` attribute or overridden by a `group` attribute in each artifact definition.
`suse` is the default group if nothing is configured.
