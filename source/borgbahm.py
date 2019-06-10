#!/usr/bin/env python3
"""
A program for conveniently creating and restoring backups of the /home directory on an
external drive with borg backup.
"""
__docformat__ = 'reStructuredText'
# ***************************************************************************************
#  File Name: borgbahm.py
#
# ---------------------------------------------------------------------------------------
#                           C O P Y R I G H T
# ---------------------------------------------------------------------------------------
#             Copyright (c) 2019 by Frank Voorburg   All rights reserved
#
#   This software has been carefully tested, but is not guaranteed for any particular
# purpose. The author does not offer any warranties and does not guarantee the accuracy,
#    adequacy, or completeness of the software and is not responsible for any errors or
#              omissions or the results obtained from use of the software.
# ---------------------------------------------------------------------------------------
#                             L I C E N S E
# ---------------------------------------------------------------------------------------
# This file is part of borgbahm. Borgbahm is free software: you can redistribute it 
# and/or modify it under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# Borgbahm is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; 
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
# PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with this
# program. If not, see <http://www.gnu.org/licenses/>.
#
# ***************************************************************************************

# ***************************************************************************************
#  Imports
# ***************************************************************************************
import logging
import os
import subprocess
import datetime
import time
import shutil
import argparse


# ***************************************************************************************
#  Global constant declarations
# ***************************************************************************************
# Program return codes.
RESULT_OK = 0
RESULT_ERROR_SUPER_USER_PRIVILEGES = 1
RESULT_ERROR_MOUNT_DEVICE = 2
RESULT_ERROR_UNMOUNT_DEVICE = 3
RESULT_ERROR_BORG_ENVIRONMENT = 4
RESULT_ERROR_INVALID_REPOSITORY = 5
RESULT_ERROR_BACKUP = 6
RESULT_ERROR_PRUNE = 7
RESULT_ERROR_RESTORE = 8


