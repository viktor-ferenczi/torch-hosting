#!/usr/bin/python3
# PYTHON_ARGCOMPLETE_OK
# -*- coding: ascii -*-
r"""

Requires Python 3.7

Requires Python packages:
- psutil

Clones a reference Wine dedicated server setup,
configures and starts a Torch server.

.wineNN:

Delete contents of folders in reference:
".wine??/drive_c/users/ds/Temp/"
".wine??/drive_c/users/ds/Local Settings/Temporary Internet Files/Content.IE5/"

Delete file from reference:
.wine??/drive_c/windows/dd_SetupUtility.txt
.wine??/drive_c/windows/Microsoft.NET/Framework/v4.0.30319/*.log
.wine??/drive_c/windows/Microsoft.NET/Framework64/v4.0.30319/*.log

Generate new GUIDs:

.wine??/system.reg
"MachineGuid"="72d72157-dd3f-40c9-b462-c6a455a30bb9"
"MachineId"="{1392A2EE-5B9E-4B71-A658-1B7163112B20}"

.wine??/user.reg
"UserId"="{64B8BFE8-E625-4C5E-8729-7F54773CF4FE}"

Generate new winserver ID:

.wine??/wineserver
wine-FV7fsW

File names to keep consistent with registry (don't touch):
.wine??/drive_c/windows/Installer/*.msi

Modify the "My *" symlinks to point to the target dsNN folder:
".wine??/drive_c/users/ds/My *" => ~/dsNN

dsNN:

Delete file from reference:
ds??/steamcmd/steamcmd.exe.1.delete

Delete all:
*.sbcB5
*.sbsB5
*.log

Update:
Torch.cfg
<InstancePath>Z:\home\ds\ds17\Instance</InstancePath>

"""
import argparse
import hashlib
import subprocess
import traceback
import argcomplete
import datetime
import json
import os
import random
import re
import shutil
import signal
import socket
import string
import sys
import uuid
import zipfile
from time import time, sleep
from typing import Optional, List

import filelock
import psutil

ENVIRONMENT = os.getenv('ENVIRONMENT', 'dev')
assert ENVIRONMENT in ('dev', 'test', 'prod')

USER_NAME = os.environ['USER']

HOME_DIR = os.path.expanduser('~')
WORLD_ZIP_DIR = os.path.expanduser('~/')
PLUGINS_DIR = os.path.expanduser('~/plugins')
ARCHIVE_DIR = os.path.expanduser('~/archive')
TEMPLATE_WINE_DIR = os.path.expanduser('~/.wine00')
TEMPLATE_SERVER_DIR = os.path.expanduser('~/ds00')
ASTEROIDS_DIR = os.path.expanduser('~/asteroids')
CACHE_DIR_TEMPLATE = '~/.cache/ds%02d'
BINARY_CACHE_DIR = os.path.expanduser('~/.cache/binary_cache')

SHA1SUM = '/usr/bin/sha1sum'

CLONE_SKIP_EXTENSIONS = set('log cache hash sbcB5 sbsB5'.split())

CLONE_SAFE_TO_LINK_EXTENSIONS = set((
                                        'bat cmd exe dll sys drv bin ocx manifest config pdb msi zip mui hlsl hlsli inl asar ' +
                                        'bmp png jpg gif ico html css js mwm pak aspx resx dds vs xml txt scf sbl sbx vsc gsc ' +
                                        'hkt mwl vx2 hash nlp h rtf pdf old sql nls vxd xsd master mof tlb rsp man msu cs mod ' +
                                        'ascx brain').split())

RX_REGISTRY_STRING = re.compile(r'^"(\w+)"=".*?"$')
RX_GUID_ELEMENT = re.compile(r'<Guid>(.*?)</Guid>')
RX_ASTEROID = re.compile(r'<StorageName>(.*?Asteroid.*?)</StorageName>')

FREE = 'FREE'
STOPPED = 'STOPPED'
STARTING = 'STARTING'
SERVING = 'SERVING'
FAILED = 'FAILED'

CANARY_TIMEOUT = 3 * 60.0
MAX_STARTUP_TIME = 8 * 60.0
WAIT_AFTER_KEEPALIVE_ACTION = 30.0

LOW_PRIORITY = 10
NORMAL_PRIORITY = 0
HIGH_PRIORITY = -10
PRIORITIES = dict(
    low=LOW_PRIORITY,
    normal=NORMAL_PRIORITY,
    high=HIGH_PRIORITY,
)


def guid() -> str:
    return str(uuid.uuid4())


def timestamp() -> str:
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def timestamp_for_filename() -> str:
    return datetime.datetime.now().strftime('%Y%m%d-%H%M%S')


