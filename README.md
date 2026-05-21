# Convert a AlmaLinux 8 server with Plesk to AlmaLinux 9

AlmaLinux 8 to 9 conversion tool

## Introduction
This script is the official tool for converting a AlmaLinux 8 server with Plesk to AlmaLinux 9. It uses the [AlmaLinux Elevate tool](https://repo.almalinux.org/elevate/), which is based on the [leapp modernization framework](https://leapp.readthedocs.io/en/latest/). The script includes additional repository and configuration support provided by Plesk.

## Preparation
To avoid downtime and data loss, make sure you have read and understood the following information before using the script:
1. **Back up all your databases** and have the means to restore them. The script uses standard MariaDB and PostgreSQL tools to upgrade the databases, but this does not guarantee that the process will be free of issues.
2. **Ensure that you have a way to restart the server without a direct SSH connection**. The conversion process may get stuck once the server boots into the temporary OS distribution that does not start any network interfaces. You can use a serial port connection to the server to monitor the status of the conversion process in real time, and to reboot the server if necessary.
3. We strongly recommend that you **create a snapshot you can use as a recovery point** in case the conversion process fails.
4. Read the [Known issues](#known-issues) section below for the list of known issues.

## Timing
The conversion process should run between 50 and 80 minutes. **Plesk services, hosted websites, and emails will be unavailable during the entirety of the conversion process**. The conversion process itself consists of three stages:
- Preparation, which takes between 30 and 40 minutes.
- Conversion, which takes between 15 and 30 minutes. During this stage, the server will not be available remotely. You can monitor the progress via a serial port console.
- Finalization, which takes between 5 and 10 minutes.

## Known issues
### Blockers
Do not use the script if any of the following is true:
- **You are running an OS other than AlmaLinux 8.9**. The script was not tested on other Red Hat Enterprise Linux 8-based distributions. The conversion process may have unexpected results if started on a server not running AlmaLinux 8.9. So we add checks to avoid any actions on such kinds of servers.
- **Plesk version is more than five releases behind the latest version**. The script is only compatible with the most recent versions of Plesk. It will prevent conversion if Plesk version is outdated.
- **PHP 5.5 and earlier are not supported** in AlmaLinux 9, and will not receive any updates after the conversion. These PHP versions are deprecated and may have security vulnerabilities. So we force to remove this versions before the conversion.
- **Conversion inside containers (like Virtuozzo containers, Docker Containers, etc) are not supported**. 
- **More than one kernel named interfaces (like ethX) are not supported**. Stability of such names are not guaranteed, so leapp prevent the conversion in such cases.

## Requirements
- Plesk version is not older than five releases back from the latest version
- AlmaLinux 8.9 or later.
- grub2 is installed
- At least 5 GB of free disk space.
- At least 1 GB of RAM.

## Using the script
To retrieve the latest available version of the tool, please navigate to the "Releases" section. Once there, locate the most recent version of the tool and download the zip archive. The zip archive will contain the almalinux8to9 tool binary.

To prepare the latest version of the tool for use from a command line, please run the following commands:
```shell
> wget https://github.com/plesk/almalinux8to9/releases/download/v1.0.0/almalinux8to9-1.0.0.zip
> unzip almalinux8to9-1.0.0.zip
> chmod 755 almalinux8to9
```

To monitor the conversion process, we recommend using the ['screen' utility](https://www.gnu.org/software/screen/) to run the script in the background. To do so, run the following command:
```shell
> screen -S almalinux8to9
> ./almalinux8to9
```
If you lose your SSH connection to the server, you can reconnect to the screen session by running the following command:
```shell
> screen -r almalinux8to9
```


You can also call almalinux8to9 in the background:
```shell
> ./almalinux8to9 &
```
And monitor its status with the '--status' or '--monitor' flags:
```shell
> ./almalinux8to9 --status
> ./almalinux8to9 --monitor
... live monitor session ...
```


This will start the conversion process. During the process, Plesk services will stop, and hosted websites will not be accessible. At the end of the preparation stage, the server will reboot.
Next, a temporary OS distribution will be used to convert your AlmaLinux 8 system to AlmaLinux 9. This process will take approximately 20 minutes. Once completed, the server will reboot once more. The almalinux8to9 script will then perform the final stages of reconfiguring and restoring Plesk-related services, configurations, and databases. This will take some time, depending on the number of hosted websites.
Once the process is complete, the almalinux8to9 script will reboot the server one last time. After that, Plesk should return to normal operation.
On the next SSH login, you will be greeted with the following message:
```
===============================================================================
Message from the Plesk almalinux8to9 tool:
The server has been converted to AlmaLinux 9.
You can remove this message from the /etc/motd file.
===============================================================================
```

### Conversion stage options
The conversion process consists of two stage options: "start", and "finish". To run stages individually, use the "--start", and "--finish" flags, or the "-s" flag with name of the stage you want to run.
1. The "start" stage installs and configures ELevate, disables Plesk services and runs ELevate. It then stops Plesk services and reboots the server.
2. The "finish" stage must be called automatically on the first boot of AlmaLinux 9. You can rerun this stage if something goes wrong during the first boot to ensure that the problem is fixed and Plesk is ready to use.

During each phase a conversion plan consisting of stages, which in turn consist of actions, is executed. You can see the general stages in the `--help` output and the detailed plan in the `--show-plan` output.

### Other arguments

### Logs
If something goes wrong, read the logs to identify the problem. You can also read the logs to check the status of the finish stage during the first boot.
The almalinux8to9 writes its log to the '/var/log/plesk/almalinux8to9.log' file, as well as to stdout.
The ELevate writes its log to the '/var/log/leapp/leapp-upgrade.log' file. Reports can be found in the '/var/log/leapp/leapp-report.txt' and the '/var/log/leapp/leapp-report.json' files.

### Revert
If the script fails during the the "start" stage before the reboot, you can use the almalinux8to9 script with the '-r' or '--revert' flags to restore Plesk to normal operation. The almalinux8to9 will undo some of the changes it made and restart Plesk services. Once you have resolved the root cause of the failure, you can attempt the conversion again.
Note:
- You cannot use revert to undo the changes after the first reboot triggered by almalinux8to9.
- Revert does not remove Leapp or packages installed by Leapp. Neither does it free persistent storage disk space reserved by Leapp.

### Check the status of the conversion process and monitor its progress
To check the status of the conversion process, use the '--status' flag. You can see the current stage of the conversion process, the elapsed time, and the estimated time until finish.
```shell
> ./almalinux8to9 --status
``` 

To monitor the progress of the conversion process in real time, The conversion process can be monitored in real time using the '--monitor' flag.
```shell
> ./almalinux8to9 --monitor
( stage 3 / action re-installing plesk components  ) 02:26 / 06:18
```

### Special cases

#### Postgresql database before version 10 is installed
By default, the tool does not allow conversion when a PostgreSQL database version prior to 10 is installed. This restriction is in place to warn about the potential loss of data during the PostgreSQL upgrade that will be performed as part of the conversion process.

In such cases, you have two options:

1. Upgrade PostgreSQL to version 10 manually before initiating the conversion.
2. Create a complete backup of the database and force the conversion using the '--upgrade-postgres' flag.

#### Perl modules installed by CPAN
During the conversion process, if the tool detects Perl modules that were installed via CPAN and cannot determine their corresponding RPM packages, it will fail with a warning. This restriction is in place because such modules will not be available after the conversion. This issue often arises because CPAN-installed modules are specifically built for a particular version of Perl. Consequently, when Perl is updated during the conversion process, these module libraries may encounter errors related to undefined symbols.

To prevent this issue, there are steps you can check for RPM package analogues for the modules, remove the CPAN modules, and then reinstall them after the conversion is complete. It is recommended to use RPM packages for reinstallation, although reinstalling the modules via CPAN is also an option.

The almalinux8to9 tool includes a list of RPM mappings for certain modules and can automatically reinstall them. The warning will only raise for modules that mapping to rpm package is unknown by the tool.

If you are confident that you no longer require the modules installed via CPAN, you can forcefully remove them by running the tool with the '--remove-unknown-perl-modules' flag.

## Issue handling
### Leapp unable to handle packages
Leapp may not be able to handle certain installed packages, especially those installed from custom repositories. In this case, the almalinux8to9 will fail while running leapp preupgrade or leapp upgrade. The easiest way to fix this issue is to remove the package(s), and then reinstall them once the conversion is complete.

### Leapp cannot choose which package to install
This issue may occur if unsupported repositories are used. For instance, if an unexpected EPEL repository is enabled on the server, the almalinux8to9 process will fail when running `leapp preupgrade` or `leapp upgrade`. This is due to conflicting packages between the el9 and el8 repositories. The simplest way to resolve this issue is to switch to the standard repositories.

### Temporary OS distribution hangs
This issue may occur, for example, if there is a custom python installation on the server or because of encoding inconsistency. The conversion process will fail while upgrading the temporary OS distribution, and the temporary OS will hang with no notification. To identify the issue, connect to the server using a serial port console and check the status of the conversion process. To fix the issue, reboot the server. Note that an unfinished installation process may result in missing packages and other issues.

### almalinux8to9 finish fails on the first boot
If something goes wrong during the finish stage, you will be informed on the next SSH login with this message:
```
===============================================================================
Message from Plesk almalinux8to9 tool:
Something went wrong during the final stage of AlmaLinux 8 to AlmaLinux 9 conversion
See the /var/log/plesk/almalinux8to9.log file for more information.
You can remove this message from the /etc/motd file.
===============================================================================
```
You can read the almalinux8to9 log to troubleshoot the issue. If the almalinux8to9 finish stage fails for any reason, once you have resolved the root cause of the failure, you can retry by running 'almalinux8to9 -s finish'.

### Send feedback
If you got any error, please [create an issue on github](https://github.com/plesk/almalinux8to9/issues). To do generate feedback archive by calling the tool with '-f' or '--prepare-feedback' flags.
```shell
./almalinux8to9 --prepare-feedback
```
Describe your problem and attach the feedback archive to the issue.
