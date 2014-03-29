# This file is part of Checkbox.
#
# Copyright 2014 Canonical Ltd.
# Written by:
#   Zygmunt Krynicki <zygmunt.krynicki@canonical.com>
#
# Checkbox is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3,
# as published by the Free Software Foundation.
#
# Checkbox is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Checkbox.  If not, see <http://www.gnu.org/licenses/>.

"""
Extension module for manage.py
==============================

This file should be copied to any plainbox test provider that wants
to add or customize 'manage.py' subcommands and expect to work with
plainbox 0.5.x LTS release.

This module provides two new functions:

1) An improved version of plainbox.provider_manage.setup()
2) A new decorator function manage_py_extension()

If imported, the maange.py script will have new subcommands:

``manage.py build``:
    to build provider executables from source
``manage.py clean``
    to clean build artifacts

In addition, the following subcommands will behave differently:

``manage.py sdist``:
    will package the manage_ext.py file and src/ directories
``manage.py install``:
    will also copy executables from build/bin
"""

import inspect
import os
import shlex
import shutil
import subprocess

from plainbox.provider_manager import ConfigValidationError
from plainbox.provider_manager import InstallCommand
from plainbox.provider_manager import ManageCommand
from plainbox.provider_manager import N_
from plainbox.provider_manager import Provider1Definition
from plainbox.provider_manager import ProviderManagerTool
from plainbox.provider_manager import SourceDistributionCommand
from plainbox.provider_manager import Unset
from plainbox.provider_manager import _
from plainbox.provider_manager import _logger 
from plainbox.provider_manager import docstring
from plainbox.provider_manager import setup_logging

__all__ = ['manage_py_extension', 'setup']


def manage_py_extension(cls):
    """
    A decorator for classes that extend subcommands of `manage.py`

    :param cls:
        A new management subcommand class. Either a new class (subclassing
        ManageCommand directly) or a subclass of one of the standard manage.py
        command classes). New commands are just appended, replacement commands
        override the stock version.
    :returns:
        cls itself, unchanged
    """
    cmd_list = ProviderManagerTool._SUB_COMMANDS
    orig = cls.__bases__[0]
    if orig == ManageCommand:
        # New subcommand, just append it
        cmd_list.append(cls)
    else:
        # Override / replacement for an existing command
        index = cmd_list.index(orig)
        del cmd_list[index]
        cmd_list.insert(index, cls)
    return cls


class ProviderManagerToolExt(ProviderManagerTool):
    """
    Extended ProviderManagerTool that optionally initializes subcommand classes
    with a full list of keywords passed to setup()
    """

    def __init__(self, definition, keywords):
        super().__init__(definition)
        self._keywords = keywords

    def add_subcommands(self, subparsers):
        """
        Add top-level subcommands to the argument parser.
        """
        for cmd_cls in self._SUB_COMMANDS:
            if getattr(cmd_cls, 'SUPPORTS_KEYWORDS', False):
                cmd = cmd_cls(self.definition, self._keywords)
            else:
                cmd = cmd_cls(self.definition)
            cmd.register_parser(subparsers)


def setup(**kwargs):
    """
    The setup method that is being called from generated manage.py scripts.

    This setup method is similar in spirit to the setup.py's setup() call
    present in most python projects. It takes any keyword arguments and tries
    to make the best of it.

    :param kwargs:
        arbitrary keyword arguments, see below for what we currently look up
    :raises:
        SystemExit with the exit code of the program. This is done regardless
        of normal / abnormal termination.

    The following keyword parameters are supported:

        name:
            name of the provider (IQN compatible). Typically something like
            ``2013.org.example:some-name`` where the ``some-name`` is a simple
            identifier and a private namespace for whoever owned
            ``org.example`` in ``2013``

        version:
            version string, required

        description:
            description (may be long/multi line), optional

        gettext_domain:
            gettext translation domain for job definition strings, optional

    Remaining keyword arguments are available for inspection from all
    subcommands.  It is expected that test authors that need to override an
    existing command or add a new command will simply access the relevant data
    directly.
    """
    setup_logging()
    manage_py = inspect.stack()[1][0].f_globals['__file__']
    location = os.path.dirname(os.path.abspath(manage_py))
    definition = Provider1Definition()
    try:
        definition.location = location
        definition.name = kwargs.get('name', None)
        definition.version = kwargs.get('version', None)
        definition.description = kwargs.get('description', None)
        definition.gettext_domain = kwargs.get('gettext_domain', Unset)
    except ConfigValidationError as exc:
        raise SystemExit(_("{}: bad value of {!r}, {}").format(
            manage_py, exc.variable.name, exc.message))
    else:
        raise SystemExit(ProviderManagerToolExt(definition, kwargs).main())