def get_file_lock_path(number: int) -> str:
    return os.path.expanduser(f'~/.local/server-{number}.lock')


def change_registry(path, **kws):
    lines = []
    with open(path, 'rt') as f:
        for line in f:

            m = RX_REGISTRY_STRING.match(line.rstrip())

            if m is None:
                lines.append(line)
                continue

            name = m.group(1)
            value = kws.get(name)

            if value is None:
                lines.append(line)
                continue

            line = '"%s"="%s"\n' % (name, value)
            lines.append(line)

    with open(path, 'wt') as f:
        f.writelines(lines)


def relink_my_folders(dst_ds, dst_wine):
    for link_name in ('My Documents', 'My Music', 'My Pictures', 'My Videos'):
        link_path = os.path.join(dst_wine, 'drive_c', 'users', USER_NAME, link_name)
        if os.path.islink(link_path):
            os.unlink(link_path)
        os.symlink(dst_ds, link_path)


def change_wine_server_id(wine_dir_path):
    path = os.path.join(wine_dir_path, 'wineserver')

    if os.path.exists(path):
        os.remove(path)

    with open(path, 'wt') as f:
        characters = string.ascii_letters + string.digits
        server_id = ''.join(random.choice(characters) for _ in range(6))
        f.write('wine-%s' % server_id)

    os.chmod(path, 0o400)


def cache_dir(number: int):
    return os.path.expanduser(CACHE_DIR_TEMPLATE % number)


def content_cache_dir(number: int):
    return os.path.join(cache_dir(number), 'content')


def edit(editor, path: str):
    with open(path, 'rt', encoding='utf8') as f:
        original = f.read()

    edited = editor(original)

    with open(path, 'wt', encoding='utf8') as f:
        f.write(edited)


def unzip(target_dir, zip_path, *, remove_top_folder=True):
    """Unzip a ZIP archive

    Automatically removes the top level folder if any.

    """
    with zipfile.ZipFile(zip_path, 'r') as zf:

        prefix = ''
        if remove_top_folder:
            for zi in zf.filelist:
                dir_of_file = os.path.dirname(zi.filename)
                if not prefix:
                    prefix = dir_of_file
                elif dir_of_file.startswith(prefix):
                    continue
                elif prefix.startswith(dir_of_file):
                    prefix = dir_of_file
                else:
                    prefix = ''
                    break

        for zi in zf.filelist:
            relative_path = zi.filename[len(prefix):].lstrip('/')
            if not relative_path:
                continue

            target_path = os.path.join(target_dir, relative_path)

            target_path_dir = os.path.dirname(target_path)
            os.makedirs(target_path_dir, exist_ok=True)

            if target_path.rstrip('/') == target_path_dir:
                continue

            with zf.open(zi) as sf:
                with open(target_path, 'wb') as tf:
                    shutil.copyfileobj(sf, tf)


def clone(source, target):
    if os.path.isdir(target):
        shutil.rmtree(target)

    for src_dir, dirnames, filenames in os.walk(source):

        dst_dir = os.path.join(target, src_dir[len(source) + 1:])
        os.makedirs(dst_dir, 0o755)

        for dirname in dirnames:

            src_path = os.path.join(src_dir, dirname)
            dst_path = os.path.join(dst_dir, dirname)

            if os.path.islink(src_path):
                original_target = os.readlink(src_path)
                os.symlink(original_target, dst_path, True)

        for filename in filenames:

            src_path = os.path.join(src_dir, filename)
            dst_path = os.path.join(dst_dir, filename)

            extension = os.path.splitext(filename)[1][1:].lower()

            if extension in CLONE_SKIP_EXTENSIONS:
                continue

            if os.path.islink(src_path):
                original_target = os.readlink(src_path)
                os.symlink(original_target, dst_path)
                continue

            if extension in CLONE_SAFE_TO_LINK_EXTENSIONS:
                os.link(src_path, dst_path)
                continue

            shutil.copy(src_path, dst_path)


def copy_tree(src, dst):
    for srcdir, dirnames, filenames in os.walk(src):
        reldir = srcdir[len(src) + 1:]
        dstdir = os.path.join(dst, reldir) if reldir else dst
        os.makedirs(dstdir, exist_ok=True)
        for filename in filenames:
            srcpath = os.path.join(srcdir, filename)
            dstpath = os.path.join(dstdir, filename)
            shutil.copy2(srcpath, dstpath)


