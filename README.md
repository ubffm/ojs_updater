# OJS-Updater

## An OJS Update CLI-Script

This tool updates a single instance of an Open Journal System (OJS) on a server to a newer version. It wraps up all
the individual steps that usually have to be carried out manually in one single command and takes additional measures to
safely fall back. Thus, it is especially intended for OJS hosting setups which employ a
one-installation-per-journal policy. Please also refer to the upgrade guide for OJS by PKP: https://docs.pkp.sfu.ca/dev/upgrade-guide/en/

Before updating, the tool will automatically backup your OJS instance folder, the submission folder, and the database.
If anything in the updating process goes wrong, the tool will reset everything to its previous state.

**CAUTION:** The resetting feature was yet only tested with our own servers and settings. We highly recommend doing a
backup yourself at least for the first time you run the tool!

We also created a more [extensive documentation](https://labs.ub.uni-frankfurt.de/post/930/) on the preparation and the workflow, if needed.

### Features

* Automatic update to the highest (locally available) OJS version
* Automatic database and journal backup before the update
* Automatic rollback when errors occur in the update process
* Backup function can be called separately from updating
* Checks permissions of relevant folders and free disk space before updating
* Migration of custom files, folders, and plugins to the updated journal directory - configurable per journal

### Prerequisites

* A Linux (other *nix systems have not been tested; Windows Servers are currently NOT supported!)
* MySQL/MariaDB (support for other databases is currently not implemented)
* Python 3.6+ 
* A running installation of OJS
* [lxml](https://pypi.org/project/lxml/) (Optional)

OJS-Updater is being tested on all currently maintained python versions (3.7+) and python 3.6 on Linux.

### Installation

Simply clone the repository and install it on your server.

```
git clone https://github.com/ubffm/ojs-updater.git
cd ojs-updater
pip install .
```

Alternatively, you can install the package via pip:

```
pip install ojs_updater
```

Now you should be able to simply run to get the help message:

`ojs_updater`

### Preparation

Before running the OJS-Updater, all folders that are configured in the `ojs_updater_settings.yml` have to exist.

The OJS-Updater searches for OJS update folders (i.e. folder with new OJS versions to be applied) in the directory given in the `ojs_updater_settings.yml` with the key `ojs_version_folder`. If multiple OJS update folders exists, the OJS update folder with the highest OJS version will be chosen by default. To fill this folder, simply download **and extract** the desired OJS version from the [PKP OJS Download Page](https://pkp.sfu.ca/ojs/ojs_download/). As described before, OJS update folders containing newer OJS versions can simply be put in the same folder. The OJS version is determined by the `version.xml` file within the respective OJS update folder.

It is suggested, that you setup a folder structure like this:
```shell
$ mkdir -p ojs/{versions,backup/{db,htdocs}}
$ chown -R <webserver-user>:<webserver-group> ojs
```
Example structure:
```
ojs            
├── backup    <-- ojs_backup_folder
│   ├── db    <-- ojs_backup_db
│   └── www   <-- ojs_backup_www
└── versions  <-- ojs_version_folder
```

The script makes, at times, rather specific assumptions in regard to folder structure and permissions. We suggest, that you run the script from the aforementioned folder (e.g. /usr/local/ojs/). Also, in order for the script to properly work, the folder that contains the journal instances has to have the permissions specified in the config file. Therefore, we recommend a folder structure like this:

Example structure:
```
/srv/www/htdocs            
└── journals       <-- Owner/group set to <webserver_user>:<webserver_group> 
    ├── journal_1  
    ├── ...
    └── journal_n  
```

### Configuration

Since every server and OJS provider philosophy may be different, the OJS-Updater tries to acknowledge this by providing you
a `ojs_updater_settings.yml`, where you have to configure all necessary OJS-folders and additional parameters. A subset of these options is also offered as CLI parameters, which take precedence over config file parameters.

In the `ojs_updater_settings.yml.example`, you will find descriptions of each parameter that you can set.

### Usage

**CAUTION!** Be aware that if something in the update process goes wrong, in the worst case, your OJS instance is not
working anymore! The OJS-Updater tries its very best to clean up, if something goes wrong while the updating process,
but it is not guaranteed!

Furthermore, although the OJS-Updater does all the updating process for you, that does NOT mean that it resolves e.g. differences in updated templates (disregarding if the templates were modified locally or if they come with the updated OJS version). Hence, there may be post-update work to do that can be done only manually!

**The tool has to be run as root.** Only as root, you can run

```
ojs_updater /ojs-dir/ojs-instance-folder/
```

However, not the whole update process is done with root privileges. The privileges are dropped soon after some system checking (read/write privileges) is done.

You can provide the tool with command-line arguments that can override parameters given in the `ojs_updater_settings.yml`. At least you have to provide the folder with the OJS instance to update.

```
positional arguments:
  folder                Path to the OJS instance to be upgraded.

optional arguments:
  -h, --help            show this help message and exit
  --permissive          If set, root privileges are not dropped (no warranty;
                        use with caution).
  --debug               Enable debug mode.
  --force               Enforce upgrade, even if the target OJS version is
                        equal. This skips all version number checks.
  -o OWNER, --owner OWNER
                        After dropping root privileges, run as this user.
                        (This should usually be the web server user).
  -g GROUP, --group GROUP
                        After dropping root privileges, run with this group.
                        (This should usually be the web server group).
  --backup              Run only (!) the backup routine.
```

## Tests

We recommend running tests before first usage of the OJS-Updater. This ensures that all method calls are working as intended on your system.

To run tests, you have to install the `requirements-dev.txt` into your virtual environment:

```shell
pip install -r requirements-dev.txt
```

Subsequently, you can simply call:

```shell
pytest .
```

### Version compatibility

In addition to the tests, the OJS-Updater comes with a configuration file for [tox](https://tox.readthedocs.io), which makes it possible to
easily test the software with several python versions simultaneously. 
```shell
tox
```

Please be aware that the tested python versions have to be compiled with `libffi-dev` (python 3.7+). Hence, if you get an error while running `tox` that says something like:

```
ModuleNotFoundError: No module named '_ctypes'
```

your Python version is missing the `libffi-dev`. 

On Ubuntu, you can simply run `sudo apt-get install libffi-dev`. 

When using `pyenv`, you need to re-install the problematic Python versions with e.g. `pyenv install 3.10` after you installed `libffi-dev`.

## Contributing

If you want to contribute to the project, please search for an issue you would like to work on and make a Pull Request.
If you find a bug or have a feature request, please open an issue.


## Acknowledgment

This is a project created and maintained by [BIOfid](https://www.biofid.de/en/) and 
the [Specialised Information Service Linguistic](https://www.linguistik.de/en/).
Both are projects funded by the German Research Foundation (DFG) and located at the [University Library J. C. Senckenberg](https://www.ub.uni-frankfurt.de/).

For further details, please refer to:

- BIOfid, DFG project identifier [326061700](https://gepris.dfg.de/gepris/projekt/326061700?language=en)
- Fachinformationsdienst Linguistik, DFG project identifier [326024153](https://gepris.dfg.de/gepris/projekt/326024153?language=en)