# https://bugs.launchpad.net/checkbox/+bug/1297255
@manage_py_extension
@docstring(SourceDistributionCommand.__doc__)
class SourceDistributionCommandExt(SourceDistributionCommand):
    _INCLUDED_ITEMS = (
        SourceDistributionCommand._INCLUDED_ITEMS
        + ['src', 'manage_ext.py'])


# https://bugs.launchpad.net/checkbox/+bug/1297255
@manage_py_extension
@docstring(InstallCommand.__doc__)
class InstallCommandExt(InstallCommand):
    
    name = 'install'

    # https://bugs.launchpad.net/checkbox/+bug/1299486
    _LOCATION_TEMPLATE = os.path.join(
        '{prefix}', 'lib', 'plainbox-providers-1',
        '{provider.name}')

    def invoked(self, ns):
        super().invoked(ns)
        self._install_src_executables(ns)

    @property
    def build_bin(self):
        return os.path.join(self.definition.location, 'build/bin')

    def _install_src_executables(self, ns):
        dest_map = self._get_dest_map(ns.layout, ns.prefix)
        dst_dir = ns.root + dest_map['bin']
        src_dir = self.build_bin
        for filename in os.listdir(src_dir):
            src_file = os.path.join(src_dir, filename)
            if os.access(src_file, os.X_OK) or filename.endswith('.exe'):
                try:
                    os.makedirs(dst_dir, exist_ok=True)
                except (IOError, OSError):
                    pass
                _logger.info(_("copying: %s => %s"), src_file, dst_dir)
                shutil.copy(src_file, dst_dir)


# https://bugs.launchpad.net/checkbox/+bug/1297256
@manage_py_extension
@docstring(
    # TRANSLATORS: please leave various options (both long and short forms),
    # environment variables and paths in their original form. Also keep the
    # special @EPILOG@ string. The first line of the translation is special and
    # is used as the help message. Please keep the pseudo-statement form and
    # don't finish the sentence with a dot.  Pay extra attention to whitespace.
    # It must be correctly preserved or the result won't work. In particular
    # the leading whitespace *must* be preserved and *must* have the same
    # length on each line.
    N_("""
    build provider specific executables from source

    This command builds provider specific executables from source code.

    The actual logic on how that is done is supplied by provider authors as a
    part of setup() call inside this manage.py script, as the build_cmd
    keyword argument.

    @EPILOG@

    Examples
    ========

    A provider using make to build provider-specific executables

    setup(
       clean_cmd='make -C src'
    )
    """))
