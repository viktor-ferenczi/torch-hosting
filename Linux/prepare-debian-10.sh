#!/bin/bash
set -xeuo pipefail

export TERM=xterm

echo "Setup of Space Engineers Torch Server on first boot of Debian 10 server"
echo

ME=$(whoami)
if ! [[ "$ME" == "root" ]]; then
    echo "Server initialization must be run as root"
    exit 1
fi

ORIGINAL_WORKING_DIR=$(pwd)

cd /root

echo "Preparing to run dedicated server"

function withRetry() {
    for RETRY in {1..30}; do
        if "$@"; then
            return 0
        fi
        echo "Retry $RETRY"
        sleep 2
    done
    echo "Failed after retries: $*"
    exit 1
}

if [[ -z $(grep non-free </etc/apt/sources.list | egrep -v '^#') ]]; then
    if [[ $ORIGINAL_WORKING_DIR == "/" ]]; then
      echo "Waiting for server initialization to complete"
      sleep 70
    fi
    withRetry apt-get -y update
    echo
    echo "Enabling non-free and contrib repositories"
    echo
    sed 's@deb http://deb.debian.org/debian/ buster main@deb http://deb.debian.org/debian/ buster main non-free contrib@' </etc/apt/sources.list >/etc/apt/sources.list.new
    mv /etc/apt/sources.list /etc/apt/sources.list.bak
    mv /etc/apt/sources.list.new /etc/apt/sources.list
    sleep 5
fi

echo "Etc/UTC" >/etc/timezone
dpkg-reconfigure -f noninteractive tzdata

dpkg --add-architecture i386

withRetry apt-get -y update
withRetry apt-get -y upgrade

if [[ $(ulimit -n) -lt 65536 ]]; then
    echo
    echo "Increasing file descriptor limits"
    echo "
root soft nofile 65536
root hard nofile 65536
* soft nofile 65536
* hard nofile 65536
" >/etc/security/limits.d/99-nofile-65536.conf
fi

if [[ $(sysctl -n net.core.somaxconn) -lt 1024 ]]; then
    echo
    echo "Increasing network buffers"
    echo "
net.core.somaxconn = 1024
net.core.netdev_max_backlog = 5000
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_wmem = 4096 12582912 16777216
net.ipv4.tcp_rmem = 4096 12582912 16777216
net.ipv4.tcp_max_syn_backlog = 8096
net.ipv4.tcp_slow_start_after_idle = 0
net.ipv4.tcp_tw_reuse = 1
net.ipv4.ip_local_port_range = 32768 65535
" >/etc/sysctl.d/99-larger-buffers-more-connections.conf
    sysctl -p
fi

if grep -q GenuineIntel </proc/cpuinfo; then
    echo
    echo "Intel CPU detected: Disabling Meltdown/Spectre protection for performance"
    echo
    sed -i /etc/default/grub -e 's@GRUB_CMDLINE_LINUX_DEFAULT="quiet"@GRUB_CMDLINE_LINUX_DEFAULT="quiet nopti nospectre_v1 nospectre_v2 nospec_store_bypass_disable intel_pstate=disable"@'
    sed -i /etc/default/grub -e 's@GRUB_CMDLINE_LINUX_DEFAULT="vultrquiet"@GRUB_CMDLINE_LINUX_DEFAULT="vultrquiet nopti nospectre_v1 nospectre_v2 nospec_store_bypass_disable intel_pstate=disable"@'
    update-grub
fi

if ! [[ -f ~/.ssh/id_rsa ]]; then
    echo
    echo "Creating SSH key for root"
    echo
    /usr/bin/ssh-keygen -q -t rsa -N "" -f ~/.ssh/id_rsa
fi

if ! [[ -e /usr/bin/gpg-agent ]] || ! [[ -e /usr/games/steamcmd ]] || ! [[ -e /usr/bin/xvfb-run ]] || ! [[ -e /usr/sbin/ufw ]]; then
    echo
    echo "Installing Debian package dependencies"
    echo
    echo 'debconf steam/question select I AGREE' | debconf-set-selections
    echo 'debconf steam/license note' | debconf-set-selections
    echo 'debconf steam/purge note' | debconf-set-selections
    withRetry apt-get -y install gnupg2 steamcmd xauth xvfb psmisc mc rsync ntp ufw cpufrequtils python3 python3-psutil python3-argcomplete python3-defusedxml python3-filelock
fi

if ! [[ -e /etc/bash_completion.d/python-argcomplete.sh ]]; then
    mkdir -p /etc/bash_completion.d
    /usr/bin/activate-global-python-argcomplete3
fi

if grep -q ondemand </etc/default/cpufrequtils; then
    sed -i /etc/default/cpufrequtils -e 's@GOVERNOR="ondemand"@GOVERNOR="performance"@'
fi

if [[ $(ufw status) == "Status: inactive" ]]; then
    echo
    echo "Configuring firewall"
    echo
    ufw allow ssh
    ufw allow 27000:27999/udp
    ufw --force enable
fi

export APT_KEY_DONT_WARN_ON_DANGEROUS_USAGE=1
if ! (apt-key list | grep -q winehq.org) || ! [[ -e /etc/apt/sources.list.d/winehq.list ]]; then
    echo
    echo "Adding Wine HQ repository"
    echo
    wget -qO - https://dl.winehq.org/wine-builds/winehq.key | apt-key add -
    echo 'deb https://dl.winehq.org/wine-builds/debian/ buster main' >/etc/apt/sources.list.d/winehq.list
    withRetry apt-get -y update
fi

if ! [[ -e /usr/bin/wine ]] || ! [[ -e /usr/bin/winetricks ]]; then
    echo
    echo "Installing Wine and Winetricks"
    echo
    withRetry apt -y install wine winetricks
fi

echo "Signal successful initialization"
touch /root/initialized

echo "Done configuring the system for running Torch."
echo
echo "Please reboot to activate higher resource limits."
echo
echo "After rebooting run prepare-user.sh to create user(s) running Torch."