# ***************************************************************************************
#  Implementation
# ***************************************************************************************
def main():
    """
    Entry point into the program.
    """
    # Initialize the program exit code.
    result = RESULT_OK

    # Handle command line parameters.
    parser = argparse.ArgumentParser(description="Manage backups of the /home directory with borg. " +
                                     "Run this program on a daily\r\nbasis to create incremental backups. It " +
                                     "automatically maintains 7 daily,\r\n4 weekly and 6 monthly backup archives.",
                                     epilog="Example for creating a new backup archive:\r\n" +
                                     "\tsudo borgbahm.py /dev/sdc /mnt/backup borgrepo Pa55w0rd\r\n\r\n" +
                                     "Example for restoring from the most recent backup archive:\r\n" +
                                     "\tsudo borgbahm.py --restore /dev/sdc /mnt/backup borgrepo Pa55w0rd\r\n\r\n" +
                                     "It is assumed that the 'mountdir' exists and that the 'borgrepo' on the " +
                                     "device\r\nis initialized. To initialize a borg repository use:\r\n" +
                                     "\tsudo borg init --encryption=repokey /mnt/backup/borgrepo\r\n\r\n",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    # Add mandatory command line parameters.
    parser.add_argument('device', type=str, help='device name of the backup drive partition, e.g. /dev/sdc.')
    parser.add_argument('mountdir', type=str, help='directory for mounting the device, e.g. /mnt/backup.')
    parser.add_argument('reponame', type=str, help='name of the borg repository on the device, e.g. borgrepo.')
    parser.add_argument('passphrase', type=str, help='passphrase to access the borg repository, e.g. Pa55w0rd.')

    # Add optional command line parameters.
    parser.add_argument('-d', '--debug', action='store_true', dest='debug_enabled', default=False,
                        help='enable debug messages on the standard output.')
    parser.add_argument('-r', '--restore', action='store_true', dest='restore_mode', default=False,
                        help='restore from the most recent archive, instead of backing up.')
    parser.add_argument('-q', '--quiet', action='store_true', dest='quiet_mode', default=False,
                        help='enable quiet mode for less output.')
    # Perform actual command line parameter parsing.
    args = parser.parse_args()

    # Set the configuration values that where specified on the command line.
    cfg_device_name = args.device
    # The directory where the cfg_device_name should be mounted. Note that this directory must
    # exist, otherwise the mount operation fails.
    cfg_mountpoint_directory = args.mountdir
    # The name of the borg backup repository. After cfg_device_name is mounted, it should be
    # located at cfg_mountpoint_directory/cfg_borg_repository_name.
    cfg_borg_repository_name = args.reponame
    # The passphrase for accessing the borg backup repository.
    cfg_borg_repository_passphrase = args.passphrase

    # Initialize local variables
    borg_repo_url = os.path.join(os.path.normpath(cfg_mountpoint_directory), cfg_borg_repository_name)
    borg_repo_passphrase = cfg_borg_repository_passphrase

    # Enable debug logging level if requested.
    if args.debug_enabled:
        logging.basicConfig(level=logging.DEBUG)

    # This program must run with super user privileges. Check this before continuing.
    if result == RESULT_OK:
        if not args.quiet_mode:
            display_info('Checking availability of super user privileges.')
        if not privileges_check_superuser():
            result = RESULT_ERROR_SUPER_USER_PRIVILEGES
            logging.error('This script requires super user privileges.')

    # Attempt to mount the device.
    if result == RESULT_OK:
        if not args.quiet_mode:
            display_info('Mounting {} to directory {}.'.format(cfg_device_name, cfg_mountpoint_directory))
        if not device_mount(cfg_device_name, cfg_mountpoint_directory):
            result = RESULT_ERROR_MOUNT_DEVICE
            logging.error('The device {} could not be mounted to {}'.format(cfg_device_name, cfg_mountpoint_directory))

    # Attempt to initialize the borg environment. This also checks if the borg repository is present.
    if result == RESULT_OK:
        if not args.quiet_mode:
            display_info('Initializing environment.')
        if not borg_init_environment(borg_repo_url, borg_repo_passphrase):
            result = RESULT_ERROR_BORG_ENVIRONMENT
            logging.error('The borg environment could not be initialized. Verify that borg is installed and ' +
                          'the repository is created.')

    # Perform a consistency check of the borg repository.
    if result == RESULT_OK:
        if not args.quiet_mode:
            display_info('Checking {} repository consistency.'.format(borg_repo_url))
        if not borg_check_repository():
            result = RESULT_ERROR_INVALID_REPOSITORY
            logging.error('The borg repository consistency check failed. It is recommeded to create a new one.')

    # Perform the actual backup, when no restore operation was requested.
    if result == RESULT_OK and not args.restore_mode:
        if not args.quiet_mode:
            display_info('Creating new backup archive.')
        if not borg_perform_backup():
            result = RESULT_ERROR_BACKUP
            logging.error('Borg encountered an error when creating the backup archive.')

    # Perform the pruning to remove those archives that are no longer needed, when no restore operation was requested.
    if result == RESULT_OK and not args.restore_mode:
        if not args.quiet_mode:
            display_info('Removing old backup archives that are no longer needed.')
        if not borg_perform_prune():
            result = RESULT_ERROR_PRUNE
            logging.error('Borg encountered an error when pruning the backup archive(s).')

    # Perform restore operation from the most recent backup archive, when restore operated was requested.
    if result == RESULT_OK and args.restore_mode:
        if not args.quiet_mode:
            display_info('Restoring the backup archive with name {}'.format(borg_get_most_recent_archive_name()))
        if not borg_perform_restore():
            result = RESULT_ERROR_RESTORE
            logging.error('Borg encountered an error when restoring from the most recent backup archive.')

    # Unmount the device. Note that this should always be done, regardless of the result value.
    if not args.quiet_mode:
        display_info('Unmounting {} from directory {}.'.format(cfg_device_name, cfg_mountpoint_directory))
    if not device_unmount(cfg_device_name, cfg_mountpoint_directory):
        result = RESULT_ERROR_UNMOUNT_DEVICE
        logging.error('The mountpoint {} could not be unmounted.'.format(cfg_mountpoint_directory))

    # Give the exit code back to the caller
    return result


def borg_init_environment(repo_location, repo_passphrase):
    """
    Initializes the borg environment by exporting the BORG_REPO and BORG_PASSPHRASE
    shell variables. This function should be called once before any other borg_xxx()
    functions are called.

    :param repo_location: The location of the borg repository.
    :param repo_passphrase: The passphrase for accessing the borg repository.

    :returns: True if successful, False otherwise.
    :rtype: bool
    """
    result = True

    # Run the command to check if borg is installed.
    borg_installed = shutil.which('borg') is not None
    logging.debug('Borg program installation check: {}'.format(borg_installed))

    if not borg_installed:
        result = False

    # Check if there is actually a repository here. Each borg repository should have a
    # file with the name 'config' in it.
    borg_repo_config_file_present = os.path.isfile(os.path.join(repo_location, 'config'))
    logging.debug('Borg repository config file present: {}'.format(borg_repo_config_file_present))

    if not borg_repo_config_file_present:
        result = False

    # Export the shell variables for borg.
    os.environ['BORG_REPO'] = repo_location
    os.environ['BORG_PASSPHRASE'] = repo_passphrase

    # Give the exit code back to the caller
    return result


def borg_check_repository():
    """
    Check if there is a valid repository, otherwise the user needs to initialized it
    manually using 'borg init'.

    :returns: True if successful, False otherwise.
    :rtype: bool
    """
    result = False

    # Check if there is a valid repository, otherwise 'borg init' needs to first be used.
    cmd = ['borg', 'check', '--repository-only']
    cmd_return = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode
    logging.debug('Borg check command returned {}'.format(cmd_return))

    # Check if the command was successful
    if cmd_return == 0:
        result = True

    # Give the result back to the caller
    return result


def borg_perform_backup():
    """
    Performs the actual backup operation of the /home directory. It is stored into a new
    archive names after the machine this program is currently running on.

    :returns: True if successful, False otherwise.
    :rtype: bool
    """
    result = False

    # Assemble the borg command for creating a new backup archive and run it.
    cmd = ['borg', 'create', '--verbose', '--stats', '--compression', 'lz4',
           '--exclude-caches', '--exclude', '/home/*/.cache/*', '::{hostname}-{now:%Y-%m-%dT%H:%M:%S}', '/home']
    cmd_return = subprocess.run(cmd).returncode
    logging.debug('Borg create command returned {}'.format(cmd_return))

    # Check if the command was successful, either success (0) or warning (1).
    if cmd_return == 0 or cmd_return == 1:
        result = True

    # Give the result back to the caller
    return result


def borg_perform_prune():
    """
    Performs the prune operation to maintain 7 daily, 4 weekly and 6 monthly archives of
    this machine.

    :returns: True if successful, False otherwise.
    :rtype: bool
    """
    result = True

    # Assemble the borg command for pruning show archives that are no longer needed and run it.
    cmd = ['borg', 'prune', '--verbose', '--list', '--prefix', '{hostname}-',
           '--keep-daily', '7', '--keep-weekly', '4', '--keep-monthly', '6']
    cmd_return = subprocess.run(cmd).returncode
    logging.debug('Borg prune command returned {}'.format(cmd_return))

    # Check if the command was successful, either success (0) or warning (1).
    if cmd_return == 0 or cmd_return == 1:
        result = True

    # Give the result back to the caller
    return result


def borg_perform_restore():
    """
    Restores from the most recent backup archive.

    :returns: True if successful, False otherwise.
    :rtype: bool
    """
    result = True

    # Get the name of the most recent backup archive and validate it.
    archive_to_restore = borg_get_most_recent_archive_name()
    logging.debug('Most recent backup archive: {}.'.format(archive_to_restore))
    if not archive_to_restore:
        result = False

    # Only continue with the restore operations if all is okay so far.
    if result is True:
        # Backup was make from /home, so the restore operation should be relative to the / directory.
        # First backup the current directory and then change to the root directory.
        current_dir_backup = os.getcwd()
        os.chdir('/')

        # Assemble the borg command for extracting the most recent backup archive and run it.
        cmd = ['borg', 'extract', '--verbose', '--list', '::{}'.format(archive_to_restore)]
        cmd_return = subprocess.run(cmd).returncode
        logging.debug('Borg extract command returned {}'.format(cmd_return))

        # Check if the command was not successful, so either success (0) or warning (1).
        if not cmd_return == 0 and not cmd_return == 1:
            result = False

        # Restore the initial work directory again.
        os.chdir(current_dir_backup)

    # Give the result back to the caller
    return result


def borg_get_most_recent_archive_name():
    """
    Obtains the name of the most recent backup archive name in the backup repository.

    :returns: The name of the most recent backup archive if successful, empty string otherwise.
    :rtype: string
    """
    result = ''

    # Assemble the borg command for listing the most recent archive. Note that borg >= v1.1.0 supports
    # the '--last 1' parameter, but this code is written to support older versions as well. This means
    # we have to run get the last listed archive from the standard output generated by the 'borg list'
    #  command.
    cmd = ['borg', 'list', '--verbose', '--prefix', '{hostname}-']
    cmd_result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    logging.debug('Borg list command returned {}'.format(cmd_result.returncode))

    # Check if the command was successful, either success (0) or warning (1).
    if cmd_result.returncode == 0 or cmd_result.returncode == 1:
        # Get the standard output and pass it as a parameter to 'tail' to get the last listing, which is
        # the most recent backup archive.
        borg_archive_list = cmd_result.stdout.decode('utf-8').splitlines()
        # Only continue if the list is not empty:
        if borg_archive_list:
            # Get the last entry in the list.
            borg_most_recent_archive_line = borg_archive_list[-1].strip()
            # Only continue if the line is not empty.
            if borg_most_recent_archive_line:
                # Get the first part of the line, which is the archive name.
                borg_most_recent_archive = borg_most_recent_archive_line.split(' ')[0:1][0]
                logging.debug('Borg list most recent archive {}'.format(borg_most_recent_archive))
                # Only set the result if the detected archive string is not empty.
                if borg_most_recent_archive:
                    result = borg_most_recent_archive

    # Give the result back to the caller
    return result


def device_mount(device_name, mount_dir):
    """
    Mounts the device_name to the specified mount_dir directory.

    :param device_name: The device name. Typically something such as /dev/sdx. Use
           'sudo fdisk -l' to list the available devices on the system.
    :param mount_dir: The mountpoint directory.
    :returns: True if successful, False otherwise.
    :rtype: bool
    """
    result = True

    # First check that the directory to mount to actually exists on the system.
    if not os.path.isdir(mount_dir):
        result = False
        logging.debug('The mountpoint {} does not exist'.format(mount_dir))

    # Continue with mounting if all is okay so far.
    if result:
        # Run the command to mount the device.
        cmd = ['mount', os.path.normpath(device_name), mount_dir]
        cmd_return = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode
        logging.debug('Mount command for device {} to directory {} returned {}'.format(device_name, mount_dir,
                      cmd_return))

        # Verify that the device was mounted correctly at the specified directory.
        if not device_is_mounted(device_name, mount_dir):
            result = False
            logging.debug('Mounting {} to {} failed'.format(device_name, mount_dir))

    # Give the result back to the caller
    return result


def device_unmount(device_name, mount_dir):
    """
    Unmounts the device that was previously mounted to the specified mount_dir directory.

    :param device_name: The device name. Typically something such as /dev/sdx. Use
           'sudo fdisk -l' to list the available devices on the system.
    :param mount_dir: The mountpoint directory.
    :returns: True if successful, False otherwise.
    :rtype: bool
    """
    result = True

    # First check that the directory to unmount from actually exists on the system.
    if not os.path.isdir(mount_dir):
        result = False
        logging.debug('The mountpoint {} does not exist'.format(mount_dir))

    # Continue with unmounting if all is okay so far and the device is actually mounted
    # at the specified mountpoint. Otherwise no unmounting needs to be done.
    if result and device_is_mounted(device_name, mount_dir):
        # Add a small delay to make sure the device is no longer busy.
        time.sleep(2)
        # Run the command to unmount the specified directory
        cmd = ['umount', mount_dir]
        cmd_return = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode
        logging.debug('Unmount command for directory {} returned {}'.format(mount_dir, cmd_return))

        # Check the command return code and update the result accordingly.
        if cmd_return != 0:
            result = False

    # Give the result back to the caller
    return result


def device_is_mounted(device_name, mount_dir):
    """
    Checks if a device is actually mounted at the specified mount_dir directory,

    :param device_name: The device name. Typically something such as /dev/sdx. Use
           'sudo fdisk -l' to list the available devices on the system.
    :param mount_dir: The mountpoint directory.
    :returns: True if mounted, False otherwise.
    :rtype: bool
    """
    result = True

    # First check that the directory of the mountpoint to check actually exists on the
    # system.
    if not os.path.isdir(mount_dir):
        result = False
        logging.debug('The mountpoint {} does not exist'.format(mount_dir))

    # Continue with checking the mountpoint if all is okay so far.
    if result:
        cmd = ['lsblk', '-o', 'MOUNTPOINT', '-nr', os.path.normpath(device_name)]
        cmd_result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Check if the command was successful before processing its output.
        if cmd_result.returncode == 0:
            mounted_dir = cmd_result.stdout.decode('utf-8').strip().splitlines()[0:1][0]
            logging.debug('Device {} reports to be mounted at {}'.format(device_name, mounted_dir))
            # Compare the mount directories to check if they match. Make sure to remove trailing
            # slashes at the end to make sure they are similar.
            if os.path.normpath(mount_dir) != os.path.normpath(mounted_dir):
                result = False
        else:
            # Command was not successful.
            result = False
            logging.debug('lsblk command for device {} failed'.format(device_name))

    # Give the result back to the caller
    return result


def privileges_check_superuser():
    """
    Checks if the program is run with super user privileges.

    :returns: True if super user privileges are available, False otherwise.
    :rtype: bool
    """
    result = False

    # The super user always has ID 0, so check for this.
    if os.geteuid() == 0:
        result = True

    # Give the result back to the caller
    return result


def display_info(info):
    """
    Display the info string on the standard output prefixed with the current date and time.
    """
    print('[{}] '.format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")) + info)


if __name__ == '__main__':
    exit(main())


# ********************************* end of borgbahm.py **********************************
