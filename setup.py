import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="obs-to-maven",
    version="1.1.2",
    author="Cedric Bosdonnat",
    author_email="cedric.bosdonnat@suse.com",
    description="Tool extracting jars from RPMs in OpenBuildService to a maven repo",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/uyuni-project/obs-to-maven",
    packages=["obs_maven"],
    entry_points={"console_scripts": ["obs-to-maven = obs_maven.core:main"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    install_requires=["PyYAML"],
)
