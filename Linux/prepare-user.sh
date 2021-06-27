#!/bin/bash

USER_NAME=$1
TORCH_BUILD_NUMBER=$2

# NOTE: The script grants SSH access without password with SSH public key. Please change it to yours:
SSH_PUBLIC_KEY="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCxKVUzrffoLj8PuZgEATGgUVRgAxCy6aMW6UmPOjpv86tMk9GHtR7r5VEvYaihBBP21p1VdCeuv3T+8/fJbxVA+4MjvFGfMiWcK77ALo90zTK6hw4BHGZm8PYaKYZZ7T96gezADXkYQ0kK3IOrgEYT3vhPoXv2c3GCpKwlxD1mbf6eZWaNu1UDlhMcIuOUbXYjghQdnCVc1opRdEnoD/1BfkO0viCHD87SXvgZyWgPjFdlHsr0CK7Rq9PImwg5ZoNgOt0l3YYENN+QaQD6pqIZhkHUDSiMdcef6xT+Jc1i0+pGTUFNtVP9EHsShGiimsgWfCavwdVjMUeZ2xzsSU4NW22LeyX+D3cW4M2QCe9pSSV5V6J80wfT9Y9ccDQ+gupNgiOXeyFLdFfsplK4Ju1FUWI6P5qE7LG2dbo26mYtQ35nbVAMKkozFE/BR8IgEkd1+Nyi9pj7vlD3hD8FyeDpnAMLKRqPDjilBEaEPK+KVRyXuZoKhitp0xzpTP7J9n3nbu3+JY3jMUL7lLh5N3g34FqZnsDrfM0XaBdhTDi+441cU+4IlHFDFP9uF+NOZJpnu4rsEr9D2C+Qauw8B8p5hReCcwTpqPTCOu+SeSonBAHuNCXOiiBbt3deSJ4MufI6VcU8cJP9oh46mD04bQfkUlXXcmz20l4pE3SSWJ+YKQ== viktor@ferenczi.eu"

set -euo pipefail

if [[ "$USER_NAME" == "" ]] || [[ "$TORCH_BUILD_NUMBER" == "" ]]; then
    echo "Usage: $0 USERNAME TORCH_BUILD_NUMBER"
    echo "Example: $0 ds 144"
    exit 1
fi

export TERM=xterm

echo "Setting up user $USER_NAME for running Torch"
echo

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

ME=$(whoami)
if ! [[ "$ME" == "root" ]]; then
    echo "This script must be run as root"
    exit 1
fi

if ! [[ -f /root/initialized ]]; then
    echo "Server has not been prepared"
    exit 1
fi

cd /root

USER_HOME="/home/$USER_NAME"
RUN_AS_USER="sudo -u $USER_NAME -i --preserve-env=TERM,WINEPREFIX"

if ! [[ -d ${USER_HOME} ]]; then
    echo
    echo "Creating user $USER_NAME"
    echo
    useradd -K UMASK=027 -s /bin/bash -m $USER_NAME
    if ! [[ -f "${USER_HOME}/.ssh/id_rsa" ]]; then
        echo "/usr/bin/ssh-keygen -q -t rsa -N \"\" -f ${USER_HOME}/.ssh/id_rsa" | $RUN_AS_USER
    fi
    echo "$SSH_PUBLIC_KEY" >>${USER_HOME}/.ssh/authorized_keys
    chown $USER_NAME:$USER_NAME ${USER_HOME}/.ssh/authorized_keys
fi

echo
echo "Preparing Wine template"
echo
TORCH_URL="https://build.torchapi.net/job/Torch/job/Torch/job/master/${TORCH_BUILD_NUMBER}/artifact/bin/torch-server.zip"
TORCH_FILENAME="torch-server.${TORCH_BUILD_NUMBER}.zip"
if ! [ -f ${USER_HOME}/${TORCH_FILENAME} ]; then
    withRetry $RUN_AS_USER wget -qO ${USER_HOME}/${TORCH_FILENAME} $TORCH_URL
fi

export WINEDEBUG=fixme-all
export WINEPREFIX=${USER_HOME}/.wine00

# See https://github.com/Winetricks/winetricks/issues/934
unset DISPLAY

if ! [[ -d "$WINEPREFIX" ]]; then
    echo
    echo "Installing Windows dependencies"
    echo
    WINETRICKS="$RUN_AS_USER xvfb-run -a -n $$ winetricks --unattended --keep_isos --country=us arch=64"
    $WINETRICKS sound=disabled
    $WINETRICKS dotnet472
    $WINETRICKS vcrun2013
    $WINETRICKS vcrun2017
fi

SERVER_DIR=${USER_HOME}/ds00
if ! [[ -d $SERVER_DIR ]]; then

    echo
    echo "Installing Torch Server"
    echo

    $RUN_AS_USER mkdir $SERVER_DIR

    echo "cd $SERVER_DIR && unzip -o ${USER_HOME}/${TORCH_FILENAME}" | $RUN_AS_USER

    RESULT=0
    (echo "cd $SERVER_DIR && wine Torch.Server.exe" | $RUN_AS_USER) || RESULT=$?

    # Error code 82 is returned when Torch.Server.exe fails to open the
    # configuration window at the end of installation. It is the expected behavior.
    # Returning a zero result code would mean no initialization.
    if [[ $RESULT -ne 82 ]]; then
        echo "Torch Server initialization returned unexpected result code: $RESULT"
        exit 1
    fi

    # Do not try to execute Torch.Server.exe from ds00, it will not work!
    # The ds00 deployment is a template, which needs to be cloned first.
fi

echo "Precompiling .NET assemblies"
$RUN_AS_USER wine C:/Windows/Microsoft.NET/Framework/v4.0.30319/ngen.exe executeQueuedItems || true
$RUN_AS_USER wine C:/Windows/Microsoft.NET/Framework/v4.0.30319/ngen.exe executeQueuedItems
$RUN_AS_USER wine C:/Windows/Microsoft.NET/Framework64/v4.0.30319/ngen.exe executeQueuedItems || true
$RUN_AS_USER wine C:/Windows/Microsoft.NET/Framework64/v4.0.30319/ngen.exe executeQueuedItems
$RUN_AS_USER wine C:/Windows/System32/schtasks.exe /run /Tn "MicrosoftWindows.NET Framework.NET Framework NGEN v4.0.30319 64"
$RUN_AS_USER wine C:/Windows/System32/schtasks.exe /run /Tn "MicrosoftWindows.NET Framework.NET Framework NGEN v4.0.30319 32"

echo "Reset the sockets library"
# It may prevent networking issues, but it is not proven yet.
$RUN_AS_USER wine netsh winsock reset

echo "Creating folders"
$RUN_AS_USER mkdir -p ${USER_HOME}/archive
$RUN_AS_USER mkdir -p ${USER_HOME}/plugins
$RUN_AS_USER mkdir -p ${USER_HOME}/logs
$RUN_AS_USER mkdir -p ${USER_HOME}/.cache/blueprint_downloader/requests
$RUN_AS_USER mkdir -p ${USER_HOME}/.cache/blueprint_downloader/responses

echo "Linking cache"
if ! [ -e "${WINEPREFIX}/drive_c/users/${USER_NAME}/.cache" ]; then
    $RUN_AS_USER ln -s  ${USER_HOME}/.cache ${WINEPREFIX}/drive_c/users/${USER_NAME}/.cache
fi

echo "Signal successful initialization"
$RUN_AS_USER touch initialized

echo "Done."
echo ""
echo "Use server.py to create, destroy, start or stop Torch based dedicated servers"
