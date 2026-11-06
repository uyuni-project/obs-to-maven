FROM registry.opensuse.org/opensuse/leap:16.0

# Installing all packages
RUN zypper refresh && \
        zypper -n install gawk bash-completion curl expect git man openssh sudo tar vim wget ripgrep \
                          python3 python313-Jinja2 python313-PyYAML rpm cpio && \
        zypper clean -a

# Creating regular user
RUN useradd --create-home --shell /bin/bash obs-maven
RUN echo "obs-maven ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

USER obs-maven