class BuildCommand(ManageCommand):

    SUPPORTS_KEYWORDS = True

    def __init__(self, definition, keywords):
        """
        Initialize a new ManageCommand instance with the specified provider.

        :param provider:
            A Provider1Definition that describes the provider to encapsulate
        :param keywords:
            A set of keywords passed to setup()
        """
        super().__init__(definition)
        self._keywords = keywords

    @property
    def build_cmd(self):
        """
        shell command to build the sources
        """
        return self._keywords.get("build_cmd")

    @property
    def src_dir(self):
        """
        absolute path of the src/ subdirectory
        """
        return os.path.join(self.definition.location, 'src')

    def register_parser(self, subparsers):
        """
        Overridden method of CommandBase.

        :param subparsers:
            The argparse subparsers objects in which command line argument
            specification should be created.

        This method is invoked by the command line handling code to register
        arguments specific to this sub-command. It must also register itself as
        the command class with the ``command`` default.
        """
        parser = self.add_subcommand(subparsers)
        parser.add_argument(
            '-n', '--dry-run',
            action='store_true', default=False,
            help=_("don't actually run any commands; just print them"))

    def invoked(self, ns):
        if self.build_cmd is None:
            print(_("This provider doesn't define build_cmd."))
            # TRANSLATORS: don't translate 'manage.py'
            print(_("Add it to manage.py and try again"))
            return 1
        if not os.path.isdir(self.src_dir):
            print(_("The src/ directory doesn't exist"))
            return 1
        if ns.dry_run:
            if shlex.split(self.build_cmd) == ['make', '-C', 'src']:
                # Special support for make, for more realistic results
                subprocess.call(
                    ['make', '-C', 'src', '-n'],
                    cwd=self.definition.location)
            else:
                print(self.build_cmd)
        else:
            subprocess.call(
                self.build_cmd, shell=True, cwd=self.definition.location)


# https://bugs.launchpad.net/checkbox/+bug/1297256
@manage_py_extension
@docstring(
    # TRANSLATORS: please leave various options (both long and short forms),
    # environment variables and paths in their original form. Also keep the
    # special @EPILOG@ string. The first line of the translation is special and
    # is used as the help message. Please keep the pseudo-statement form and
    # don't finish the sentence with a dot.  Pay extra attention to whitespace.
    # It must be correctly preserved or the result won't work. In particular
    # the leading whitespace *must* be preserved and *must* have the same
    # length on each line.
    N_("""
    clean build results

    This command complements the build command and removes any build artifacts
    including specifically any binary files added to the bin/ directory.

    The actual logic on how that is done is supplied by provider authors as a
    part of setup() call inside this manage.py script, as the build_cmd
    keyword argument

    @EPILOG@

    Examples
    ========

    A provider using make to build provider-specific executables

    setup(
       clean_cmd='make -C src clean'
    )
    """))
class CleanCommand(ManageCommand):

    SUPPORTS_KEYWORDS = True

    def __init__(self, definition, keywords):
        """
        Initialize a new ManageCommand instance with the specified provider.

        :param provider:
            A Provider1Definition that describes the provider to encapsulate
        :param keywords:
            A set of keywords passed to setup()
        """
        super().__init__(definition)
        self._keywords = keywords

    @property
    def clean_cmd(self):
        """
        shell command to clean the build tree
        """
        return self._keywords.get("clean_cmd")

    @property
    def src_dir(self):
        """
        absolute path of the src/ subdirectory
        """
        return os.path.join(self.definition.location, 'src')

    def register_parser(self, subparsers):
        """
        Overridden method of CommandBase.

        :param subparsers:
            The argparse subparsers objects in which command line argument
            specification should be created.

        This method is invoked by the command line handling code to register
        arguments specific to this sub-command. It must also register itself as
        the command class with the ``command`` default.
        """
        parser = self.add_subcommand(subparsers)
        parser.add_argument(
            '-n', '--dry-run',
            action='store_true', default=False,
            help=_("don't actually run any commands; just print them"))

    def invoked(self, ns):
        if self.clean_cmd is None:
            print(_("This provider doesn't define clean_cmd."))
            # TRANSLATORS: don't translate 'manage.py'
            print(_("Add it to manage.py and try again"))
            return 1
        if not os.path.isdir(self.src_dir):
            print(_("The src/ directory doesn't exist"))
            return 1
        if ns.dry_run:
            if shlex.split(self.clean_cmd) == ['make', '-C', 'src', 'clean']:
                # Special support for make, for more realistic results
                subprocess.call(
                    ['make', '-C', 'src', 'clean', '-n'],
                    cwd=self.definition.location)
            else:
                print(self.clean_cmd)
        else:
            subprocess.call(
                self.clean_cmd, shell=True, cwd=self.definition.location)