def cleanup_archive(archive_ds_dir: str):
    for fn in os.listdir(archive_ds_dir):
        if fn in ('Instance', 'Logs', 'Torch.cfg', 'start', 'start.log', 'zip_path'):
            continue
        fp = os.path.join(archive_ds_dir, fn)
        if os.path.isdir(fp):
            shutil.rmtree(fp)
        else:
            os.remove(fp)


class Server:
    ip_cache: List[str] = []

    def __init__(self, number: int):
        assert 0 <= number < 100
        self.number = number
        self.world = {}

    @property
    def ip(self):
        if self.ip_cache:
            return self.ip_cache[0]
        ip = socket.gethostbyname(socket.gethostname())
        self.ip_cache.append(ip)
        return ip

    @property
    def port(self) -> int:
        return 27000 + self.number

    @property
    def wine_dir(self) -> str:
        return os.path.expanduser('~/.wine%02d' % self.number)

    @property
    def server_dir(self) -> str:
        return os.path.expanduser('~/ds%02d' % self.number)

    @property
    def logs_dir(self) -> str:
        return os.path.join(self.server_dir, 'Logs')

    @property
    def instance_dir(self) -> str:
        return os.path.join(self.server_dir, 'Instance')

    @property
    def world_dir(self) -> str:
        return os.path.join(self.instance_dir, 'Saves', 'World')

    @property
    def canary_path(self) -> str:
        return os.path.join(self.instance_dir, 'canary')

    @property
    def plugins_dir(self) -> str:
        return os.path.join(self.server_dir, 'Plugins')

    @property
    def world_json_path(self) -> str:
        return os.path.join(self.server_dir, 'world.json')

    @property
    def plugins(self):
        plugins = self.world['plugins']
        if 'Hosting' not in plugins:
            plugins.insert(0, 'Hosting')
        return plugins

    @property
    def zip_path(self) -> str:
        try:
            with open(os.path.join(self.server_dir, 'zip_path'), 'rt') as f:
                return f.read().strip()
        except (IOError, OSError):
            return ''

    @property
    def world_checksum(self):
        checksum_path = os.path.join(self.world_dir, 'checksum.txt')
        if not os.path.exists(checksum_path):
            return None
        with open(checksum_path, 'rt') as f:
            return f.read().strip()

    @property
    def intent(self) -> str:
        try:
            with open(os.path.join(self.server_dir, 'intent'), 'rt') as f:
                return f.read().strip()
        except (IOError, OSError):
            return ''

    @property
    def exists(self) -> bool:
        return os.path.isdir(self.server_dir)

    @property
    def pid(self) -> Optional[int]:
        instance_dir = self.instance_dir
        for process in psutil.process_iter(attrs=['pid', 'cmdline']):
            try:
                cmdline = process.cmdline()
            except psutil.NoSuchProcess:
                continue
            if cmdline and 'Torch.Server.exe' in cmdline[0] and '-instancepath' in cmdline and instance_dir in cmdline:
                return process.pid
        return None

    @property
    def file_lock_path(self):
        return get_file_lock_path(self.number)

    @property
    def keepalive_log_path(self):
        return os.path.expanduser(f'~/logs/keepalive-{self.number}.{datetime.date.today().isoformat()}.log')

    @property
    def keepalive_pid_path(self):
        return os.path.expanduser(f'~/.local/keepalive-{self.number}.pid')

    @property
    def keepalive_pid(self) -> Optional[int]:
        try:
            with open(self.keepalive_pid_path, 'rt') as f:
                return int(f.read())
        except (IOError, OSError, ValueError):
            return None

    def write_keepalive_pid(self):
        with open(self.keepalive_pid_path, 'wt') as f:
            f.write(str(os.getpid()))

    def remove_keepalive_pid(self):
        try:
            os.remove(self.keepalive_pid_path)
        except (IOError, OSError):
            pass

    @property
    def running(self) -> bool:
        return self.pid is not None

    @property
    def ready_path(self) -> str:
        return os.path.join(self.server_dir, 'ready')

    @property
    def keen_log_path(self) -> Optional[str]:
        logs_dir = self.logs_dir
        if not os.path.isdir(logs_dir):
            return None
        for fn in sorted(os.listdir(self.logs_dir), reverse=True):
            if fn.startswith('Keen-') and fn.endswith('.log'):
                return os.path.join(logs_dir, fn)
        return None

    @property
    def torch_log_path(self) -> Optional[str]:
        logs_dir = self.logs_dir
        if not os.path.isdir(logs_dir):
            return None
        for fn in sorted(os.listdir(self.logs_dir), reverse=True):
            if fn.startswith('Torch-') and fn.endswith('.log'):
                return os.path.join(logs_dir, fn)
        return None

    @property
    def ready(self) -> bool:
        ready_path = self.ready_path
        if os.path.exists(ready_path):
            return True

        keen_log_path = self.keen_log_path
        if keen_log_path is None:
            return False

        with open(keen_log_path, 'rt') as keen_log:
            for line in keen_log:
                if 'Keen: Game ready' in line:
                    break
            else:
                return False

        with open(ready_path, 'wt') as f:
            f.write(timestamp())

        return True

    @property
    def has_failed_startup(self) -> bool:
        keen_log_path = self.keen_log_path
        if keen_log_path is None:
            return True

        with open(keen_log_path, 'rt') as keen_log:
            for line in keen_log:
                if 'Keen: Game ready' in line:
                    return False
                if 'Error: No IP assigned' in line:
                    return True
                if 'Exception while loading world' in line:
                    return True
                if 'An error occurred while loading the world' in line:
                    return True
                if 'Could not obtain all workshop item details' in line:
                    return True
                if 'Logging off Steam' in line:
                    return True
                if 'Shutting down server' in line:
                    return True
                if 'Keen: Exiting' in line:
                    return True
                # if 'Keen: System.NullReferenceException: Object reference not set to an instance of an object.' in line:
                #     return True

        return False

    @property
    def has_recent_canary(self) -> bool:
        path = self.canary_path
        if not os.path.exists(path):
            return False
        canary_age = time() - os.stat(path).st_mtime
        return canary_age < CANARY_TIMEOUT

    @property
    def process(self) -> Optional[psutil.Process]:
        pid = self.pid
        if pid is None:
            return None

        return psutil.Process(pid)

    @property
    def serving(self) -> bool:
        process = self.process
        if process is None:
            return True

        for c in process.connections('udp4'):
            if c.laddr.port == self.port and getattr(self, 'raddr', ()) == ():
                return True

        return False

    @property
    def lifetime(self) -> float:
        process = self.process
        if process is None:
            return 1e9
        return time() - process.create_time()

    @property
    def status(self):
        if not self.exists:
            return FREE

        if self.intent != SERVING:
            return STOPPED

        if self.ready:
            if self.running and self.serving and self.has_recent_canary:
                self.cache_binary_world_file()
                return SERVING
            return FAILED

        if not self.running:
            return FAILED

        if self.lifetime >= MAX_STARTUP_TIME:
            return FAILED

        if self.has_failed_startup:
            return FAILED

        return STARTING

    @property
    def working(self) -> bool:
        return self.status in (STARTING, SERVING)

    @property
    def server_name(self) -> str:
        return self.world['name']

    @property
    def world_name(self) -> str:
        return self.world['name']

    @property
    def max_players(self) -> int:
        return self.world['maxPlayers']

    @property
    def phase(self) -> str:
        try:
            with open(os.path.join(self.instance_dir, 'phase'), 'rt') as f:
                return f.read()
        except (IOError, OSError):
            return ''

    @property
    def priority(self) -> Optional[str]:
        try:
            with open(os.path.join(self.instance_dir, 'priority'), 'rt') as f:
                return f.read().strip()
        except (IOError, OSError):
            return None

    # Commands

    @classmethod
    def command_list(cls) -> int:
        for number in range(1, 100):
            server = cls(number)
            status = server.status
            if status != FREE:
                print(f'{number:02d} {status} {server.zip_path}')
        return 0

    def command_create(self, world_zip_path: str, suffix: str) -> int:
        if self.exists:
            if self.running:
                raise ValueError(f'Server already exists and running with number {self.number}, stop and archive it before recreating')
            raise ValueError(f'Server already exists with number {self.number}, archive it before recreating')

        if os.path.isdir(self.wine_dir):
            shutil.rmtree(self.wine_dir)

        self.clone()
        self.extract_world(world_zip_path)
        self.load_world_json()
        self.deploy_asteroids()
        self.extract_plugins()
        self.configure_torch()
        self.configure_dedicated_server(suffix)
        self.configure_plugin()
        self.write_start_script()
        self.link_mod_cache()
        self.write_zip_path(world_zip_path)
        self.write_server_name_suffix(suffix)
        self.checksum_world()
        self.attempt_using_cached_binary()
        return 0

    def command_archive(self, *, initiator='cmdline', full: bool = False) -> int:
        if self.running:
            raise ValueError(f'Server is still running with number {self.number}, stop it before archiving')

        archive_dir = os.path.join(ARCHIVE_DIR, f'ds{self.number:02d}')
        os.makedirs(archive_dir, exist_ok=True)

        mode = 'full' if full else 'world_logs'
        archive_ds_dir = os.path.join(archive_dir, f'{timestamp_for_filename()}_{initiator}_{mode}')

        shutil.move(self.server_dir, archive_ds_dir)

        try:
            shutil.rmtree(self.wine_dir)
        except OSError:
            sleep(1)
            shutil.rmtree(self.wine_dir)

        if not full:
            cleanup_archive(archive_ds_dir)

        return 0

    def command_destroy(self) -> int:
        if not self.exists:
            return 0

        self.command_kill()
        for dir_path in (self.server_dir, self.wine_dir):
            try:
                shutil.rmtree(dir_path)
            except (IOError, OSError):
                pass
        return 0

    def command_start(self, update: bool = False) -> int:
        self.write_intent(SERVING)
        os.chdir(self.server_dir)
        options = 'update' if update else ''
        return os.system(f'nohup xvfb-run -a -n {self.number} bash start {options} >start.log 2>&1 &')

    def command_stop(self) -> int:
        if not self.exists:
            return 0

        self.write_intent(STOPPED)
        pid = self.pid
        if not pid:
            return 0

        os.kill(pid, signal.SIGTERM)
        return 0

    def command_kill(self) -> int:
        if not self.exists:
            return 0

        self.write_intent(STOPPED)
        for _ in range(50):
            pid = self.pid
            if not pid:
                break
            os.kill(pid, signal.SIGKILL)
            sleep(0.1)
        else:
            print(f'{timestamp()} ERROR: Failed to kill Torch server processes with -instance_dir {self.instance_dir}', file=sys.stderr)
            return 1

        return 0

    def command_pid(self) -> int:
        pid = self.pid
        if pid is None:
            print(pid)
        return 0

    def command_check(self) -> int:
        return 0 if self.working else 1

    def command_status(self) -> int:
        print(self.status)
        return 0

    def command_keepalive(self, *, stop: bool, period: int) -> int:
        self.stop_keepalive()
        if stop:
            return 0

        self.write_keepalive_pid()
        self.monitor(period)
        return 0

    def stop_keepalive(self):
        pid = self.keepalive_pid
        if pid is None:
            return

        try:
            os.kill(pid, signal.SIGKILL)
        except (OSError, IOError):
            pass

        self.remove_keepalive_pid()

    def monitor(self, period: float):
        lock_file_path = self.file_lock_path

        while 1:
            with open(self.keepalive_log_path, 'at') as output:
                sys.stdout = output
                sys.stderr = output

                # noinspection PyBroadException
                try:
                    with filelock.FileLock(lock_file_path):
                        self.monitor_once()
                except KeyboardInterrupt:
                    print(f'{timestamp()}: Keepalive terminated (SIGTERM)')
                    break
                except SystemExit:
                    print(f'{timestamp()}: Keepalive finished (SystemExit)')
                    break
                except Exception:
                    print(f'{timestamp()} ERROR: {traceback.format_exc()}', end='')
                finally:
                    output.flush()

                sleep(period)

    def monitor_once(self):
        if self.intent != SERVING:
            return

        if self.working:
            self.set_priority()
            return

        result = self.keepalive_action()
        if result:
            print(f'{timestamp()} ERROR: Keepalive failed to recover server')
            return

        print(f'{timestamp()}: Keepalive recovered server, waiting {WAIT_AFTER_KEEPALIVE_ACTION} seconds')
        sleep(WAIT_AFTER_KEEPALIVE_ACTION)

    def keepalive_action(self):
        print(f'{timestamp()}: Initiating keepalive action, server status: {self.status}')

        if os.path.exists(os.path.join(self.server_dir, 'recreate')):
            result = self.command_recreate(initiator='keepalive')
        else:
            result = self.command_restart()

        return result

    def command_restart(self) -> int:
        print(f'{timestamp()}: Restarting {self.number:02d}')

        self.command_kill()

        result = self.command_start()
        if result:
            return result

        return 0

    # Helpers

    def command_recreate(self, *, initiator='cmdline') -> int:
        print(f'{timestamp()}: Recreating {self.number:02d}')

        self.command_kill()

        zip_path = self.zip_path

        path = os.path.join(self.server_dir, 'server_name_suffix')
        if os.path.isfile(path):
            with open(path, 'rt') as f:
                suffix = f.read().strip()
        else:
            suffix = ''

        print(f'{timestamp()}: Archiving logs and world files of {self.number:02d}')
        self.command_archive(initiator=initiator)

        print(f'{timestamp()}: Recreating {self.number:02d} from {zip_path}')
        self.command_create(zip_path, suffix)

        print(f'{timestamp()}: Starting {self.number:02d}')
        result = self.command_start()
        if result:
            return result

        print(f'{timestamp()}: Recreated and started {self.number:02d}')
        return 0

    def command_upgrade(self) -> int:
        if self.running:
            print('Cannot upgrade, server is running', file=sys.stderr)
            return 1

        copy_tree(TEMPLATE_SERVER_DIR, self.server_dir)
        return 0

    def clone(self):
        clone(TEMPLATE_WINE_DIR, self.wine_dir)

        change_registry(
            os.path.join(self.wine_dir, 'system.reg'),
            MachineGuid=guid(),
            MachineId="{%s}" % guid().upper(),
        )

        change_registry(
            os.path.join(self.wine_dir, 'user.reg'),
            UserId="{%s}" % guid().upper(),
        )

        clone(TEMPLATE_SERVER_DIR, self.server_dir)

        relink_my_folders(self.server_dir, self.wine_dir)

        change_wine_server_id(self.wine_dir)

    def load_world_json(self):
        with open(self.world_json_path, 'rt', encoding='utf8') as f:
            self.world = json.load(f)

    def link_mod_cache(self):
        cache = content_cache_dir(self.number)
        if not os.path.isdir(cache):
            os.makedirs(cache, exist_ok=True)
        if not os.path.isdir(self.instance_dir):
            raise IOError('Missing Instance folder: ' + self.instance_dir)
        link = os.path.join(self.instance_dir, 'content')
        os.symlink(cache, link, target_is_directory=True)

    def write_intent(self, intent):
        with open(os.path.join(self.server_dir, 'intent'), 'wt') as f:
            f.write(intent)

    def write_server_name_suffix(self, suffix):
        with open(os.path.join(self.server_dir, 'server_name_suffix'), 'wt') as f:
            f.write(suffix)

    def checksum_world(self):
        stdout, stderr = subprocess.Popen([SHA1SUM, 'Sandbox.sbc', 'Sandbox_config.sbc', 'SANDBOX_0_0_0_.sbs'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1024, cwd=self.world_dir).communicate()
        assert not stderr, 'sha1sum failed: ' + stderr.decode('utf8')
        sha256 = hashlib.sha256(stdout)
        with open(os.path.join(self.world_dir, 'checksum.txt'), 'wt') as f:
            f.write(sha256.hexdigest())

    def cache_binary_world_file(self):
        checksum = self.world_checksum
        if not checksum:
            return

        sbsb5_cache_path = os.path.join(BINARY_CACHE_DIR, f'{checksum}.sbsB5')
        if os.path.exists(sbsb5_cache_path):
            return

        sbsb5_path = os.path.join(self.world_dir, 'SANDBOX_0_0_0_.sbsB5')
        if not os.path.exists(sbsb5_path):
            return

        os.makedirs(BINARY_CACHE_DIR, exist_ok=True)
        shutil.copy(sbsb5_path, sbsb5_cache_path)

    def attempt_using_cached_binary(self):
        checksum = self.world_checksum
        if not checksum:
            return

        sbsb5_cache_path = os.path.join(BINARY_CACHE_DIR, f'{checksum}.sbsB5')
        if not os.path.exists(sbsb5_cache_path):
            return

        sbsb5_path = os.path.join(self.world_dir, 'SANDBOX_0_0_0_.sbsB5')
        if os.path.exists(sbsb5_path):
            return

        shutil.copy(sbsb5_cache_path, sbsb5_path)

    def write_zip_path(self, world_zip_path):
        with open(os.path.join(self.server_dir, 'zip_path'), 'wt') as f:
            f.write(world_zip_path)

    def write_start_script(self):
        path = os.path.join(self.server_dir, 'start')
        with open(path, 'wt') as f:
            f.write(f'''\
#!/bin/bash

NOUPDATE=""
if [ -z "$1" ]; then
    NOUPDATE="-noupdate"
fi

WINEPREFIX={self.wine_dir} WINEDEBUG=fixme-all wine Torch.Server.exe -nogui $NOUPDATE -ticktimeout 60 -autostart -instancepath {self.server_dir}/Instance -instancename "{self.server_name}"
''')

        os.chmod(path, 0o755)

    def extract_plugins(self):
        for name in self.plugins:
            self.extract_plugin(name)

    def extract_plugin(self, name: str):
        zip_path = os.path.join(PLUGINS_DIR, name + '.zip')
        plugin_dir = os.path.join(self.plugins_dir, name)
        os.mkdir(plugin_dir)
        unzip(plugin_dir, zip_path)

    def configure_plugin(self):
        config = '''<?xml version="1.0" encoding="utf-8"?>
<SpaceBattleConfig 
  xmlns:xsd="http://www.w3.org/2001/XMLSchema" 
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  
  <Environment>%s</Environment>
  <Address>%s:%d</Address>
  
</SpaceBattleConfig>''' % (ENVIRONMENT, self.ip, self.port)

        config_path = os.path.join(self.server_dir, 'Instance/SpaceBattle.cfg')
        with open(config_path, 'wt') as f:
            f.write(config)

    def iter_plugin_guids(self):
        for plugin in os.listdir(self.plugins_dir):
            manifest_path = os.path.join(self.plugins_dir, plugin, 'manifest.xml')
            if not os.path.exists(manifest_path):
                continue
            with open(manifest_path, 'rt') as f:
                for line in f:
                    for m in RX_GUID_ELEMENT.finditer(line):
                        yield m.group(1)
                        break
                    else:
                        continue
                    break
                else:
                    raise ValueError(f'No <Guid> found in {manifest_path}')

    def configure_torch(self):
        config_path = os.path.join(self.server_dir, 'Torch.cfg')

        def replace_instance_path(text):
            text = re.sub(r'<InstancePath>.*?</InstancePath>', r'<InstancePath>C:\\Users\\%s\\My Documents\\Instance</InstancePath>' % USER_NAME, text)
            if '<Plugins></Plugins>' not in text:
                raise ValueError(f'Invalid Torch.cfg template: {config_path}')
            guids = '\n'.join(f'<guid>{g}</guid>' for g in self.iter_plugin_guids())
            text = text.replace('<Plugins></Plugins>', f'<Plugins>\n{guids}\n</Plugins>')
            return text

        edit(replace_instance_path, config_path)

    def configure_dedicated_server(self, server_name_suffix: str) -> None:
        admin_port = 9000 + self.number

        server_name = ('%s %s' % (self.server_name, server_name_suffix)).rstrip()

        def edit_dedicated_server_cfg(text):
            text = re.sub(r'<LoadWorld>.*?</LoadWorld>', r'<LoadWorld>C:/users/%s/My Documents/Instance/Saves/World</LoadWorld>' % USER_NAME, text)
            text = re.sub(r'<IP>.*?</IP>', '<IP>0.0.0.0</IP>', text)
            text = re.sub(r'<ServerPort>\d+</ServerPort>', '<ServerPort>%d</ServerPort>' % self.port, text)
            text = re.sub(r'<RemoteApiPort>\d+</RemoteApiPort>', '<RemoteApiPort>%d</RemoteApiPort>' % admin_port, text)
            text = re.sub(r'<ServerName>.*?</ServerName>', '<ServerName>%s</ServerName>' % server_name, text)
            return text

        config_path = os.path.join(self.server_dir, 'Instance/SpaceEngineers-Dedicated.cfg')
        edit(edit_dedicated_server_cfg, config_path)

    def extract_world(self, world_zip_path: str) -> None:
        unzip(self.server_dir, world_zip_path)
        if not os.path.isfile(self.world_json_path):
            raise IOError('Invalid world archive (missing world.json file): ' + world_zip_path)

    def deploy_asteroids(self):
        world_dir = os.path.join(self.instance_dir, 'Saves', 'World')

        asteroids = []
        sbs_path = os.path.join(world_dir, 'SANDBOX_0_0_0_.sbs')
        with open(sbs_path, 'rt') as f:
            for line in f:
                m = RX_ASTEROID.match(line.strip())
                if m is not None:
                    asteroids.append(m.group(1))

        for storage_name in asteroids:
            filename = storage_name + '.vx2'
            src_path = os.path.join(ASTEROIDS_DIR, filename)
            dst_path = os.path.join(world_dir, filename)
            if not os.path.exists(dst_path):
                shutil.copy(src_path, dst_path)

    def set_priority(self):
        process = self.process
        if process is None:
            return

        priority = self.priority
        if priority is None:
            return

        nice_level = PRIORITIES.get(priority)
        if nice_level is None:
            print(f'{timestamp()} ERROR: Got unknown priority value "{priority}"')
            return

        self.process.nice(nice_level)


def main():
    parser = argparse.ArgumentParser()

    def fail(message):
        print(message, file=sys.stderr)
        print(file=sys.stderr)
        parser.print_usage(sys.stderr)
        sys.exit(1)

    subparsers = parser.add_subparsers(
        title='commands',
        description='server management command',
        help='server management command')

    subparser = subparsers.add_parser('list', description='List servers and their status')
    subparser.set_defaults(command=Server.command_list)

    subparser = subparsers.add_parser('create', description='Creates a Torch server (does not start it)')
    subparser.set_defaults(command=Server.command_create)
    subparser.add_argument('number', type=int, help='Server number 01..99, port number is 27000 + server number')
    subparser.add_argument('world', type=str, help='Path of the archive (ZIP) file to load the world from')
    subparser.add_argument('-s', '--suffix', type=str, default='', help='Suffix to append to the server name')

    subparser = subparsers.add_parser('archive', description='Archives a stopped Torch server (frees up the server number)')
    subparser.set_defaults(command=Server.command_archive)
    subparser.add_argument('number', type=int, help='Server number 01..99')
    subparser.add_argument('-f', '--full', action='store_true', default=False, help='Archives the full dsNN folder, not just the world and the logs')

    subparser = subparsers.add_parser('destroy', description='Kills and deletes a Torch server without archiving')
    subparser.set_defaults(command=Server.command_destroy)
    subparser.add_argument('number', type=int, help='Server number 01..99')

    subparser = subparsers.add_parser('start', description='Starts a Torch server, does nothing if already running')
    subparser.set_defaults(command=Server.command_start)
    subparser.add_argument('number', type=int, help='Server number 01..99')
    subparser.add_argument('-u', '--update', action='store_true', default=False, help='Requests Dedicated Server (game) update on startup')

    subparser = subparsers.add_parser('stop', description='Stops a Torch server, does nothing if not running currently')
    subparser.set_defaults(command=Server.command_stop)
    subparser.add_argument('number', type=int, help='Server number 01..99')

    subparser = subparsers.add_parser('kill', description='Kills a Torch server, does nothing if not running currently')
    subparser.set_defaults(command=Server.command_kill)
    subparser.add_argument('number', type=int, help='Server number 01..99')

    subparser = subparsers.add_parser('pid', description='Prints the PID of the Torch server process if running, nothing otherwise')
    subparser.set_defaults(command=Server.command_pid)
    subparser.add_argument('number', type=int, help='Server number 01..99')

    subparser = subparsers.add_parser('check', description='Checks whether a game server is working (starting on serving requests)')
    subparser.set_defaults(command=Server.command_check)
    subparser.add_argument('number', type=int, help='Server number 01..99')

    subparser = subparsers.add_parser('status', description='Prints the status of a game server or nothing if it does not exist')
    subparser.set_defaults(command=Server.command_status)
    subparser.add_argument('number', type=int, help='Server number 01..99')

    subparser = subparsers.add_parser('keepalive', description='Background process to keep the server alive by restarting or recreating it')
    subparser.set_defaults(command=Server.command_keepalive)
    subparser.add_argument('number', type=int, help='Server number 01..99')
    subparser.add_argument('-s', '--stop', action='store_true', default=False, help='Stops a running keepalive rather than starting one')
    subparser.add_argument('-p', '--period', type=int, default=10, help='Period of repeated checks [seconds]')

    subparser = subparsers.add_parser('recreate', description='Recreates and starts an existing Torch server')
    subparser.set_defaults(command=Server.command_recreate)
    subparser.add_argument('number', type=int, help='Server number 01..99, port number is 27000 + server number')

    subparser = subparsers.add_parser('restart', description='Stops and restarts an existing Torch server')
    subparser.set_defaults(command=Server.command_restart)
    subparser.add_argument('number', type=int, help='Server number 01..99, port number is 27000 + server number')

    subparser = subparsers.add_parser('upgrade', description='Upgrades Torch from the ds00 template (must be stopped)')
    subparser.set_defaults(command=Server.command_upgrade)
    subparser.add_argument('number', type=int, help='Server number 01..99')

    argcomplete.autocomplete(parser)

    args = parser.parse_args()

    if 'command' not in args:
        parser.print_usage()
        sys.exit(0)

    command = args.command

    if 'number' in args:
        number = args.number
        if number < 1 or number > 99:
            fail(f'Invalid server number: {args.number}')

        server = Server(number)

        if command is Server.command_create:
            with filelock.FileLock(get_file_lock_path(number)):
                result = server.command_create(world_zip_path=os.path.abspath(args.world), suffix=args.suffix)
        elif command is Server.command_start:
            with filelock.FileLock(get_file_lock_path(number)):
                result = server.command_start(args.update)
        elif command is Server.command_start:
            with filelock.FileLock(get_file_lock_path(number)):
                result = server.command_archive(full=args.full)
        elif command is Server.command_keepalive:
            result = server.command_keepalive(stop=args.stop, period=args.period)
        else:
            with filelock.FileLock(get_file_lock_path(number)):
                result = command(server)

    else:
        result = command()

    sys.exit(result)


if __name__ == '__main__':
    main()
